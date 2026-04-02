from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_video_pipeline.config import load_config
from ai_video_pipeline.pipeline import DailyVideoPipeline
from ai_video_pipeline.scheduler import run_scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automated AI short-video pipeline")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config YAML/JSON")
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately")
    parser.add_argument("--sample-run", action="store_true", help="Use bundled seed topics instead of live fetch")
    parser.add_argument("--review-mode", action="store_true", help="Override mode to review")
    parser.add_argument("--check-providers", action="store_true", help="Validate configured provider access and exit")
    parser.add_argument(
        "--approve-date",
        help="Approve and render a pending review packet for the given run date (YYYY-MM-DD)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(Path(args.config))
    if args.review_mode:
        config.mode = "review"

    pipeline = DailyVideoPipeline(project_root=ROOT, config=config)

    if args.check_providers:
        pipeline.check_providers()
        return 0

    if args.approve_date:
        pipeline.approve_and_render(args.approve_date)
        return 0

    if args.run_now:
        pipeline.run(use_sample_data=args.sample_run)
        return 0

    run_scheduler(pipeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
