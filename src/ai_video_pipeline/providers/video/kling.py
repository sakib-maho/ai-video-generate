from __future__ import annotations

from ...models import VideoRenderRequest, VideoRenderResult
from .base import BaseVideoProvider


class KlingVideoProvider(BaseVideoProvider):
    name = "kling"

    def available(self) -> bool:
        return False

    def render(self, request: VideoRenderRequest) -> VideoRenderResult:  # pragma: no cover
        raise NotImplementedError("Kling adapter is reserved for credential-specific implementation.")
