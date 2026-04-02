from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(slots=True)
class CountryConfig:
    name: str
    label: str
    default_language: str
    languages: list[str]
    enabled: bool
    videos_per_day: int
    news_feeds: list[str]
    reddit_feeds: list[str]
    trends_feeds: list[str]


@dataclass(slots=True)
class ScheduleConfig:
    enabled: bool
    timezone: str
    hour: int
    minute: int


@dataclass(slots=True)
class GlobalDefaults:
    script_duration_seconds: int
    extended_script_duration_seconds: int
    tone: str
    thumbnail_style: str
    videos_per_country: int
    history_cooldown_days: int
    safety_threshold: float
    max_retry_attempts: int
    enable_background_music: bool
    enable_voiceover: bool
    brand_intro: bool
    brand_outro: bool
    evergreen_fallback: bool


@dataclass(slots=True)
class ProviderConfig:
    primary: str
    fallback: list[str]


@dataclass(slots=True)
class PipelineConfig:
    database_path: str
    output_root: str
    log_level: str
    mode: str
    schedule: ScheduleConfig
    global_defaults: GlobalDefaults
    countries: list[CountryConfig]
    content_provider: ProviderConfig
    video_provider: ProviderConfig


@dataclass(slots=True)
class TopicSource:
    name: str
    source_type: str
    url: str


@dataclass(slots=True)
class TopicCandidate:
    title: str
    country: str
    signature: str
    sources: list[TopicSource]
    why_trending: str
    published_at: datetime | None
    source_count: int
    trend_score: float = 0.0
    freshness_score: float = 0.0
    suitability_score: float = 0.0
    risk_flags: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    fact_check_status: str = "needs_review"
    citations: list[str] = field(default_factory=list)
    duplicate_recently_used: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactCheckSourceAssessment:
    url: str
    domain: str
    credibility: str
    corroborates: bool
    snippet: str
    notes: str


@dataclass(slots=True)
class FactCheckReport:
    status: str
    summary: str
    claims: list[str]
    verified_claims: list[str]
    uncertain_claims: list[str]
    source_assessments: list[FactCheckSourceAssessment]
    citations: list[str]
    reviewer: str


@dataclass(slots=True)
class SelectedTopic:
    candidate: TopicCandidate
    language: str
    tone: str
    duration_seconds: int


@dataclass(slots=True)
class Scene:
    index: int
    title: str
    visual_prompt: str
    narration: str
    caption: str
    duration_seconds: float


@dataclass(slots=True)
class ScriptPackage:
    hook: str
    summary: str
    scenes: list[Scene]
    voiceover_script: str
    captions: list[str]
    cta: str
    language: str
    tone: str


@dataclass(slots=True)
class SeoPackage:
    title_options: list[str]
    final_title: str
    description: str
    hashtags: list[str]
    keywords: list[str]
    upload_filename: str
    youtube_tags: list[str]
    tiktok_tags: list[str]
    instagram_tags: list[str]


@dataclass(slots=True)
class ThumbnailPackage:
    text_options: list[str]
    selected_text: str
    prompt: str
    style: str
    source_image_path: str | None = None
    thumbnail_path: str | None = None
    vertical_cover_path: str | None = None


@dataclass(slots=True)
class VideoRenderRequest:
    country: str
    run_date: str
    output_dir: Path
    topic: SelectedTopic
    script: ScriptPackage
    seo: SeoPackage
    thumbnail: ThumbnailPackage
    subtitles_path: Path
    final_output_path: Path
    include_music: bool
    include_voiceover: bool
    brand_intro: bool
    brand_outro: bool
    scene_image_paths: list[str] = field(default_factory=list)
    voiceover_audio_path: Path | None = None
    background_music_path: str | None = None


@dataclass(slots=True)
class VideoRenderResult:
    provider_name: str
    output_path: str
    status: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CountryRunArtifacts:
    selected_topic: SelectedTopic
    script: ScriptPackage
    seo: SeoPackage
    thumbnail: ThumbnailPackage
    scene_image_paths: list[Path]
    subtitles_path: Path
    metadata_path: Path
    voiceover_path: Path | None
    final_video_path: Path | None
