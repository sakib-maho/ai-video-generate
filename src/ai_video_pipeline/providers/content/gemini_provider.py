from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ...models import CharacterDesign, Scene, ScriptPackage, SelectedTopic, SeoPackage, StoryboardBeat, ThumbnailPackage
from ...utils import (
    funny_cartoon_angle_directive,
    retry_call,
    scene_variety_directive,
    script_language_directive,
    seo_language_directive,
    summary_only_script_directive,
)
from .base import BaseContentProvider


class GeminiContentProvider(BaseContentProvider):
    name = "gemini"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
        self.api_version = os.environ.get("GEMINI_API_VERSION", "v1beta").strip()

    def available(self) -> bool:
        return bool(self.api_key)

    def generate_script(self, topic: SelectedTopic) -> ScriptPackage:
        prompt = (
            "Return strict JSON only.\n"
            "Create a credible short-form vertical video package designed as a stylized 3D cartoon animated short.\n"
            f"Country: {topic.candidate.country}\n"
            f"Language: {topic.language}\n"
            f"Tone: {topic.tone}\n"
            f"Duration seconds: {topic.duration_seconds}\n"
            f"Topic headline: {topic.candidate.title}\n"
            f"Angle (for writing only—do not recite as citations or name outlets): {topic.candidate.why_trending}\n"
            f"{summary_only_script_directive()}"
            "Avoid presenting uncertain claims as confirmed facts.\n"
            "Create one recurring host character and optionally one sidekick/motif for consistent animation across scenes.\n"
            "Every scene must be visually specific, animated, and suitable for image-to-video generation.\n"
            f"{scene_variety_directive(topic.duration_seconds)}"
            f"{script_language_directive(topic.language)}"
            f"{funny_cartoon_angle_directive() if getattr(topic, 'content_angle', None) == 'funny_cartoon' else ''}"
            "JSON schema:\n"
            "{"
            '"hook":"string",'
            '"summary":"string",'
            '"mode":"cartoon_animated_short",'
            '"visual_style":"string",'
            '"character_sheet":[{"name":"string","role":"string","appearance":"string","wardrobe":"string","personality":"string","consistency_prompt":"string"}],'
            '"storyboard":[{"scene_index":1,"setting":"string","shot_type":"string","camera_move":"string","action":"string","emotion":"string","transition":"string","animation_prompt":"string"}],'
            '"scenes":[{"index":1,"title":"string","visual_prompt":"string","narration":"string","caption":"string","duration_seconds":10.0,"setting":"string","characters":["string"],"shot_type":"string","camera_move":"string","emotion":"string","action":"string","transition":"string","animation_prompt":"string"}],'
            '"voiceover_script":"string",'
            '"captions":["string"],'
            '"cta":"string"'
            "}"
        )
        payload = self._generate_json(prompt)
        scenes = [Scene(**scene) for scene in payload["scenes"]]
        characters = [CharacterDesign(**item) for item in payload.get("character_sheet", [])]
        storyboard = [StoryboardBeat(**item) for item in payload.get("storyboard", [])]
        return ScriptPackage(
            hook=payload["hook"],
            summary=payload["summary"],
            scenes=scenes,
            voiceover_script=payload["voiceover_script"],
            captions=payload["captions"],
            cta=payload["cta"],
            language=topic.language,
            tone=topic.tone,
            mode=payload.get("mode", "cartoon_animated_short"),
            visual_style=payload.get("visual_style", "stylized 3D cartoon animation"),
            character_sheet=characters,
            storyboard=storyboard,
        )

    def generate_seo(self, topic: SelectedTopic, script: ScriptPackage) -> SeoPackage:
        prompt = (
            "Return strict JSON only.\n"
            "Create SEO metadata for a short-form vertical video.\n"
            f"Country: {topic.candidate.country}\n"
            f"Language: {topic.language}\n"
            f"Tone: {topic.tone}\n"
            f"Topic: {topic.candidate.title}\n"
            f"Script summary: {script.summary}\n"
            f"{seo_language_directive(topic.language)}"
            "JSON schema:\n"
            "{"
            '"title_options":["string","string","string","string","string"],'
            '"final_title":"string",'
            '"description":"string",'
            '"hashtags":["string"],'
            '"keywords":["string"],'
            '"upload_filename":"string",'
            '"youtube_tags":["string"],'
            '"tiktok_tags":["string"],'
            '"instagram_tags":["string"]'
            "}"
        )
        payload = self._generate_json(prompt)
        return SeoPackage(
            title_options=payload["title_options"][:5],
            final_title=payload["final_title"],
            description=payload["description"],
            hashtags=payload["hashtags"][:20],
            keywords=payload["keywords"],
            upload_filename=payload["upload_filename"],
            youtube_tags=payload["youtube_tags"],
            tiktok_tags=payload["tiktok_tags"],
            instagram_tags=payload["instagram_tags"],
        )

    def generate_thumbnail(self, topic: SelectedTopic, script: ScriptPackage, seo: SeoPackage) -> ThumbnailPackage:
        prompt = (
            "Return strict JSON only.\n"
            "Create thumbnail planning metadata for a short-form stylized 3D cartoon animated trend video.\n"
            f"Country: {topic.candidate.country}\n"
            f"Language: {topic.language}\n"
            f"Topic: {topic.candidate.title}\n"
            f"Recommended title: {seo.final_title}\n"
            f"Hook: {script.hook}\n"
            f"Visual style: {script.visual_style}\n"
            "JSON schema:\n"
            "{"
            '"text_options":["string","string","string","string"],'
            '"selected_text":"string",'
            '"prompt":"string",'
            '"style":"string"'
            "}"
        )
        payload = self._generate_json(prompt)
        return ThumbnailPackage(
            text_options=payload["text_options"][:4],
            selected_text=payload["selected_text"],
            prompt=payload["prompt"],
            style=payload["style"],
        )

    def _generate_json(self, prompt: str) -> dict[str, Any]:
        data = self._call_generate_content(prompt)
        text = self._extract_text(data)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = self._extract_json_block(text)
            return json.loads(cleaned)

    def _call_generate_content(self, prompt: str) -> dict[str, Any]:
        url = (
            f"https://generativelanguage.googleapis.com/{self.api_version}/models/"
            f"{self.model}:generateContent"
        )
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        def _do_request() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Gemini API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Gemini API request failed: {exc}") from exc

        return retry_call(_do_request, attempts=3, delay_seconds=1.0, backoff=2.0)

    def validate_access(self) -> dict[str, str]:
        payload = self._call_generate_content("Return strict JSON only: {\"status\":\"ok\"}")
        text = self._extract_text(payload)
        parsed = json.loads(self._extract_json_block(text) if "{" in text else text)
        return {"provider": self.name, "status": parsed.get("status", "ok"), "model": self.model}

    def _extract_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {payload}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text_chunks = [part.get("text", "") for part in parts if part.get("text")]
        if not text_chunks:
            raise RuntimeError(f"Gemini returned no text parts: {payload}")
        return "".join(text_chunks).strip()

    def _extract_json_block(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(f"Gemini response was not parseable JSON: {text}")
        return text[start : end + 1]
