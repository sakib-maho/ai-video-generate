from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import Scene, ScriptPackage, SelectedTopic, SeoPackage, ThumbnailPackage
from .providers.content import GeminiContentProvider, OpenAIContentProvider
from .providers.content.base import BaseContentProvider
from .utils import slugify


LANGUAGE_STRINGS = {
    "en": {
        "hook": "Why is everyone suddenly talking about {topic}?",
        "scene_open": "Here is the key update.",
        "cta": "Follow for clearer daily trend breakdowns.",
        "description": "{topic} is gaining traction in {country}. This short explains what happened, why it matters, and what people are reacting to right now.",
        "thumb": "{topic}\nWhy Now?",
    },
    "ja": {
        "hook": "今なぜ「{topic}」がこれほど話題なのか。",
        "scene_open": "ここが押さえるべきポイントです。",
        "cta": "毎日のトレンド解説を見たい方はフォローしてください。",
        "description": "{country}で話題の{topic}を短く整理しました。何が起きていて、なぜ注目されているのかを素早く把握できます。",
        "thumb": "{topic}\nなぜ話題？",
    },
    "bn": {
        "hook": "হঠাৎ করে কেন সবাই {topic} নিয়ে কথা বলছে?",
        "scene_open": "এখানেই মূল আপডেট।",
        "cta": "এমন নির্ভরযোগ্য ট্রেন্ড আপডেট পেতে ফলো করুন।",
        "description": "{country}-এ {topic} এখন আলোচনায়। কী ঘটেছে, কেন ট্রেন্ড করছে, আর মানুষ কীভাবে প্রতিক্রিয়া দিচ্ছে তা এই শর্টে সংক্ষেপে দেখানো হয়েছে।",
        "thumb": "{topic}\nকেন ট্রেন্ডিং?",
    },
}


class TemplateContentProvider(BaseContentProvider):
    name = "template"

    def available(self) -> bool:
        return True

    def generate_script(self, topic: SelectedTopic) -> ScriptPackage:
        strings = LANGUAGE_STRINGS.get(topic.language, LANGUAGE_STRINGS["en"])
        hook = strings["hook"].format(topic=topic.candidate.title)
        scene_count = 4 if topic.duration_seconds <= 60 else 5
        per_scene = round(topic.duration_seconds / scene_count, 2)
        scenes: list[Scene] = []
        source_names = ", ".join(sorted({source.name for source in topic.candidate.sources}))
        core_points = [
            topic.candidate.why_trending,
            f"This signal appeared across {topic.candidate.source_count} source streams.",
            "The topic is strong for short-form because it is easy to visualize and explain quickly.",
            "Credibility matters, so the coverage stays close to what reputable sources are actually reporting.",
            "If this develops further, a follow-up short can focus on reactions or practical impact.",
        ]
        for index in range(scene_count):
            point = core_points[index]
            scenes.append(
                Scene(
                    index=index + 1,
                    title=f"{strings['scene_open']} {index + 1}",
                    visual_prompt=f"Vertical short visual for {topic.candidate.title}, scene {index + 1}, high clarity, modern motion graphics, no copyrighted footage.",
                    narration=f"{hook if index == 0 else point} Source context: {source_names}.",
                    caption=point,
                    duration_seconds=per_scene,
                )
            )

        voiceover = " ".join(scene.narration for scene in scenes) + f" {strings['cta']}"
        captions = [scene.caption for scene in scenes]
        summary = f"{topic.candidate.title} is trending in {topic.candidate.country} because {topic.candidate.why_trending}"
        return ScriptPackage(
            hook=hook,
            summary=summary,
            scenes=scenes,
            voiceover_script=voiceover,
            captions=captions,
            cta=strings["cta"],
            language=topic.language,
            tone=topic.tone,
        )

    def generate_seo(self, topic: SelectedTopic, script: ScriptPackage) -> SeoPackage:
        country = topic.candidate.country.replace("_", " ").title()
        base = topic.candidate.title
        title_options = [
            f"{base}: What’s Actually Happening?",
            f"Why {base} Is Blowing Up Right Now",
            f"{country} Trend Watch: {base}",
            f"{base} in 45 Seconds",
            f"The Real Story Behind {base}",
        ]
        final_title = title_options[1]
        description = LANGUAGE_STRINGS.get(topic.language, LANGUAGE_STRINGS["en"])["description"].format(
            topic=base,
            country=country,
        )
        hashtags = [
            "#Shorts",
            "#Trending",
            f"#{slugify(country).replace('-', '')}",
            f"#{slugify(base).replace('-', '')[:24]}",
            "#NewsUpdate",
            "#ViralTopic",
            "#DailyBrief",
            "#Explained",
            "#YouTubeShorts",
            "#TikTokNews",
            "#Reels",
            "#CurrentEvents",
            "#TrendWatch",
            "#VisualStory",
            "#FastFacts",
            "#CredibleContent",
            "#DailyTopic",
            "#StoryIn60Seconds",
            "#SocialBuzz",
            "#WhatHappened",
        ]
        keywords = [slugify(word).replace("-", " ") for word in base.split()[:6]] + [country.lower(), "viral topic"]
        upload_filename = f"{topic.candidate.country}_{slugify(base)}_{topic.language}"
        tags = [topic.candidate.country, topic.language, topic.tone, "short video", "viral"]
        return SeoPackage(
            title_options=title_options,
            final_title=final_title,
            description=description,
            hashtags=hashtags,
            keywords=keywords,
            upload_filename=upload_filename,
            youtube_tags=tags + ["youtube shorts"],
            tiktok_tags=tags + ["tiktok"],
            instagram_tags=tags + ["instagram reels"],
        )

    def generate_thumbnail(self, topic: SelectedTopic, script: ScriptPackage, seo: SeoPackage) -> ThumbnailPackage:
        strings = LANGUAGE_STRINGS.get(topic.language, LANGUAGE_STRINGS["en"])
        prompt = (
            f"Create a bold short-video thumbnail about {topic.candidate.title}. "
            f"Style: {topic.tone}. Country focus: {topic.candidate.country}. "
            "Use clean editorial composition, high contrast, modern motion-news design, and no copyrighted footage."
        )
        text_options = [
            strings["thumb"].format(topic=topic.candidate.title[:28]),
            script.hook[:38],
            seo.final_title[:42],
        ]
        return ThumbnailPackage(
            text_options=text_options,
            selected_text=text_options[0],
            prompt=prompt,
            style="clean news",
        )


class ContentService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.providers: dict[str, BaseContentProvider] = {
            "template": TemplateContentProvider(),
            "gemini": GeminiContentProvider(project_root=project_root),
            "openai": OpenAIContentProvider(project_root=project_root),
        }

    def resolve_provider(self, preferred: str, fallbacks: list[str]) -> BaseContentProvider:
        for name in [preferred] + fallbacks:
            provider = self.providers.get(name)
            if provider and provider.available():
                return provider
        return self.providers["template"]
