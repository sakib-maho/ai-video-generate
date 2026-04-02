from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.config import load_config
from ai_video_pipeline.fact_check import FactCheckService
from ai_video_pipeline.pipeline import DailyVideoPipeline
from ai_video_pipeline.storage import Storage
from ai_video_pipeline.models import FactCheckSourceAssessment, TopicCandidate, TopicSource


class DeduplicationTests(unittest.TestCase):
    def test_recently_used_signature_is_detected(self) -> None:
        db_path = ROOT / "data" / "test_pipeline.db"
        if db_path.exists():
            db_path.unlink()
        storage = Storage(db_path)
        candidate = TopicCandidate(
            title="Cherry blossom front shifts travel plans across Japan",
            country="japan",
            signature="blossom cherry front japan plans shifts travel",
            sources=[TopicSource(name="Seed", source_type="seed", url="https://example.com")],
            why_trending="Travel plans change with bloom timing.",
            published_at=None,
            source_count=1,
            trend_score=80.0,
            freshness_score=20.0,
            suitability_score=18.0,
            risk_flags=[],
            risk_score=0.0,
            fact_check_status="verified",
            citations=["https://example.com"],
        )
        storage.record_candidate(run_date="2026-04-02", candidate=candidate, selected=True, status="selected")
        self.assertTrue(storage.was_recently_used(candidate.signature, "japan", cooldown_days=7))

    def test_selection_falls_through_to_next_safe_topic_when_top_is_recent_duplicate(self) -> None:
        db_path = ROOT / "data" / "selection_test_pipeline.db"
        if db_path.exists():
            db_path.unlink()

        config = load_config(ROOT / "config" / "config.yaml")
        config.database_path = str(db_path.relative_to(ROOT))
        pipeline = DailyVideoPipeline(project_root=ROOT, config=config)

        duplicate = TopicCandidate(
            title="Bangladesh heatwave sparks school and health alerts",
            country="bangladesh",
            signature="alerts bangladesh health heatwave school sparks",
            sources=[TopicSource(name="Seed", source_type="seed", url="https://example.com/1")],
            why_trending="Strong public interest.",
            published_at=None,
            source_count=1,
            trend_score=92.0,
            freshness_score=20.0,
            suitability_score=18.0,
            risk_flags=[],
            risk_score=0.0,
            fact_check_status="verified",
            citations=["https://example.com/1"],
        )
        fresh = TopicCandidate(
            title="New Bangladesh infrastructure launch boosts travel buzz",
            country="bangladesh",
            signature="bangladesh boosts infrastructure launch travel buzz",
            sources=[TopicSource(name="Seed", source_type="seed", url="https://example.com/2")],
            why_trending="Fresh visual milestone.",
            published_at=None,
            source_count=1,
            trend_score=70.0,
            freshness_score=16.0,
            suitability_score=16.0,
            risk_flags=[],
            risk_score=0.0,
            fact_check_status="verified",
            citations=["https://example.com/2"],
        )

        pipeline.storage.record_candidate(
            run_date="2026-04-02",
            candidate=duplicate,
            selected=True,
            status="selected",
        )
        selected = pipeline._select_topic("bangladesh", [duplicate, fresh])
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.candidate.title, fresh.title)

    def test_evergreen_fallback_is_available_when_no_safe_candidate_exists(self) -> None:
        db_path = ROOT / "data" / "evergreen_test_pipeline.db"
        if db_path.exists():
            db_path.unlink()

        config = load_config(ROOT / "config" / "config.yaml")
        config.database_path = str(db_path.relative_to(ROOT))
        pipeline = DailyVideoPipeline(project_root=ROOT, config=config)
        evergreen = pipeline._build_evergreen_topic("bangladesh", logger=NoneLogger())
        self.assertIsNotNone(evergreen)
        assert evergreen is not None
        self.assertEqual(evergreen.candidate.extra["fallback"], "evergreen")

    def test_fact_check_marks_misinformation_flag_as_unsafe(self) -> None:
        candidate = TopicCandidate(
            title="Rumor says major event changed overnight",
            country="bangladesh",
            signature="event major overnight rumor says changed",
            sources=[TopicSource(name="Seed", source_type="seed", url="https://example.com/rumor")],
            why_trending="This rumor is spreading quickly and may be misinformation.",
            published_at=None,
            source_count=1,
            trend_score=60.0,
            freshness_score=10.0,
            suitability_score=10.0,
            risk_flags=["misinformation"],
            risk_score=20.0,
            fact_check_status="needs_review",
            citations=["https://example.com/rumor"],
        )
        report = FactCheckService(ROOT).evaluate(candidate)
        self.assertEqual(report.status, "unsafe")

    def test_fact_check_uses_gemini_result_when_available(self) -> None:
        candidate = TopicCandidate(
            title="Bangladesh launch draws wide public attention",
            country="bangladesh",
            signature="attention bangladesh draws launch public wide",
            sources=[TopicSource(name="Seed", source_type="seed", url="https://example.com/launch")],
            why_trending="People are discussing a visible launch event.",
            published_at=None,
            source_count=1,
            trend_score=60.0,
            freshness_score=10.0,
            suitability_score=10.0,
            risk_flags=[],
            risk_score=0.0,
            fact_check_status="needs_review",
            citations=["https://example.com/launch"],
        )

        class GeminiFactCheckStub(FactCheckService):
            def __init__(self) -> None:
                super().__init__(ROOT)
                self.gemini_api_key = "test-key"

            def _assess_source(self, url: str, claims: list[str]):  # type: ignore[override]
                return FactCheckSourceAssessment(
                    url=url,
                    domain="example.com",
                    credibility="medium",
                    corroborates=True,
                    snippet="Bangladesh launch draws wide public attention.",
                    notes="Stubbed assessment.",
                )

            def _call_gemini_json(self, prompt: str):  # type: ignore[override]
                return {
                    "status": "verified",
                    "summary": "Gemini found the framing supported.",
                    "claims": [candidate.title],
                    "verified_claims": [candidate.title],
                    "uncertain_claims": [],
                }

        report = GeminiFactCheckStub().evaluate(candidate)
        self.assertEqual(report.status, "verified")
        self.assertTrue(report.reviewer.startswith("gemini:"))


class NoneLogger:
    def warning(self, message: str) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
