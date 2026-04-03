from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar


def script_language_directive(language: str) -> str:
    """Prompt suffix so script JSON uses the target language (required for correct TTS)."""
    if language == "bn":
        return (
            "LANGUAGE (mandatory): Write ALL spoken and on-screen copy in Bengali (Bangla) using Bengali script (বাংলা). "
            "This includes hook, summary, every scene title/narration/caption, voiceover_script, the captions array, and cta. "
            "Do not use English for those strings. Use English only inside visual_prompt/animation_prompt if needed for image models.\n"
        )
    if language == "ja":
        return (
            "LANGUAGE (mandatory): Write ALL spoken and on-screen copy in Japanese (日本語), including hook, summary, "
            "scene narration/captions, voiceover_script, captions, and cta. English only where unavoidable for loanwords.\n"
        )
    if language == "hi":
        return (
            "LANGUAGE (mandatory): Write ALL spoken and on-screen copy in Hindi using Devanagari script (हिन्दी). "
            "This includes hook, summary, every scene title/narration/caption, voiceover_script, captions array, and cta. "
            "Do not use English for those strings. English only inside visual_prompt/animation_prompt if needed for image models.\n"
        )
    return (
        "LANGUAGE: Use natural English for hook, narration, voiceover_script, captions, and cta.\n"
    )


def summary_only_script_directive() -> str:
    """Spoken copy must sound like a short AI explainer, not a news bibliography."""
    return (
        "SPOKEN COPY (mandatory): hook, every scene narration, voiceover_script, captions, and cta must be plain, "
        "viewer-friendly summary language only. Do NOT include URLs, domain names, publication titles, 'source context', "
        "citation lists, or phrases like 'according to reports from…'. Do not read research or feed metadata aloud. "
        "Paraphrase the idea in natural speech. visual_prompt and animation_prompt may stay concrete for image models.\n"
    )


def scene_variety_directive(duration_seconds: int) -> str:
    """Ask the script model for many distinct visual beats so each scene gets its own image."""
    min_s = int(os.environ.get("PIPELINE_MIN_SCENES", "6"))
    max_s = int(os.environ.get("PIPELINE_MAX_SCENES", "10"))
    target = max(min_s, min(max_s, max(min_s, (int(duration_seconds) + 4) // 6)))
    return (
        f"SCENE COUNT & VISUAL VARIETY (mandatory): Provide at least {target} objects in `scenes` "
        f"(indices 1..N in order) for a ~{duration_seconds}s video. "
        "Each scene MUST have a unique `visual_prompt` and `setting`: change location, time, mood, or story beat—"
        "never describe one static illustration reused for the whole short. Advance the narrative visually every scene. "
        "Vary `shot_type`, `camera_move`, and `action` so each frame would look clearly different as a still image. "
        "Include matching `storyboard` rows (one per scene, scene_index aligned).\n"
    )


def funny_cartoon_angle_directive() -> str:
    """Extra prompt for funny, high-energy cartoon shorts (paired with content_angle=funny_cartoon)."""
    return (
        "CONTENT ANGLE (mandatory): Treat this as a FUNNY cartoon comedy short — family-safe, playful, exaggerated "
        "reactions, light slapstick, visual gags, and comic timing. Avoid grim or purely serious news tone; "
        "reframe the topic into cartoon hijinks while staying respectful. "
        "Visual target: premium 3D CGI (theatrical/Pixar-like polish), bright inviting lighting, readable "
        "environments (markets, streets, homes). Emphasize bouncy motion, expressive poses, and clear silhouettes "
        "in visual_prompt and animation_prompt.\n"
    )


def seo_language_directive(language: str) -> str:
    """Prompt suffix for SEO metadata language."""
    if language == "bn":
        return (
            "Write title_options, final_title, description, hashtags, and platform tags for a Bangladesh audience; "
            "prefer Bengali (Bangla script) for titles/description/hashtags where natural.\n"
        )
    if language == "ja":
        return "Write title_options, final_title, description, and tags primarily in Japanese.\n"
    if language == "hi":
        return (
            "Write title_options, final_title, description, hashtags, and platform tags for a Hindi-speaking audience; "
            "prefer Hindi in Devanagari for titles/description/hashtags where natural.\n"
        )
    return ""


STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "of",
    "to",
    "and",
    "in",
    "on",
    "for",
    "with",
    "as",
    "at",
    "new",
    "top",
    "after",
    "across",
    "from",
    "over",
    "into",
    "bangladesh",
    "japan",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(text: str) -> str:
    value = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-") or "item"


def normalize_topic(text: str) -> str:
    lowered = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = [token for token in lowered.split() if token and token not in STOPWORDS]
    return " ".join(tokens[:8]).strip()


def topic_signature(text: str) -> str:
    lowered = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = sorted({token for token in lowered.split() if token and token not in STOPWORDS})
    return " ".join(tokens[:6]).strip() or slugify(text)


def split_sentences(text: str, max_chars: int = 260) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?।！？])\s+", normalized)
    chunks: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not current:
            current = part
            continue
        if len(current) + 1 + len(part) <= max_chars:
            current = f"{current} {part}"
        else:
            chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def recency_hours(value: datetime | None, reference: datetime | None = None) -> float:
    if value is None:
        return 999.0
    base = reference or now_local()
    return max((base - value).total_seconds() / 3600.0, 0.0)


def within_days(value: datetime | None, days: int, reference: datetime | None = None) -> bool:
    if value is None:
        return False
    base = reference or now_local()
    return value >= base - timedelta(days=days)


def escape_drawtext_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:")


def discover_font(language: str) -> str | None:
    candidates: dict[str, list[str]] = {
        "en": [
            os.environ.get("FONT_PATH_LATIN", ""),
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
        ],
        "ja": [
            os.environ.get("FONT_PATH_JAPANESE", ""),
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ],
        "bn": [
            os.environ.get("FONT_PATH_BENGALI", ""),
            "/Library/Fonts/NotoSansBengali-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ],
        "hi": [
            os.environ.get("FONT_PATH_DEVANAGARI", ""),
            "/Library/Fonts/NotoSansDevanagari-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ],
    }
    for item in candidates.get(language, candidates["en"]):
        if item and Path(item).exists():
            return item
    return None


def ffprobe_duration_seconds(path: Path) -> float | None:
    """Return audio/video duration in seconds using ffprobe, or None on failure."""
    ffprobe_bin = os.environ.get("FFPROBE_BIN", "ffprobe")
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
        if result.returncode != 0:
            return None
        line = (result.stdout or "").strip().splitlines()[0] if result.stdout else ""
        if not line or line == "N/A":
            return None
        return float(line)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return None


def slideshow_stitched_duration_seconds(scene_durations: list[float]) -> float:
    """Approximate final video length from slideshow (sum of scenes minus xfade overlaps)."""
    n = len(scene_durations)
    if n == 0:
        return 0.0
    xfade = float(os.environ.get("SLIDESHOW_XFADE_SECONDS", "0.35"))
    trans = min(xfade, max(0.0, min(scene_durations) * 0.4)) if n else 0.0
    if n > 1 and trans > 0.05 and xfade > 0:
        return float(sum(scene_durations)) - (n - 1) * trans
    return float(sum(scene_durations))


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=str(cwd) if cwd else None, check=False, text=True, capture_output=True
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=err or result.stderr,
        )
    return result


T = TypeVar("T")


def retry_call(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
) -> T:
    last_error: Exception | None = None
    current_delay = delay_seconds
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(current_delay)
            current_delay *= backoff
    assert last_error is not None
    raise last_error
