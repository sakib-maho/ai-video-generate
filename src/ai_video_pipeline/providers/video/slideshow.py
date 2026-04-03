from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ...models import VideoRenderRequest, VideoRenderResult
from ...utils import ensure_dir, run_command, write_text
from .base import BaseVideoProvider

# Vertical 9:16 — motion is much more visible at 30fps with proper zoompan duration.
_FPS = 30
# Crossfade between scenes (reels-style; set 0 to disable)
_XFADE_SECONDS = float(os.environ.get("SLIDESHOW_XFADE_SECONDS", "0.35"))
_XFADE_TRANSITION = os.environ.get("SLIDESHOW_XFADE_TRANSITION", "slideleft").strip() or "slideleft"


class SlideshowVideoProvider(BaseVideoProvider):
    name = "slideshow"

    def available(self) -> bool:
        ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
        try:
            run_command([ffmpeg_bin, "-version"])
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
        return True

    def _scene_frame_count(self, duration_seconds: float) -> int:
        return max(3, int(round(float(duration_seconds) * _FPS)))

    def _cartoon_motion_vf(self, *, frames: int, with_image: bool) -> str:
        """Ken Burns + drift; cartoon punch via saturation, mild sharpen, vignette."""
        # zoompan `d` = number of output frames — was `1` before, which killed all motion.
        drift_x = f"iw/2-(iw/zoom/2)+48*sin(on*0.045)"
        drift_y = f"ih/2-(ih/zoom/2)+36*cos(on*0.052)"
        zoom_expr = "if(eq(on,0),1,min(zoom+0.00018,1.28))"
        if with_image:
            base = [
                "scale=1080:1920:force_original_aspect_ratio=increase",
                "crop=1080:1920",
                (
                    f"zoompan=z='{zoom_expr}':d={frames}:x='{drift_x}':y='{drift_y}'"
                    f":s=1080x1920:fps={_FPS}"
                ),
            ]
        else:
            base = [
                (
                    f"zoompan=z='{zoom_expr}':d={frames}:x='{drift_x}':y='{drift_y}'"
                    f":s=1080x1920:fps={_FPS}"
                ),
            ]
        # "Reel" look: saturated, crisp edges, soft vignette; floating shapes keep energy on fallbacks.
        polish = [
            "format=yuv420p",
            "eq=saturation=1.22:contrast=1.08:brightness=0.03",
            "unsharp=5:5:0.8:3:3:0.0",
            "vignette=angle=PI/4:eval=frame:dither=1",
        ]
        return ",".join(base + polish)

    def _abstract_overlay_vf(self, scene_index: int) -> str:
        base_color = "0x0f172a" if scene_index % 2 else "0x1d4ed8"
        accent_color = "0xf97316" if scene_index % 2 else "0x22c55e"
        return ",".join(
            [
                f"drawbox=x='-260+mod(t*210,1600)':y=120:w=360:h=360:color=white@0.08:t=fill",
                f"drawbox=x='840-mod(t*160,1550)':y=1220:w=300:h=300:color={accent_color}@0.16:t=fill",
                "drawbox=x='120+55*sin(t*1.15)':y='900+25*cos(t*1.05)':w=820:h=6:color=white@0.16:t=fill",
                f"drawbox=x=58:y=100:w=964:h=1590:color={accent_color}@0.05:t=8",
                "drawbox=x='210+95*sin(t*0.55)':y='280+65*cos(t*0.75)':w=190:h=190:color=white@0.05:t=fill",
            ]
        )

    def _build_xfade_complex(self, n: int, durations: list[float], trans: float) -> str:
        """Chain xfade filters: [0:v][1:v]...[vout]."""
        merged = float(durations[0])
        parts: list[str] = []
        cur = "0:v"
        for i in range(1, n):
            offset = merged - trans
            out = "vout" if i == n - 1 else f"v{i}"
            parts.append(
                f"[{cur}][{i}:v]xfade=transition={_XFADE_TRANSITION}:duration={trans:.6f}:offset={offset:.6f}[{out}]"
            )
            merged = merged + float(durations[i]) - trans
            cur = out
        return ";".join(parts)

    def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
        work_dir = ensure_dir(request.output_dir / "_render")
        scene_videos: list[Path] = []
        scene_durations: list[float] = []
        notes: list[str] = []
        character_sheet_images = [Path(path) for path in request.character_sheet_image_paths if Path(path).exists()]

        for scene in request.script.scenes:
            video_path = work_dir / f"scene_{scene.index}.mp4"
            frames = self._scene_frame_count(scene.duration_seconds)
            scene_image_path = None
            if len(request.scene_image_paths) >= scene.index:
                candidate_image = Path(request.scene_image_paths[scene.index - 1])
                if candidate_image.exists():
                    scene_image_path = candidate_image
            fallback_character_image = None
            if not scene_image_path and character_sheet_images:
                fallback_character_image = character_sheet_images[(scene.index - 1) % len(character_sheet_images)]

            base_color = "0x0f172a" if scene.index % 2 else "0x1d4ed8"
            vf_parts = self._abstract_overlay_vf(scene.index)

            video_command = [
                ffmpeg_bin,
                "-y",
            ]
            if scene_image_path:
                motion_filter = ",".join(
                    [
                        self._cartoon_motion_vf(frames=frames, with_image=True),
                        vf_parts,
                    ]
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
            elif fallback_character_image:
                notes.append(f"Scene {scene.index} rendered from character-sheet fallback.")
                drift_x = f"iw/2-(iw/zoom/2)+48*sin(on*0.045)"
                drift_y = f"ih/2-(ih/zoom/2)+36*cos(on*0.052)"
                zoom_expr = "if(eq(on,0),1,min(zoom+0.00018,1.28))"
                motion_filter = ",".join(
                    [
                        "scale=1080:1920:force_original_aspect_ratio=decrease",
                        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x101828",
                        (
                            f"zoompan=z='{zoom_expr}':d={frames}:x='{drift_x}':y='{drift_y}'"
                            f":s=1080x1920:fps={_FPS}"
                        ),
                        "format=yuv420p",
                        "eq=saturation=1.22:contrast=1.08:brightness=0.03",
                        "unsharp=5:5:0.8:3:3:0.0",
                        "vignette=angle=PI/4:eval=frame:dither=1",
                        vf_parts,
                    ]
                )
                video_command.extend(
                    [
                        "-loop",
                        "1",
                        "-i",
                        str(fallback_character_image),
                        "-t",
                        str(scene.duration_seconds),
                        "-vf",
                        motion_filter,
                    ]
                )
            else:
                notes.append(f"Scene {scene.index} rendered with abstract motion fallback.")
                motion_filter = ",".join(
                    [
                        self._cartoon_motion_vf(frames=frames, with_image=False),
                        vf_parts,
                    ]
                )
                video_command.extend(
                    [
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c={base_color}:s=1080x1920:d={scene.duration_seconds}",
                        "-t",
                        str(scene.duration_seconds),
                        "-vf",
                        motion_filter,
                    ]
                )
            video_command.extend(
                [
                    "-r",
                    str(_FPS),
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
            scene_durations.append(float(scene.duration_seconds))

        n = len(scene_videos)
        trans = min(_XFADE_SECONDS, max(0.0, min(scene_durations) * 0.4)) if n else 0.0
        if n > 1 and trans > 0.05 and _XFADE_SECONDS > 0:
            stitched_path = work_dir / "stitched.mp4"
            inputs: list[str] = []
            for p in scene_videos:
                inputs.extend(["-i", str(p)])
            fc = self._build_xfade_complex(n, scene_durations, trans)
            xfade_cmd = (
                [ffmpeg_bin, "-y"]
                + inputs
                + [
                    "-filter_complex",
                    fc,
                    "-map",
                    "[vout]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                    str(stitched_path),
                ]
            )
            run_command(xfade_cmd)
            notes.append(
                f"Scene transitions: {_XFADE_TRANSITION} crossfade ({trans:.2f}s). "
                "Override with SLIDESHOW_XFADE_SECONDS / SLIDESHOW_XFADE_TRANSITION."
            )
        else:
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
