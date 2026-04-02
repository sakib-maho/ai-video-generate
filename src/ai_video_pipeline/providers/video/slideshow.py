from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ...models import VideoRenderRequest, VideoRenderResult
from ...utils import ensure_dir, run_command, write_text
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
        scene_videos: list[Path] = []
        notes: list[str] = []

        for scene in request.script.scenes:
            video_path = work_dir / f"scene_{scene.index}.mp4"
            scene_image_path = None
            if len(request.scene_image_paths) >= scene.index:
                candidate_image = Path(request.scene_image_paths[scene.index - 1])
                if candidate_image.exists():
                    scene_image_path = candidate_image

            base_color = "0x0f172a" if scene.index % 2 else "0x1d4ed8"
            accent_color = "0xf97316" if scene.index % 2 else "0x22c55e"
            vf_parts = [
                "format=yuv420p",
                "drawbox=x='-220+mod(t*180,1500)':y=140:w=320:h=320:color=white@0.08:t=fill",
                f"drawbox=x='800-mod(t*140,1500)':y=1260:w=260:h=260:color={accent_color}@0.16:t=fill",
                "drawbox=x='140+40*sin(t*1.2)':y='860+30*cos(t*1.1)':w=760:h=5:color=white@0.22:t=fill",
                f"drawbox=x=80:y=120:w=920:h=1480:color={accent_color}@0.05:t=6",
                "drawbox=x='240+80*sin(t*0.7)':y='320+60*cos(t*0.9)':w=150:h=150:color=white@0.05:t=fill",
            ]

            video_command = [
                ffmpeg_bin,
                "-y",
            ]
            if scene_image_path:
                motion_filter = ",".join(
                    [
                        "scale=1080:1920:force_original_aspect_ratio=increase",
                        "crop=1080:1920",
                        "zoompan=z='min(zoom+0.0007,1.10)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920",
                    ]
                    + vf_parts
                )
                video_command.extend(
                    [
                        "-loop",
                        "1",
                        "-i",
                        str(scene_image_path),
                        "-t",
                        str(scene.duration_seconds),
                        "-vf",
                        motion_filter,
                    ]
                )
            else:
                notes.append(f"Scene {scene.index} rendered with abstract motion fallback.")
                video_command.extend(
                    [
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c={base_color}:s=1080x1920:d={scene.duration_seconds}",
                        "-t",
                        str(scene.duration_seconds),
                        "-vf",
                        ",".join(vf_parts),
                    ]
                )
            video_command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                    str(video_path),
                ]
            )
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

        final_command = [ffmpeg_bin, "-y", "-i", str(stitched_path)]
        if request.include_voiceover and request.voiceover_audio_path and request.voiceover_audio_path.exists():
            final_command.extend(["-i", str(request.voiceover_audio_path)])
        final_command.extend(
            [
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
        else:
            final_command.extend(["-an"])
        final_command.append(str(request.final_output_path))
        run_command(final_command)
        return VideoRenderResult(
            provider_name=self.name,
            output_path=str(request.final_output_path),
            status="rendered",
            notes=notes,
        )
