from __future__ import annotations

from ...models import VideoRenderRequest, VideoRenderResult
from .base import BaseVideoProvider


class SoraVideoProvider(BaseVideoProvider):
    name = "sora"

    def available(self) -> bool:
        return False

    def render(self, request: VideoRenderRequest) -> VideoRenderResult:  # pragma: no cover
        raise NotImplementedError("Sora adapter is reserved for credential-specific implementation.")
