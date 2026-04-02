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

        filters = ["drawbox=x=0:y=0:w=iw:h=ih:color=black@0.18:t=fill"]
        if font:
            filters.append(
                "drawtext="
                f"fontfile='{font}':"
                f"textfile='{escape_drawtext_path(text_file)}':"
                "fontcolor=white:fontsize=72:"
                "box=1:boxcolor=black@0.4:boxborderw=28:"
                "line_spacing=18:x=(w-text_w)/2:y=(h-text_h)/2"
            )
        self._render_variant(
            ffmpeg_bin=ffmpeg_bin,
            source_image=Path(package.source_image_path) if package.source_image_path else None,
            output_path=thumb_path,
            size="1280x720",
            fallback_color="0x7c2d12",
            filters=filters,
        )
        self._render_variant(
            ffmpeg_bin=ffmpeg_bin,
            source_image=Path(package.source_image_path) if package.source_image_path else None,
            output_path=cover_path,
            size="1080x1920",
            fallback_color="0x1e293b",
            filters=filters,
        )
        package.thumbnail_path = str(thumb_path)
        package.vertical_cover_path = str(cover_path)
        return package

    def _render_variant(
        self,
        *,
        ffmpeg_bin: str,
        source_image: Path | None,
        output_path: Path,
        size: str,
        fallback_color: str,
        filters: list[str],
    ) -> None:
        if source_image and source_image.exists():
            input_command = [
                ffmpeg_bin,
                "-y",
                "-i",
                str(source_image),
                "-vf",
                ",".join(
                    [
                        f"scale={size.split('x')[0]}:{size.split('x')[1]}:force_original_aspect_ratio=increase",
                        f"crop={size}",
                    ]
                    + filters
                ),
                "-frames:v",
                "1",
                str(output_path),
            ]
            run_command(input_command)
            return

        run_command(
            [
                ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={fallback_color}:s={size}:d=1",
                "-vf",
                ",".join(filters),
                "-frames:v",
                "1",
                str(output_path),
            ]
        )
