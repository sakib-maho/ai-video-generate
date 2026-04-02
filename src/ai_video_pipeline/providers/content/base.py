from __future__ import annotations

from abc import ABC, abstractmethod

from ...models import ScriptPackage, SelectedTopic, SeoPackage, ThumbnailPackage


class BaseContentProvider(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def generate_script(self, topic: SelectedTopic) -> ScriptPackage:
        raise NotImplementedError

    @abstractmethod
    def generate_seo(self, topic: SelectedTopic, script: ScriptPackage) -> SeoPackage:
        raise NotImplementedError

    @abstractmethod
    def generate_thumbnail(self, topic: SelectedTopic, script: ScriptPackage, seo: SeoPackage) -> ThumbnailPackage:
        raise NotImplementedError
