from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .models import ScriptPackage, SelectedTopic
from .utils import ensure_dir, retry_call


class SceneImageService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1").strip()

    def available(self) -> bool:
        return bool(self.api_key)

    def generate_character_sheets(self, selected: SelectedTopic, script: ScriptPackage, output_dir: Path) -> list[Path]:
        if not self.available() or not script.character_sheet:
            return []
        sheets_dir = ensure_dir(output_dir / "character_sheets")
        generated: list[Path] = []
        funny_3d = getattr(selected, "content_angle", None) == "funny_cartoon"
        funny_style = (
            "Aesthetic: high-end theatrical 3D animation appeal (Pixar/Disney-quality character design)—rounded "
            "forms, large expressive eyes, appealing materials, warm saturated palette. "
            if funny_3d
            else ""
        )
        for index, character in enumerate(script.character_sheet, start=1):
            prompt = (
                f"Create a full-body vertical character sheet for a stylized 3D cartoon short.\n"
                f"Country context: {selected.candidate.country}\n"
                f"Topic context: {selected.candidate.title}\n"
                f"Character name: {character.name}\n"
                f"Role: {character.role}\n"
                f"Appearance: {character.appearance}\n"
                f"Wardrobe: {character.wardrobe}\n"
                f"Personality: {character.personality}\n"
                f"Consistency rule: {character.consistency_prompt}\n"
                f"{funny_style}"
                "Style: polished animated feature-film concept art, expressive face, clean turnaround-ready framing, vibrant but tasteful color design, soft cinematic lighting, no text, no watermark."
            )
            output_path = sheets_dir / f"character_{index:02d}_{character.name.lower().replace(' ', '_')}.png"
            try:
                self._generate_image(prompt=prompt, output_path=output_path)
                generated.append(output_path)
            except Exception:
                continue
        return generated

    def generate_scene_images(self, selected: SelectedTopic, script: ScriptPackage, output_dir: Path) -> list[Path]:
        if not self.available():
            return []
        images_dir = ensure_dir(output_dir / "scene_images")
        generated: list[Path] = []
        character_context = " ".join(character.consistency_prompt for character in script.character_sheet)
        funny_3d = getattr(selected, "content_angle", None) == "funny_cartoon"
        funny_scene = (
            "Shot like a frame from a premium 3D animated film: bright daylight, festive or lively setting when it fits "
            "(market, street fair, neighborhood), energetic poses implying motion—running, reaching, reacting. "
            if funny_3d
            else ""
        )
        for scene in script.scenes:
            prompt = (
                f"Create a cinematic vertical scene visual for a short-form animated video.\n"
                f"Country: {selected.candidate.country}\n"
                f"Language: {selected.language}\n"
                f"Topic: {selected.candidate.title}\n"
                f"Scene intent: {scene.visual_prompt}\n"
                f"Characters: {', '.join(scene.characters) if scene.characters else 'none specified'}\n"
                f"Character consistency: {character_context}\n"
                f"{funny_scene}"
                "Style: stylized 3D cartoon movie frame, consistent recurring characters, expressive action pose, shallow depth of field, clean composition, no captions, no watermarks, no copyrighted footage, high contrast."
            )
            output_path = images_dir / f"scene_{scene.index:02d}.png"
            try:
                self._generate_image(prompt=prompt, output_path=output_path)
                generated.append(output_path)
            except Exception:
                continue
        return generated

    def _generate_image(self, *, prompt: str, output_path: Path) -> Path:
        url = "https://api.openai.com/v1/images/generations"
        body = {
            "model": self.model,
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "medium",
            "output_format": "png",
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        def _do_request() -> bytes:
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"OpenAI image API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"OpenAI image request failed: {exc}") from exc

            data_entries = payload.get("data", [])
            if not data_entries:
                raise RuntimeError(f"OpenAI image response had no data: {payload}")
            image_b64 = data_entries[0].get("b64_json")
            if not image_b64:
                raise RuntimeError(f"OpenAI image response had no b64_json: {payload}")
            return base64.b64decode(image_b64)

        image_bytes = retry_call(_do_request, attempts=2, delay_seconds=1.0, backoff=2.0)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        return output_path
