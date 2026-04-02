from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseVoiceProvider(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, *, text: str, language: str, output_path: Path) -> Path:
        raise NotImplementedError
