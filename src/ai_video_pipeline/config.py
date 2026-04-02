from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import CountryConfig, GlobalDefaults, PipelineConfig, ProviderConfig, ScheduleConfig
from .utils import load_env_file


def _load_serialized(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Config is not JSON-compatible and PyYAML is not installed. "
            "Either install requirements.txt or keep config/config.yaml in JSON-compatible YAML."
        ) from exc

    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("Configuration root must be an object")
    return payload


def load_config(path: Path) -> PipelineConfig:
    load_env_file(path.parent.parent / ".env")
    raw = _load_serialized(path)

    schedule = ScheduleConfig(**raw["schedule"])
    defaults = GlobalDefaults(**raw["global_defaults"])
    countries = [CountryConfig(**entry) for entry in raw["countries"]]
    content_provider = ProviderConfig(**raw["providers"]["content"])
    video_provider = ProviderConfig(**raw["providers"]["video"])

    config = PipelineConfig(
        database_path=os.environ.get("PIPELINE_DATABASE_PATH", raw["database_path"]),
        output_root=os.environ.get("PIPELINE_OUTPUT_ROOT", raw["output_root"]),
        log_level=os.environ.get("LOG_LEVEL", raw["log_level"]),
        mode=os.environ.get("PIPELINE_MODE", raw["mode"]),
        schedule=schedule,
        global_defaults=defaults,
        countries=countries,
        content_provider=content_provider,
        video_provider=video_provider,
    )
    return config
