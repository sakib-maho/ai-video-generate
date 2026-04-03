from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import wave
from pathlib import Path

from ...utils import retry_call, split_sentences
from .base import BaseVoiceProvider


class GeminiTTSVoiceProvider(BaseVoiceProvider):
    name = "gemini_tts"

    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.api_version = os.environ.get("GEMINI_API_VERSION", "v1beta").strip()
        self.model = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
        self.voice_map = {
            "en": os.environ.get("GEMINI_TTS_VOICE_EN", "Kore").strip(),
            "ja": os.environ.get("GEMINI_TTS_VOICE_JA", "Kore").strip(),
            "bn": os.environ.get("GEMINI_TTS_VOICE_BN", "Sulafat").strip(),
            "hi": os.environ.get("GEMINI_TTS_VOICE_HI", "Kore").strip(),
        }
        self.style_map = {
            "en": os.environ.get(
                "GEMINI_TTS_STYLE_EN",
                "Speak naturally in clear, modern short-form video narration style.",
            ).strip(),
            "ja": os.environ.get(
                "GEMINI_TTS_STYLE_JA",
                "自然で信頼感のある短尺動画ナレーションとして読み上げてください。",
            ).strip(),
            "bn": os.environ.get(
                "GEMINI_TTS_STYLE_BN",
                "প্রাকৃতিক বাংলাদেশি বাংলা উচ্চারণে, উষ্ণ কিন্তু বিশ্বাসযোগ্য নিউজ-স্টাইল ভয়েসে পড়ুন।",
            ).strip(),
            "hi": os.environ.get(
                "GEMINI_TTS_STYLE_HI",
                "स्पष्ट, प्राकृतिक हिंदी उच्चारण में, भरोसेमंद न्यूज़-स्टाइल आवाज़ में पढ़ें।",
            ).strip(),
        }

    def available(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, *, text: str, language: str, output_path: Path) -> Path:
        voice_name = self.voice_map.get(language, self.voice_map["en"])
        style = self.style_map.get(language, self.style_map["en"])
        chunks = split_sentences(text, max_chars=220 if language in {"bn", "hi"} else 260) or [text.strip()]
        pcm_chunks: list[bytes] = []
        for chunk in chunks:
            prompt = (
                f"{style}\n"
                "Read the following script exactly as narration. Keep pacing natural, avoid robotic cadence, and preserve the script language.\n\n"
                f"{chunk}"
            )
            payload = self._call_tts(prompt=prompt, voice_name=voice_name)
            inline_data = payload["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm_chunks.append(base64.b64decode(inline_data["data"]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"".join(pcm_chunks))
        return output_path

    def _call_tts(self, *, prompt: str, voice_name: str) -> dict:
        url = (
            f"https://generativelanguage.googleapis.com/{self.api_version}/models/"
            f"{self.model}:generateContent"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name,
                        }
                    }
                },
            },
            "model": self.model,
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
        def _do_request() -> dict:
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Gemini TTS API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Gemini TTS request failed: {exc}") from exc

        return retry_call(_do_request, attempts=3, delay_seconds=1.0, backoff=2.0)

    def validate_access(self) -> dict[str, str]:
        payload = self._call_tts(prompt="বলুন: হ্যালো।", voice_name=self.voice_map["bn"])
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        if not parts or "inlineData" not in parts[0]:
            raise RuntimeError(f"Gemini TTS returned no audio payload: {payload}")
        return {"provider": self.name, "status": "ok", "model": self.model}
