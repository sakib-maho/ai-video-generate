from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.models import Scene
from ai_video_pipeline.providers.video.runway import RunwayVideoProvider


class RunwayProviderTests(unittest.TestCase):
    def test_scene_duration_maps_to_supported_values(self) -> None:
        provider = RunwayVideoProvider()
        self.assertEqual(provider._scene_duration(4.2), 5)
        self.assertEqual(provider._scene_duration(6.9), 5)
        self.assertEqual(provider._scene_duration(8.1), 10)

    def test_runway_prompt_funny_cartoon_adds_motion_prefix(self) -> None:
        provider = RunwayVideoProvider()
        scene = Scene(
            index=1,
            title="x",
            visual_prompt="VIS",
            narration="N",
            caption="",
            duration_seconds=5.0,
            animation_prompt="A hero trips comically over a banana peel.",
        )
        request = SimpleNamespace(topic=SimpleNamespace(content_angle="funny_cartoon"))
        out = provider._runway_prompt_text(request, scene)
        self.assertTrue(out.startswith("Premium 3D CGI animated short"))
        self.assertIn("banana", out)
        self.assertLessEqual(len(out), 1000)

    def test_runway_prompt_without_funny_cartoon_is_scene_text_only(self) -> None:
        provider = RunwayVideoProvider()
        scene = Scene(
            index=1,
            title="x",
            visual_prompt="",
            narration="Plain narration only.",
            caption="",
            duration_seconds=5.0,
            animation_prompt="",
        )
        request = SimpleNamespace(topic=SimpleNamespace(content_angle=None))
        out = provider._runway_prompt_text(request, scene)
        self.assertEqual(out, "Plain narration only.")


if __name__ == "__main__":
    unittest.main()
