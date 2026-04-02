from __future__ import annotations

from pathlib import Path

from .providers.voice import GeminiTTSVoiceProvider, MacOSSayVoiceProvider, NoOpVoiceProvider, OpenAITTSVoiceProvider, PiperTTSVoiceProvider
from .providers.voice.base import BaseVoiceProvider


class VoiceService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.providers: dict[str, BaseVoiceProvider] = {
            "openai_tts": OpenAITTSVoiceProvider(),
            "gemini_tts": GeminiTTSVoiceProvider(),
            "piper_tts": PiperTTSVoiceProvider(),
            "macos_say": MacOSSayVoiceProvider(),
            "noop": NoOpVoiceProvider(),
        }

    def resolve_provider(self, preferred: str = "openai_tts", fallbacks: list[str] | None = None) -> BaseVoiceProvider:
        for name in [preferred] + (fallbacks or ["gemini_tts", "piper_tts", "macos_say", "noop"]):
            provider = self.providers.get(name)
            if provider and provider.available():
                return provider
        return self.providers["noop"]

    def ordered_providers(self, preferred: str = "openai_tts", fallbacks: list[str] | None = None) -> list[BaseVoiceProvider]:
        ordered: list[BaseVoiceProvider] = []
        for name in [preferred] + (fallbacks or ["gemini_tts", "piper_tts", "macos_say", "noop"]):
            provider = self.providers.get(name)
            if provider and provider.available() and provider not in ordered:
                ordered.append(provider)
        if self.providers["noop"] not in ordered:
            ordered.append(self.providers["noop"])
        return ordered
