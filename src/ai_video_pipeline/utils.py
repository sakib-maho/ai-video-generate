from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, TypeVar


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
    }
    for item in candidates.get(language, candidates["en"]):
        if item and Path(item).exists():
            return item
    return None


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
