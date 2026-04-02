from __future__ import annotations

from pathlib import Path

from .providers.voice import GeminiTTSVoiceProvider, NoOpVoiceProvider
from .providers.voice.base import BaseVoiceProvider


class VoiceService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.providers: dict[str, BaseVoiceProvider] = {
            "gemini_tts": GeminiTTSVoiceProvider(),
            "noop": NoOpVoiceProvider(),
        }

    def resolve_provider(self, preferred: str = "gemini_tts", fallbacks: list[str] | None = None) -> BaseVoiceProvider:
        for name in [preferred] + (fallbacks or ["noop"]):
            provider = self.providers.get(name)
            if provider and provider.available():
                return provider
        return self.providers["noop"]
