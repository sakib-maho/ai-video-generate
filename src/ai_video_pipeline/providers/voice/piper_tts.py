from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ...utils import retry_call
from .base import BaseVoiceProvider


class PiperTTSVoiceProvider(BaseVoiceProvider):
    name = "piper_tts"

    def __init__(self) -> None:
        self.python_bin = os.environ.get("PIPER_PYTHON", ".venv/bin/python").strip()
        self.model_map = {
            "en": os.environ.get("PIPER_MODEL_EN", "").strip(),
            "ja": os.environ.get("PIPER_MODEL_JA", "").strip(),
            "bn": os.environ.get("PIPER_MODEL_BN", "").strip(),
            "hi": os.environ.get("PIPER_MODEL_HI", "").strip(),
        }

    def available(self) -> bool:
        python_path = Path(self.python_bin)
        if not python_path.exists():
            return False
        try:
            subprocess.run(
                [str(python_path), "-c", "from piper.voice import PiperVoice; print('ok')"],
                check=True,
                text=True,
                capture_output=True,
            )
        except Exception:
            return False
        return any(self.model_map.values())

    def synthesize(self, *, text: str, language: str, output_path: Path) -> Path:
        model_path = self.model_map.get(language) or self.model_map.get("en") or ""
        if not model_path:
            raise RuntimeError(f"No Piper model configured for language '{language}'.")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        script = """
from pathlib import Path
import wave
from piper.voice import PiperVoice

model_path = Path(__import__('os').environ['PIPER_MODEL_PATH'])
output_path = Path(__import__('os').environ['PIPER_OUTPUT_PATH'])
text = __import__('os').environ['PIPER_TEXT']
voice = PiperVoice.load(model_path)
with wave.open(str(output_path), 'wb') as wav_file:
    voice.synthesize_wav(text, wav_file)
print(output_path.stat().st_size)
"""

        env = os.environ.copy()
        env["PIPER_MODEL_PATH"] = model_path
        env["PIPER_OUTPUT_PATH"] = str(output_path)
        env["PIPER_TEXT"] = text

        def _do_run() -> str:
            proc = subprocess.run(
                [self.python_bin, "-c", script],
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
            return proc.stdout

        retry_call(_do_run, attempts=2, delay_seconds=0.5, backoff=2.0)
        if not output_path.exists() or output_path.stat().st_size <= 1024:
            raise RuntimeError("Piper did not produce usable audio output.")
        return output_path

    def validate_access(self) -> dict[str, str]:
        if not self.available():
            raise RuntimeError("Piper Python environment or model configuration not available.")
        configured = [lang for lang, path in self.model_map.items() if path]
        return {"provider": self.name, "status": "available", "languages": ",".join(configured)}
