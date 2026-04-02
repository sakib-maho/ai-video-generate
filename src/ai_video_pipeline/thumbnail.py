from __future__ import annotations

import os
from pathlib import Path

from .models import ThumbnailPackage
from .utils import ensure_dir
from .utils import discover_font, escape_drawtext_path, run_command, write_text


class ThumbnailRenderer:
    def render(self, package: ThumbnailPackage, output_dir: Path, language: str) -> ThumbnailPackage:
        ffmpeg_bin = os.environ.get("FFMPEG_BIN", "ffmpeg")
        font = discover_font(language)
        thumb_path = output_dir / "thumbnail.png"
        cover_path = output_dir / "vertical_cover.png"
        work_dir = ensure_dir(output_dir / "_render")
        text_file = work_dir / "thumbnail_text.txt"
        write_text(text_file, package.selected_text)

        filters = ["drawbox=x=0:y=0:w=iw:h=ih:color=black@0.15:t=fill"]
        if font:
            filters.append(
                "drawtext="
                f"fontfile='{font}':"
                f"textfile='{escape_drawtext_path(text_file)}':"
                "fontcolor=white:fontsize=72:"
                "box=1:boxcolor=black@0.4:boxborderw=28:"
                "line_spacing=18:x=(w-text_w)/2:y=(h-text_h)/2"
            )
        run_command(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x7c2d12:s=1280x720:d=1",
                "-vf",
                ",".join(filters),
                "-frames:v",
                "1",
                str(thumb_path),
            ]
        )
        run_command(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x1e293b:s=1080x1920:d=1",
                "-vf",
                ",".join(filters),
                "-frames:v",
                "1",
                str(cover_path),
            ]
        )
        package.thumbnail_path = str(thumb_path)
        package.vertical_cover_path = str(cover_path)
        return package
