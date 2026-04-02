from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.models import TopicCandidate, TopicSource
from ai_video_pipeline.trends import aggregate_and_score
from ai_video_pipeline.logging_utils import PipelineLogger


class ScoringTests(unittest.TestCase):
    def test_fresher_multi_source_topic_ranks_higher(self) -> None:
        now = datetime.now().astimezone()
        logger = PipelineLogger(ROOT / "output" / "_test_logs")
        fresh = TopicCandidate(
            title="Japan robotics showcase reveals compact home assistant concept",
            country="japan",
            signature="assistant compact concept home reveals robotics showcase",
            sources=[
                TopicSource(name="Feed A", source_type="news", url="https://a.example"),
                TopicSource(name="Feed B", source_type="social", url="https://b.example"),
            ],
            why_trending="Visual tech demo with strong discussion and high short-form appeal.",
            published_at=now - timedelta(hours=2),
            source_count=2,
            citations=["https://a.example", "https://b.example"],
        )
        older = TopicCandidate(
            title="Routine policy meeting update",
            country="japan",
            signature="meeting policy routine update",
            sources=[TopicSource(name="Feed C", source_type="news", url="https://c.example")],
            why_trending="Dry coverage with limited visual payoff.",
            published_at=now - timedelta(hours=60),
            source_count=1,
            citations=["https://c.example"],
        )
        ranked = aggregate_and_score([older, fresh], logger=logger)
        self.assertEqual(ranked[0].title, fresh.title)
        self.assertGreater(ranked[0].trend_score, ranked[1].trend_score)


if __name__ == "__main__":
    unittest.main()
