from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.providers.video.runway import RunwayVideoProvider


class RunwayProviderTests(unittest.TestCase):
    def test_scene_duration_maps_to_supported_values(self) -> None:
        provider = RunwayVideoProvider()
        self.assertEqual(provider._scene_duration(4.2), 5)
        self.assertEqual(provider._scene_duration(6.9), 5)
        self.assertEqual(provider._scene_duration(8.1), 10)


if __name__ == "__main__":
    unittest.main()
