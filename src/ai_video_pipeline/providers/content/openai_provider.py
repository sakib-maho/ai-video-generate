from __future__ import annotations

import os

from ...models import ScriptPackage, SelectedTopic, SeoPackage, ThumbnailPackage
from .base import BaseContentProvider


class OpenAIContentProvider(BaseContentProvider):
    name = "openai"

    def __init__(self, project_root) -> None:
        self.project_root = project_root

    def available(self) -> bool:
        if not os.environ.get("OPENAI_API_KEY"):
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def generate_script(self, topic: SelectedTopic) -> ScriptPackage:  # pragma: no cover
        raise NotImplementedError(
            "OpenAI script generation is intentionally isolated here. "
            "Set OPENAI_API_KEY and implement the provider call pattern you prefer."
        )

    def generate_seo(self, topic: SelectedTopic, script: ScriptPackage) -> SeoPackage:  # pragma: no cover
        raise NotImplementedError(
            "OpenAI SEO generation should be implemented in this adapter when credentials are available."
        )

    def generate_thumbnail(
        self, topic: SelectedTopic, script: ScriptPackage, seo: SeoPackage
    ) -> ThumbnailPackage:  # pragma: no cover
        raise NotImplementedError(
            "OpenAI thumbnail/image generation should be implemented in this adapter when needed."
        )
