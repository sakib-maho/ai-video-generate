from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.config import load_config
from ai_video_pipeline.pipeline import DailyVideoPipeline


class CountryFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(ROOT / "config" / "config.yaml")
        self.pipeline = DailyVideoPipeline(ROOT, self.config)
        self.logger = MagicMock()

    def test_none_means_no_filter(self) -> None:
        self.assertIsNone(self.pipeline._resolve_country_filter(None, self.logger))

    def test_empty_list_means_no_filter(self) -> None:
        self.assertIsNone(self.pipeline._resolve_country_filter([], self.logger))

    def test_case_insensitive_match(self) -> None:
        r = self.pipeline._resolve_country_filter(["Bangladesh", "JAPAN"], self.logger)
        self.assertEqual(r, {"bangladesh", "japan"})

    def test_unknown_only_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.pipeline._resolve_country_filter(["not_a_country"], self.logger)


if __name__ == "__main__":
    unittest.main()
