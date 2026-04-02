from __future__ import annotations

from pathlib import Path

from .base import BaseVoiceProvider


class NoOpVoiceProvider(BaseVoiceProvider):
    name = "noop"

    def available(self) -> bool:
        return True

    def synthesize(self, *, text: str, language: str, output_path: Path) -> Path:
        raise RuntimeError("No voice provider is configured.")
