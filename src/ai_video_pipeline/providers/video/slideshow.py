from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ...models import VideoRenderRequest, VideoRenderResult
from ...utils import discover_font, ensure_dir, escape_drawtext_path, run_command, write_text
from .base import BaseVideoProvider


class SlideshowVideoProvider(BaseVideoProvider):
    name = "slideshow"

    def available(self) -> bool:
        ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
        try:
            run_command([ffmpeg_bin, "-version"])
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
        return True

    def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
        work_dir = ensure_dir(request.output_dir / "_render")
        font = discover_font(request.topic.language)
        scene_videos: list[Path] = []
        notes: list[str] = []

        for scene in request.script.scenes:
            scene_text_file = work_dir / f"scene_{scene.index}.txt"
            image_path = work_dir / f"scene_{scene.index}.png"
            video_path = work_dir / f"scene_{scene.index}.mp4"
            scene_text = f"{scene.title}\n\n{scene.caption}\n\nSource: {request.topic.candidate.sources[0].name}"
            write_text(scene_text_file, scene_text)

            color = "0x0f172a" if scene.index % 2 else "0x1d4ed8"
            vf_parts = []
            if font:
                vf_parts.append(
                    "drawtext="
                    f"fontfile='{font}':"
                    f"textfile='{escape_drawtext_path(scene_text_file)}':"
                    "fontcolor=white:fontsize=54:"
                    "box=1:boxcolor=black@0.45:boxborderw=24:"
                    "line_spacing=18:"
                    "x=(w-text_w)/2:y=(h-text_h)/2"
                )
            else:
                notes.append("No suitable font found; slide text image rendered without drawtext.")

            image_command = [
                ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=1080x1920:d=1",
            ]
            if vf_parts:
                image_command.extend(["-vf", ",".join(vf_parts)])
            image_command.extend(["-frames:v", "1", str(image_path)])
            run_command(image_command)

            video_command = [
                ffmpeg_bin,
                "-y",
                "-loop",
                "1",
                "-i",
                str(image_path),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t",
                str(scene.duration_seconds),
                "-vf",
                "zoompan=z='min(zoom+0.0008,1.08)':d=1:s=1080x1920,format=yuv420p",
                "-shortest",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                str(video_path),
            ]
            run_command(video_command)
            scene_videos.append(video_path)

        concat_file = work_dir / "concat.txt"
        write_text(concat_file, "\n".join(f"file '{path.name}'" for path in scene_videos))

        stitched_path = work_dir / "stitched.mp4"
        run_command(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(stitched_path),
            ],
            cwd=work_dir,
        )

        subtitle_filter = f"subtitles='{escape_drawtext_path(request.subtitles_path)}'"
        final_command = [ffmpeg_bin, "-y", "-i", str(stitched_path)]
        if request.include_voiceover and request.voiceover_audio_path and request.voiceover_audio_path.exists():
            final_command.extend(["-i", str(request.voiceover_audio_path)])
        final_command.extend(
            [
                "-vf",
                subtitle_filter,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
            ]
        )
        if request.include_voiceover and request.voiceover_audio_path and request.voiceover_audio_path.exists():
            final_command.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        final_command.append(str(request.final_output_path))
        run_command(final_command)
        return VideoRenderResult(
            provider_name=self.name,
            output_path=str(request.final_output_path),
            status="rendered",
            notes=notes,
        )
