from __future__ import annotations

from abc import ABC, abstractmethod

from ...models import VideoRenderRequest, VideoRenderResult


class BaseVideoProvider(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        raise NotImplementedError
