from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

from .models import FactCheckReport, FactCheckSourceAssessment, TopicCandidate
from .utils import normalize_topic, retry_call


TRUSTED_DOMAINS = {
    "news.google.com": "high",
    "google.com": "medium",
    "nhk.or.jp": "high",
    "japantimes.co.jp": "high",
    "bdnews24.com": "high",
    "thedailystar.net": "high",
    "reddit.com": "low",
    "x.com": "low",
    "twitter.com": "low",
    "example.com": "low",
}


class FactCheckService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
        self.gemini_api_version = os.environ.get("GEMINI_API_VERSION", "v1beta").strip()

    def evaluate(self, candidate: TopicCandidate) -> FactCheckReport:
        if candidate.extra.get("fallback") == "evergreen":
            claims = self._extract_claims(candidate)
            return FactCheckReport(
                status="verified",
                summary="Evergreen internal fallback topic selected; no external factual claim escalation detected.",
                claims=claims,
                verified_claims=claims,
                uncertain_claims=[],
                source_assessments=[
                    FactCheckSourceAssessment(
                        url="local://evergreen",
                        domain="local",
                        credibility="internal",
                        corroborates=True,
                        snippet=candidate.why_trending,
                        notes="Internal evergreen topic seed.",
                    )
                ],
                citations=["local://evergreen"],
                reviewer="heuristic_v1",
            )

        claims = self._extract_claims(candidate)
        assessments = [self._assess_source(url, claims) for url in candidate.citations[:3]]
        # Do not let LLM fact-check override explicit misinformation risk flags.
        if "misinformation" in candidate.risk_flags:
            return self._evaluate_heuristic(candidate, claims, assessments)
        openai_report = self._evaluate_with_openai(candidate, claims, assessments)
        if openai_report is not None:
            return openai_report
        gemini_report = self._evaluate_with_gemini(candidate, claims, assessments)
        if gemini_report is not None:
            return gemini_report

        return self._evaluate_heuristic(candidate, claims, assessments)

    def _evaluate_heuristic(
        self,
        candidate: TopicCandidate,
        claims: list[str],
        assessments: list[FactCheckSourceAssessment],
    ) -> FactCheckReport:
        corroborating = [item for item in assessments if item.corroborates]
        trusted = [item for item in assessments if item.credibility in {"high", "medium"}]
        trusted_corroborating = [item for item in trusted if item.corroborates]

        if "misinformation" in candidate.risk_flags:
            status = "unsafe"
            summary = "Topic is flagged as potential misinformation and is blocked before script generation."
        elif "graphic" in candidate.risk_flags and len(trusted_corroborating) < 2:
            status = "unsafe"
            summary = "Graphic or harm-sensitive topic lacks enough corroboration from trusted sources."
        elif len(trusted_corroborating) >= 2:
            status = "verified"
            summary = "Multiple trusted sources corroborate the core claim set."
        elif trusted and corroborating:
            status = "needs_review"
            summary = "At least one credible source supports the topic, but corroboration is still limited."
        elif candidate.source_count >= 2 and corroborating:
            status = "needs_review"
            summary = "Multiple sources mention the topic, but source credibility remains mixed."
        elif trusted and not corroborating:
            status = "conflicting"
            summary = "Trusted sources were found, but the fetched evidence did not clearly support the selected framing."
        else:
            status = "needs_review"
            summary = "Evidence is limited; topic is usable only with cautious, attribution-heavy scripting."

        verified_claims = claims if status == "verified" else []
        uncertain_claims = claims if status in {"needs_review", "conflicting", "unsafe"} else []
        return FactCheckReport(
            status=status,
            summary=summary,
            claims=claims,
            verified_claims=verified_claims,
            uncertain_claims=uncertain_claims,
            source_assessments=assessments,
            citations=candidate.citations,
            reviewer="heuristic_v1",
        )

    def _evaluate_with_gemini(
        self,
        candidate: TopicCandidate,
        claims: list[str],
        assessments: list[FactCheckSourceAssessment],
    ) -> FactCheckReport | None:
        if not self.gemini_api_key:
            return None

        prompt = self._build_gemini_prompt(candidate, claims, assessments)
        try:
            payload = self._call_gemini_json(prompt)
        except Exception:
            return None

        status = payload.get("status", "needs_review")
        if status not in {"verified", "needs_review", "conflicting", "unsafe"}:
            status = "needs_review"
        summary = str(payload.get("summary", "Gemini fact-check returned no summary."))[:400]
        verified_claims = [str(item)[:220] for item in payload.get("verified_claims", [])]
        uncertain_claims = [str(item)[:220] for item in payload.get("uncertain_claims", [])]
        returned_claims = [str(item)[:220] for item in payload.get("claims", [])] or claims

        return FactCheckReport(
            status=status,
            summary=summary,
            claims=returned_claims[:4],
            verified_claims=verified_claims[:4],
            uncertain_claims=uncertain_claims[:4],
            source_assessments=assessments,
            citations=candidate.citations,
            reviewer=f"gemini:{self.gemini_model}",
        )

    def _evaluate_with_openai(
        self,
        candidate: TopicCandidate,
        claims: list[str],
        assessments: list[FactCheckSourceAssessment],
    ) -> FactCheckReport | None:
        if not self.openai_api_key:
            return None
        prompt = self._build_openai_prompt(candidate, claims, assessments)
        try:
            payload = self._call_openai_json(prompt)
        except Exception:
            return None

        status = payload.get("status", "needs_review")
        if status not in {"verified", "needs_review", "conflicting", "unsafe"}:
            status = "needs_review"
        summary = str(payload.get("summary", "OpenAI fact-check returned no summary."))[:400]
        verified_claims = [str(item)[:220] for item in payload.get("verified_claims", [])]
        uncertain_claims = [str(item)[:220] for item in payload.get("uncertain_claims", [])]
        returned_claims = [str(item)[:220] for item in payload.get("claims", [])] or claims
        return FactCheckReport(
            status=status,
            summary=summary,
            claims=returned_claims[:4],
            verified_claims=verified_claims[:4],
            uncertain_claims=uncertain_claims[:4],
            source_assessments=assessments,
            citations=candidate.citations,
            reviewer=f"openai:{self.openai_model}",
        )

    def _build_openai_prompt(
        self,
        candidate: TopicCandidate,
        claims: list[str],
        assessments: list[FactCheckSourceAssessment],
    ) -> str:
        assessment_lines = []
        for item in assessments:
            assessment_lines.append(
                json.dumps(
                    {
                        "url": item.url,
                        "domain": item.domain,
                        "credibility": item.credibility,
                        "corroborates": item.corroborates,
                        "snippet": item.snippet,
                        "notes": item.notes,
                    },
                    ensure_ascii=False,
                )
            )
        return (
            "Return strict JSON only.\n"
            "You are a conservative fact-checking assistant for short-form video production.\n"
            "Decide whether the topic framing is verified, needs_review, conflicting, or unsafe.\n"
            "Do not upgrade weak evidence. If evidence is thin, return needs_review.\n"
            f"Country: {candidate.country}\n"
            f"Topic: {candidate.title}\n"
            f"Why trending: {candidate.why_trending}\n"
            f"Risk flags: {candidate.risk_flags}\n"
            f"Claims: {json.dumps(claims, ensure_ascii=False)}\n"
            f"Source assessments: [{', '.join(assessment_lines)}]\n"
            "JSON schema:\n"
            "{"
            '"status":"verified|needs_review|conflicting|unsafe",'
            '"summary":"string",'
            '"claims":["string"],'
            '"verified_claims":["string"],'
            '"uncertain_claims":["string"]'
            "}"
        )

    def _call_openai_json(self, prompt: str) -> dict[str, Any]:
        url = "https://api.openai.com/v1/responses"
        body = {
            "model": self.openai_model,
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            },
            method="POST",
        )

        def _do_request() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"OpenAI fact-check API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"OpenAI fact-check request failed: {exc}") from exc

            text = data.get("output_text", "").strip()
            if not text:
                outputs = data.get("output", [])
                for item in outputs:
                    for content in item.get("content", []):
                        if content.get("type") in {"output_text", "text"} and content.get("text"):
                            text = str(content["text"]).strip()
                            break
                    if text:
                        break
            if not text:
                raise RuntimeError(f"OpenAI fact-check response contained no text output: {data}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    raise RuntimeError(f"OpenAI fact-check response was not parseable JSON: {text}")
                return json.loads(text[start : end + 1])

        return retry_call(_do_request, attempts=2, delay_seconds=0.5, backoff=2.0)

    def _build_gemini_prompt(
        self,
        candidate: TopicCandidate,
        claims: list[str],
        assessments: list[FactCheckSourceAssessment],
    ) -> str:
        assessment_lines = []
        for item in assessments:
            assessment_lines.append(
                json.dumps(
                    {
                        "url": item.url,
                        "domain": item.domain,
                        "credibility": item.credibility,
                        "corroborates": item.corroborates,
                        "snippet": item.snippet,
                        "notes": item.notes,
                    },
                    ensure_ascii=False,
                )
            )
        return (
            "Return strict JSON only.\n"
            "You are a conservative fact-checking assistant for short-form video production.\n"
            "Decide whether the topic framing is verified, needs_review, conflicting, or unsafe.\n"
            "Do not upgrade weak evidence. If evidence is thin, return needs_review.\n"
            f"Country: {candidate.country}\n"
            f"Topic: {candidate.title}\n"
            f"Why trending: {candidate.why_trending}\n"
            f"Risk flags: {candidate.risk_flags}\n"
            f"Claims: {json.dumps(claims, ensure_ascii=False)}\n"
            f"Source assessments: [{', '.join(assessment_lines)}]\n"
            "JSON schema:\n"
            "{"
            '"status":"verified|needs_review|conflicting|unsafe",'
            '"summary":"string",'
            '"claims":["string"],'
            '"verified_claims":["string"],'
            '"uncertain_claims":["string"]'
            "}"
        )

    def _call_gemini_json(self, prompt: str) -> dict[str, Any]:
        url = (
            f"https://generativelanguage.googleapis.com/{self.gemini_api_version}/models/"
            f"{self.gemini_model}:generateContent"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.8,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.gemini_api_key,
            },
            method="POST",
        )

        def _do_request() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Gemini fact-check API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Gemini fact-check request failed: {exc}") from exc

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"Gemini fact-check returned no candidates: {data}")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts if part.get("text")).strip()
            if not text:
                raise RuntimeError(f"Gemini fact-check returned no text: {data}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    raise RuntimeError(f"Gemini fact-check response was not parseable JSON: {text}")
                return json.loads(text[start : end + 1])

        return retry_call(_do_request, attempts=2, delay_seconds=0.5, backoff=2.0)

    def _extract_claims(self, candidate: TopicCandidate) -> list[str]:
        claims = []
        if candidate.title.strip():
            claims.append(candidate.title.strip())
        for sentence in re.split(r"(?<=[.!?।！？])\s+", candidate.why_trending.strip()):
            sentence = sentence.strip()
            if sentence and sentence not in claims:
                claims.append(sentence[:220])
        return claims[:4]

    def _assess_source(self, url: str, claims: list[str]) -> FactCheckSourceAssessment:
        domain = urllib.parse.urlparse(url).netloc.lower() or "unknown"
        credibility = self._credibility_for_domain(domain)
        snippet, notes = self._fetch_snippet(url)
        corroborates = self._snippet_supports_claims(snippet, claims)
        return FactCheckSourceAssessment(
            url=url,
            domain=domain,
            credibility=credibility,
            corroborates=corroborates,
            snippet=snippet[:360],
            notes=notes or "No notes.",
        )

    def _credibility_for_domain(self, domain: str) -> str:
        for known, credibility in TRUSTED_DOMAINS.items():
            if domain.endswith(known):
                return credibility
        return "unknown"

    def _fetch_snippet(self, url: str) -> tuple[str, str]:
        if not url.startswith(("http://", "https://")):
            return "", "Non-http citation."
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Video-Pipeline/1.0)"},
        )

        def _do_fetch() -> tuple[str, str]:
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    raw = response.read(8192).decode("utf-8", errors="ignore")
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                return "", f"Fetch failed: {exc}"
            text = self._strip_html(raw)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:600], "Fetched source snippet."

        return retry_call(_do_fetch, attempts=2, delay_seconds=0.3, backoff=2.0)

    def _strip_html(self, html: str) -> str:
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return unescape(text)

    def _snippet_supports_claims(self, snippet: str, claims: list[str]) -> bool:
        normalized_snippet = normalize_topic(snippet)
        if not normalized_snippet:
            return False
        snippet_tokens = set(normalized_snippet.split())
        for claim in claims:
            claim_tokens = set(normalize_topic(claim).split())
            if not claim_tokens:
                continue
            overlap = len(claim_tokens & snippet_tokens)
            if overlap >= max(2, len(claim_tokens) // 3):
                return True
        return False
