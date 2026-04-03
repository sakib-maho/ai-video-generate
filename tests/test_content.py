from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.content import TemplateContentProvider
from ai_video_pipeline.models import SelectedTopic, TopicCandidate, TopicSource


class ContentTests(unittest.TestCase):
    def test_template_provider_generates_cartoon_storyboard(self) -> None:
        provider = TemplateContentProvider()
        selected = SelectedTopic(
            candidate=TopicCandidate(
                title="Bangladesh festival lights go viral online",
                country="bangladesh",
                signature="bangladesh festival lights go viral online",
                sources=[TopicSource(name="Seed", source_type="seed", url="https://example.com")],
                why_trending="Bright visuals and strong public reactions are spreading quickly.",
                published_at=None,
                source_count=1,
                citations=["https://example.com"],
            ),
            language="bn",
            tone="viral but credible",
            duration_seconds=45,
        )

        script = provider.generate_script(selected)

        self.assertEqual(script.mode, "cartoon_animated_short")
        self.assertGreaterEqual(len(script.character_sheet), 1)
        self.assertEqual(len(script.storyboard), len(script.scenes))
        self.assertTrue(all(scene.animation_prompt for scene in script.scenes))


if __name__ == "__main__":
    unittest.main()
