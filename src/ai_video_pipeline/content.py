from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import CharacterDesign, Scene, ScriptPackage, SelectedTopic, SeoPackage, StoryboardBeat, ThumbnailPackage
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
    "hi": {
        "hook": "अचानक सब {topic} की चर्चा क्यों कर रहे हैं?",
        "scene_open": "यही मुख्य अपडेट है।",
        "cta": "ऐसे भरोसेमंद ट्रेंड अपडेट के लिए फॉलो करें।",
        "description": "{country} में {topic} अभी चर्चा में है। क्या हुआ, क्यों ट्रेंड कर रहा है, और लोग कैसे प्रतिक्रिया दे रहे हैं—यह शॉर्ट में संक्षेप में।",
        "thumb": "{topic}\nक्यों ट्रेंड?",
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
        storyboard: list[StoryboardBeat] = []
        source_names = ", ".join(sorted({source.name for source in topic.candidate.sources}))
        host_name = {
            "en": "Mina",
            "ja": "Mina",
            "bn": "মীনা",
            "hi": "मीना",
        }.get(topic.language, "Mina")
        guide = CharacterDesign(
            name=host_name,
            role="on-camera animated host",
            appearance="young expressive presenter with big eyes, friendly face, soft cinematic lighting, stylized 3D cartoon proportions",
            wardrobe="clean modern outfit in coral and white, simple accessories, visually readable silhouette",
            personality="curious, warm, energetic, credible",
            consistency_prompt=f"{host_name}, the recurring animated host, must keep the same face, hairstyle, colors, outfit family, and stylized 3D-cartoon look in every shot.",
        )
        sidekick = CharacterDesign(
            name="Pulse",
            role="visual cue mascot",
            appearance="small floating geometric companion with glowing eyes and rounded shapes",
            wardrobe="teal and orange accent colors with polished toy-like material",
            personality="reactive, playful, supportive",
            consistency_prompt="Pulse should appear as the same floating mascot with identical colors and rounded 3D toy finish across scenes.",
        )
        character_sheet = [guide, sidekick]
        core_points = [
            {
                "title": strings["scene_open"],
                "setting": "colorful city square with animated screens and moving crowd energy",
                "action": f"{guide.name} spots the topic signal and turns toward camera with urgency",
                "emotion": "excited curiosity",
                "camera_move": "fast dolly in",
                "shot_type": "medium close-up",
                "point": topic.candidate.why_trending,
            },
            {
                "title": "What triggered it",
                "setting": "stylized digital map room with animated icons and headline cards",
                "action": f"{guide.name} points at floating cards while {sidekick.name} highlights key signals",
                "emotion": "focused explanation",
                "camera_move": "parallax orbit",
                "shot_type": "wide",
                "point": f"This signal appeared across {topic.candidate.source_count} source streams.",
            },
            {
                "title": "Why people care",
                "setting": "busy street vignette showing everyday reactions and visual symbolism for the trend",
                "action": f"{guide.name} walks through the scene while quick reaction moments play behind",
                "emotion": "confident storytelling",
                "camera_move": "tracking shot",
                "shot_type": "full body",
                "point": "The topic is strong for short-form because it is easy to visualize and explain quickly.",
            },
            {
                "title": "Why it matters",
                "setting": "clean infographic stage with icons, depth, and cinematic rim light",
                "action": f"{guide.name} delivers the grounded takeaway while {sidekick.name} settles beside the final point",
                "emotion": "credible and calm",
                "camera_move": "slow push in",
                "shot_type": "medium",
                "point": "Credibility matters, so the coverage stays close to what reputable sources are actually reporting.",
            },
            {
                "title": "What to watch next",
                "setting": "sunset skyline with floating update cards and space for a clean CTA beat",
                "action": f"{guide.name} closes with a forward-looking beat and invites viewers back",
                "emotion": "hopeful momentum",
                "camera_move": "lift up reveal",
                "shot_type": "wide hero shot",
                "point": "If this develops further, a follow-up short can focus on reactions or practical impact.",
            },
        ]
        for index in range(scene_count):
            beat = core_points[index]
            point = beat["point"]
            characters = [guide.name, sidekick.name]
            visual_prompt = (
                f"Consistent stylized 3D cartoon short film frame for {topic.candidate.title}. "
                f"Setting: {beat['setting']}. Characters: {guide.consistency_prompt} {sidekick.consistency_prompt} "
                f"Action: {beat['action']}. Emotion: {beat['emotion']}. Camera: {beat['shot_type']} with {beat['camera_move']}. "
                "Vibrant cinematic lighting, shallow depth of field, polished family-friendly animation, vertical 9:16, no captions, no watermark."
            )
            scenes.append(
                Scene(
                    index=index + 1,
                    title=str(beat["title"]),
                    visual_prompt=visual_prompt,
                    narration=f"{hook if index == 0 else point} Source context: {source_names}.",
                    caption=point,
                    duration_seconds=per_scene,
                    setting=str(beat["setting"]),
                    characters=characters,
                    shot_type=str(beat["shot_type"]),
                    camera_move=str(beat["camera_move"]),
                    emotion=str(beat["emotion"]),
                    action=str(beat["action"]),
                    transition="match cut" if index < scene_count - 1 else "hold",
                    animation_prompt=(
                        f"Animate {guide.name} in a stylized 3D cartoon world. {beat['action']}. "
                        f"Use {beat['camera_move']} and keep the same character design. End on a {('match cut' if index < scene_count - 1 else 'gentle hold')}."
                    ),
                )
            )
            storyboard.append(
                StoryboardBeat(
                    scene_index=index + 1,
                    setting=str(beat["setting"]),
                    shot_type=str(beat["shot_type"]),
                    camera_move=str(beat["camera_move"]),
                    action=str(beat["action"]),
                    emotion=str(beat["emotion"]),
                    transition="match cut" if index < scene_count - 1 else "hold",
                    animation_prompt=scenes[-1].animation_prompt,
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
            mode="cartoon_animated_short",
            visual_style="stylized 3D cartoon animation with consistent characters",
            character_sheet=character_sheet,
            storyboard=storyboard,
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
            f"Create a bold thumbnail for a stylized 3D cartoon vertical short about {topic.candidate.title}. "
            f"Style: {topic.tone}. Country focus: {topic.candidate.country}. "
            "Use expressive animated character acting, cinematic lighting, high contrast, clean composition, no text baked into the image, and no copyrighted footage."
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

    def ordered_providers(self, preferred: str, fallbacks: list[str]) -> list[BaseContentProvider]:
        ordered: list[BaseContentProvider] = []
        for name in [preferred] + fallbacks + ["template"]:
            provider = self.providers.get(name)
            if provider and provider.available() and provider not in ordered:
                ordered.append(provider)
        if self.providers["template"] not in ordered:
            ordered.append(self.providers["template"])
        return ordered
