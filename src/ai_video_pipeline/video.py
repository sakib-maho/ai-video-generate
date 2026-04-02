from __future__ import annotations

from pathlib import Path

from .models import VideoRenderRequest, VideoRenderResult
from .providers.video import (
    KlingVideoProvider,
    PikaVideoProvider,
    RunwayVideoProvider,
    SlideshowVideoProvider,
    SoraVideoProvider,
)
from .providers.video.base import BaseVideoProvider


class VideoService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.providers: dict[str, BaseVideoProvider] = {
            "slideshow": SlideshowVideoProvider(),
            "sora": SoraVideoProvider(),
            "runway": RunwayVideoProvider(),
            "kling": KlingVideoProvider(),
            "pika": PikaVideoProvider(),
        }

    def resolve_provider(self, preferred: str, fallbacks: list[str]) -> BaseVideoProvider:
        for name in [preferred] + fallbacks:
            provider = self.providers.get(name)
            if provider and provider.available():
                return provider
        return self.providers["slideshow"]

    def render(self, preferred: str, fallbacks: list[str], request: VideoRenderRequest) -> VideoRenderResult:
        provider = self.resolve_provider(preferred, fallbacks)
        return provider.render(request)
