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

    def generate_scene_images(self, selected: SelectedTopic, script: ScriptPackage, output_dir: Path) -> list[Path]:
        if not self.available():
            return []
        images_dir = ensure_dir(output_dir / "scene_images")
        generated: list[Path] = []
        for scene in script.scenes:
            prompt = (
                f"Create a cinematic vertical scene visual for a short-form video.\n"
                f"Country: {selected.candidate.country}\n"
                f"Language: {selected.language}\n"
                f"Topic: {selected.candidate.title}\n"
                f"Scene intent: {scene.visual_prompt}\n"
                "Style: modern editorial motion-graphics-ready still frame, clean composition, no captions, no watermarks, no copyrighted footage, high contrast."
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
