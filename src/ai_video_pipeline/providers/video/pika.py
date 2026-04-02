from __future__ import annotations

from ...models import VideoRenderRequest, VideoRenderResult
from .base import BaseVideoProvider


class PikaVideoProvider(BaseVideoProvider):
    name = "pika"

    def available(self) -> bool:
        return False

    def render(self, request: VideoRenderRequest) -> VideoRenderResult:  # pragma: no cover
        raise NotImplementedError("Pika adapter is reserved for credential-specific implementation.")
