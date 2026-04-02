from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import ensure_dir


class PipelineLogger:
    def __init__(self, log_dir: Path, level: str = "INFO") -> None:
        ensure_dir(log_dir)
        self.text_path = log_dir / "logs.txt"
        self.json_path = log_dir / "logs.jsonl"
        self.logger = logging.getLogger(f"ai_video_pipeline.{id(self)}")
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self.logger.handlers.clear()
        handler = logging.FileHandler(self.text_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.logger.addHandler(console)

    def info(self, message: str) -> None:
        self.logger.info(message)

    def warning(self, message: str) -> None:
        self.logger.warning(message)

    def error(self, message: str) -> None:
        self.logger.error(message)

    def event(self, event_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "event": event_type,
            "payload": payload,
        }
        with self.json_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
