from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from ...utils import retry_call
from .base import BaseVoiceProvider


class OpenAITTSVoiceProvider(BaseVoiceProvider):
    name = "openai_tts"

    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip()
        self.voice_map = {
            "en": os.environ.get("OPENAI_TTS_VOICE_EN", "alloy").strip(),
            "ja": os.environ.get("OPENAI_TTS_VOICE_JA", "alloy").strip(),
            "bn": os.environ.get("OPENAI_TTS_VOICE_BN", "alloy").strip(),
        }

    def available(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, *, text: str, language: str, output_path: Path) -> Path:
        voice = self.voice_map.get(language, self.voice_map["en"])
        instruction = self._instruction_for_language(language)
        url = "https://api.openai.com/v1/audio/speech"
        body = {
            "model": self.model,
            "voice": voice,
            "input": text,
            "format": "wav",
            "instructions": instruction,
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
                with urllib.request.urlopen(request, timeout=120) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"OpenAI TTS API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"OpenAI TTS request failed: {exc}") from exc

        audio_bytes = retry_call(_do_request, attempts=3, delay_seconds=1.0, backoff=2.0)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        return output_path

    def validate_access(self) -> dict[str, str]:
        return {"provider": self.name, "status": "configured", "model": self.model}

    def _instruction_for_language(self, language: str) -> str:
        if language == "bn":
            return "Speak in natural Bangla with smooth pacing and warm, credible narration."
        if language == "ja":
            return "Speak naturally in Japanese with clean pacing and a credible short-video narration tone."
        return "Speak naturally with modern, credible short-video narration pacing."
