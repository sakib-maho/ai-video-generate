#!/usr/bin/env python3
"""
Local image→video using Stable Video Diffusion (open weights).

- On macOS (Apple Silicon), PyTorch MPS does NOT support Conv3D, which SVD needs.
  This script therefore uses CPU on Darwin unless you pass --device cuda on a
  NVIDIA machine. Expect long runtimes on CPU (tens of minutes per clip).

- This produces short diffusion video from a still — closer to "motion" than Ken
  Burns, but NOT the same as hand-made Pixar-style 3D. For that, use Blender or a
  commercial 3D/AI service.

- Model license: see https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt

Usage:
  .venv/bin/python scripts/local_i2v_svd.py \\
    --image output/2026-04-02/japan/scene_images/scene_01.png \\
    --output /tmp/svd_clip.mp4

Requires:
  .venv/bin/pip install -r scripts/requirements-local-i2v.txt
"""
from __future__ import annotations

import argparse
import os
import platform
import sys


def _pick_device(explicit: str | None) -> str:
    if explicit:
        return explicit
    if platform.system() == "Darwin":
        # MPS cannot run SVD (Conv3D); avoid partial offload errors.
        return "cpu"
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def main() -> int:
    parser = argparse.ArgumentParser(description="Local SVD image→video clip")
    parser.add_argument("--image", required=True, help="Input image (PNG/JPG)")
    parser.add_argument("--output", required=True, help="Output .mp4 path")
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        default=None,
        help="Override auto device (default: cpu on macOS, cuda if available else cpu). MPS is not supported for SVD.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model",
        default="stabilityai/stable-video-diffusion-img2vid-xt",
        help="Hugging Face model id",
    )
    parser.add_argument("--fps", type=int, default=8, help="FPS for exported MP4")
    args = parser.parse_args()

    try:
        import torch
        from diffusers import StableVideoDiffusionPipeline
        from diffusers.utils import export_to_video, load_image
    except ImportError:
        print("Missing deps. Run: .venv/bin/pip install -r scripts/requirements-local-i2v.txt", file=sys.stderr)
        return 1

    image_path = os.path.abspath(args.image)
    output_path = os.path.abspath(args.output)
    if not os.path.isfile(image_path):
        print(f"Not found: {image_path}", file=sys.stderr)
        return 1

    device = _pick_device(args.device)

    dtype = torch.float16 if device == "cuda" else torch.float32

    print(f"Device: {device} (dtype={dtype})")
    print(f"Loading {args.model} … (first run downloads weights)")

    pipe = StableVideoDiffusionPipeline.from_pretrained(
        args.model,
        torch_dtype=dtype,
        variant="fp16" if device == "cuda" else None,
    )
    if device == "cuda":
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cpu")

    image = load_image(image_path)
    # SVD was trained near 1024×576; match aspect for best results.
    image = image.resize((1024, 576))

    generator = torch.manual_seed(args.seed)
    result = pipe(image, decode_chunk_size=8, generator=generator)
    frames = result.frames[0]

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    export_to_video(frames, output_path, fps=args.fps)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
