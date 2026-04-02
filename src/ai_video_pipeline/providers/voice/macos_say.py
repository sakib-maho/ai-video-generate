from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path

from ...utils import retry_call, run_command
from .base import BaseVoiceProvider


class MacOSSayVoiceProvider(BaseVoiceProvider):
    name = "macos_say"

    def available(self) -> bool:
        try:
            run_command(["/usr/bin/say", "-v", "?"])
        except Exception:
            return False
        return True

    def synthesize(self, *, text: str, language: str, output_path: Path) -> Path:
        voice = self._voice_for_language(language)
        prepared = self._prepare_text(text, language)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def _do_say() -> str:
            result = subprocess.run(
                ["/usr/bin/say", "-v", voice, "-o", str(output_path), prepared],
                check=True,
                text=True,
                capture_output=True,
            )
            return result.stdout

        retry_call(_do_say, attempts=2, delay_seconds=0.2, backoff=2.0)
        return output_path

    def validate_access(self) -> dict[str, str]:
        return {"provider": self.name, "status": "available", "voice": "system"}

    def _voice_for_language(self, language: str) -> str:
        if language == "ja":
            return "Eddy (Japanese (Japan))"
        if language == "bn":
            return "Aman"
        return "Eddy (English (US))"

    def _prepare_text(self, text: str, language: str) -> str:
        if language == "bn":
            # macOS say has no Bengali voice; keep an intelligible fallback by stripping unsupported script.
            ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
            cleaned = " ".join(ascii_text.replace("।", ". ").split())
            return cleaned or "Bangladesh daily video update."
        return " ".join(text.split())
