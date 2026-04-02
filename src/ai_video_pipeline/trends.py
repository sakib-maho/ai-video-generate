from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

from .logging_utils import PipelineLogger
from .models import CountryConfig, TopicCandidate, TopicSource
from .utils import iso_to_datetime, normalize_topic, recency_hours, topic_signature, within_days


SAFE_VISUAL_KEYWORDS = {
    "launch",
    "festival",
    "robot",
    "weather",
    "travel",
    "cherry",
    "tech",
    "showcase",
    "record",
    "heatwave",
    "transport",
    "sports",
}

SENSITIVE_KEYWORDS = {
    "election": "political",
    "war": "sensitive",
    "killed": "graphic",
    "dead": "graphic",
    "attack": "sensitive",
    "bomb": "graphic",
    "misinformation": "misinformation",
    "rumor": "misinformation",
    "scam": "misinformation",
}


def fetch_url(url: str, timeout: int = 15) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AI-Video-Pipeline/1.0)",
            "Accept": "application/json, application/xml, text/xml, application/rss+xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class TrendDiscoveryService:
    def __init__(self, project_root: Path, logger: PipelineLogger) -> None:
        self.project_root = project_root
        self.logger = logger

    def discover(self, country: CountryConfig, use_sample_data: bool = False) -> list[TopicCandidate]:
        if use_sample_data:
            return self._load_seed(country)

        raw_items: list[TopicCandidate] = []
        for url in country.trends_feeds:
            raw_items.extend(self._discover_rss(country, url, source_type="trends"))
        for url in country.news_feeds:
            raw_items.extend(self._discover_rss(country, url, source_type="news"))
        for url in country.reddit_feeds:
            raw_items.extend(self._discover_reddit(country, url))

        if not raw_items:
            self.logger.warning(f"No live discovery results for {country.name}; using seed topics")
            return self._load_seed(country)

        return aggregate_and_score(raw_items, logger=self.logger)

    def _load_seed(self, country: CountryConfig) -> list[TopicCandidate]:
        seed_path = self.project_root / "data" / "seed_topics.json"
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        topics = []
        for item in payload.get(country.name, []):
            title = item["title"]
            published_at = iso_to_datetime(item.get("published_at"))
            topics.append(
                TopicCandidate(
                    title=title,
                    country=country.name,
                    signature=topic_signature(title),
                    sources=[
                        TopicSource(
                            name=item["source_name"],
                            source_type=item["source_type"],
                            url=item["source_url"],
                        )
                    ],
                    why_trending=item["why_trending"],
                    published_at=published_at,
                    source_count=1,
                    citations=[item["source_url"]],
                )
            )
        return aggregate_and_score(topics, logger=self.logger)

    def _discover_rss(self, country: CountryConfig, url: str, source_type: str) -> list[TopicCandidate]:
        try:
            data = fetch_url(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            self.logger.warning(f"Feed fetch failed for {url}: {exc}")
            return []

        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            self.logger.warning(f"Feed parse failed for {url}: {exc}")
            return []

        items: list[TopicCandidate] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            description = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or url).strip()
            pub_date_raw = (item.findtext("pubDate") or item.findtext("published") or "").strip()
            pub_date = None
            if pub_date_raw:
                try:
                    pub_date = parsedate_to_datetime(pub_date_raw)
                except (TypeError, ValueError):
                    pub_date = iso_to_datetime(pub_date_raw)
            items.append(
                TopicCandidate(
                    title=title,
                    country=country.name,
                    signature=topic_signature(title),
                    sources=[TopicSource(name=urllib.parse.urlparse(url).netloc, source_type=source_type, url=link)],
                    why_trending=description[:320] or f"Fresh signal from {urllib.parse.urlparse(url).netloc}",
                    published_at=pub_date,
                    source_count=1,
                    citations=[link],
                )
            )
        return items

    def _discover_reddit(self, country: CountryConfig, url: str) -> list[TopicCandidate]:
        try:
            data = fetch_url(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            self.logger.warning(f"Reddit fetch failed for {url}: {exc}")
            return []

        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self.logger.warning(f"Reddit JSON parse failed for {url}: {exc}")
            return []

        items: list[TopicCandidate] = []
        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = (post.get("title") or "").strip()
            if not title:
                continue
            permalink = post.get("permalink", "")
            link = f"https://www.reddit.com{permalink}" if permalink else url
            created_utc = post.get("created_utc")
            published_at = datetime.fromtimestamp(created_utc).astimezone() if created_utc else None
            items.append(
                TopicCandidate(
                    title=title,
                    country=country.name,
                    signature=topic_signature(title),
                    sources=[TopicSource(name="Reddit", source_type="social", url=link)],
                    why_trending=f"High-engagement community discussion with score {post.get('score', 0)}.",
                    published_at=published_at,
                    source_count=1,
                    citations=[link],
                )
            )
        return items


def aggregate_and_score(candidates: Iterable[TopicCandidate], logger: PipelineLogger | None = None) -> list[TopicCandidate]:
    grouped: dict[tuple[str, str], list[TopicCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.country, candidate.signature)].append(candidate)

    merged: list[TopicCandidate] = []
    for (_, _), items in grouped.items():
        canonical = max(items, key=lambda item: len(item.title))
        sources = []
        citations = []
        why_bits = []
        most_recent = None
        for item in items:
            sources.extend(item.sources)
            citations.extend(item.citations)
            why_bits.append(item.why_trending)
            if item.published_at and (most_recent is None or item.published_at > most_recent):
                most_recent = item.published_at

        merged_candidate = TopicCandidate(
            title=canonical.title,
            country=canonical.country,
            signature=canonical.signature,
            sources=sources,
            why_trending=" ".join(dict.fromkeys(bit for bit in why_bits if bit))[:500],
            published_at=most_recent,
            source_count=len({source.url for source in sources}),
            citations=list(dict.fromkeys(citations)),
        )
        merged_candidate.freshness_score = score_freshness(merged_candidate.published_at)
        merged_candidate.risk_flags = detect_risk_flags(merged_candidate.title, merged_candidate.why_trending)
        merged_candidate.risk_score = score_risk(merged_candidate.risk_flags)
        merged_candidate.suitability_score = score_suitability(merged_candidate.title, merged_candidate.why_trending)
        merged_candidate.fact_check_status = classify_fact_check(merged_candidate)
        merged_candidate.trend_score = round(
            30.0
            + merged_candidate.freshness_score
            + min(merged_candidate.source_count * 8.0, 24.0)
            + merged_candidate.suitability_score
            - merged_candidate.risk_score,
            2,
        )
        merged.append(merged_candidate)

    merged.sort(key=lambda item: item.trend_score, reverse=True)
    if logger:
        logger.event("trend_discovery_ranked", {"count": len(merged)})
    return merged


def score_freshness(published_at: datetime | None) -> float:
    hours = recency_hours(published_at)
    if hours <= 3:
        return 25.0
    if hours <= 8:
        return 20.0
    if hours <= 24:
        return 14.0
    if hours <= 48:
        return 8.0
    if hours <= 96:
        return 3.0
    return 0.0


def detect_risk_flags(title: str, why_trending: str) -> list[str]:
    combined = f"{title} {why_trending}".lower()
    flags = {flag for keyword, flag in SENSITIVE_KEYWORDS.items() if keyword in combined}
    return sorted(flags)


def score_risk(flags: list[str]) -> float:
    mapping = {"political": 10.0, "sensitive": 12.0, "graphic": 18.0, "misinformation": 20.0}
    return sum(mapping.get(flag, 6.0) for flag in flags)


def score_suitability(title: str, why_trending: str) -> float:
    combined = f"{title} {why_trending}".lower()
    visual_bonus = sum(4.0 for keyword in SAFE_VISUAL_KEYWORDS if keyword in combined)
    brevity_bonus = 6.0 if len(normalize_topic(title).split()) <= 8 else 2.0
    return min(visual_bonus + brevity_bonus, 24.0)


def classify_fact_check(candidate: TopicCandidate) -> str:
    if "misinformation" in candidate.risk_flags:
        return "unsafe"
    if candidate.source_count >= 2:
        return "verified"
    if within_days(candidate.published_at, 2):
        return "needs_review"
    return "verified"

