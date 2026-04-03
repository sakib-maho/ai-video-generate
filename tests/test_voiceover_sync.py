from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.utils import slideshow_stitched_duration_seconds


class SlideshowDurationTests(unittest.TestCase):
    def test_single_scene_is_sum(self) -> None:
        self.assertEqual(slideshow_stitched_duration_seconds([12.0]), 12.0)

    def test_multi_scene_subtracts_xfade(self) -> None:
        d = slideshow_stitched_duration_seconds([10.0, 10.0, 10.0])
        # 30 - 2*trans; trans = min(0.35, 4) = 0.35 with default env
        self.assertAlmostEqual(d, 30.0 - 2 * 0.35, places=4)


if __name__ == "__main__":
    unittest.main()
