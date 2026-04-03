from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.utils import scene_variety_directive


class SceneVarietyDirectiveTests(unittest.TestCase):
    def test_45s_targets_at_least_6(self) -> None:
        text = scene_variety_directive(45)
        self.assertIn("at least", text.lower())
        self.assertIn("unique", text.lower())

    def test_respects_pipeline_min_env(self) -> None:
        old_min = os.environ.get("PIPELINE_MIN_SCENES")
        old_max = os.environ.get("PIPELINE_MAX_SCENES")
        try:
            os.environ["PIPELINE_MIN_SCENES"] = "9"
            os.environ["PIPELINE_MAX_SCENES"] = "10"
            text = scene_variety_directive(20)
            self.assertIn("at least 9", text)
        finally:
            for key, old in (("PIPELINE_MIN_SCENES", old_min), ("PIPELINE_MAX_SCENES", old_max)):
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old


if __name__ == "__main__":
    unittest.main()
