"""Hempdawg Video Resize ×32 — resize VIDEO so W/H are nearest multiples of 32."""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any, Optional

import torch
import torch.nn.functional as F

try:
    from comfy_api.latest import InputImpl, Types
except Exception:  # pragma: no cover
    InputImpl = None
    Types = None


def _round_to_32(value: int) -> int:
    return max(32, int(round(int(value) / 32.0) * 32))


def _ratio_string(width: int, height: int) -> str:
    g = math.gcd(max(1, width), max(1, height))
    rw, rh = width // g, height // g
    return f"{width}×{height} ({rw}:{rh})"


def _components_from_video(video: Any):
    get = getattr(video, "get_components", None)
    if not callable(get):
        raise ValueError("VIDEO input is not a ComfyUI Video object")
    comps = get()
    images = getattr(comps, "images", None)
    audio = getattr(comps, "audio", None)
    fr = getattr(comps, "frame_rate", None)
    alpha = getattr(comps, "alpha", None)
    if images is None:
        raise ValueError("VIDEO has no image frames")
    fps = float(fr) if fr is not None else 24.0
    return images, audio, fps, alpha


def _resize_frames(images: torch.Tensor, new_h: int, new_w: int) -> torch.Tensor:
    # images: [B, H, W, C] -> NCHW for interpolate
    x = images.detach().float().cpu()
    if x.ndim != 4:
        raise ValueError(f"Expected [B,H,W,C] frames, got {tuple(x.shape)}")
    b, h, w, c = x.shape
    if h == new_h and w == new_w:
        return x.clamp(0.0, 1.0)
    nchw = x.permute(0, 3, 1, 2).contiguous()
    nchw = F.interpolate(nchw, size=(new_h, new_w), mode="bilinear", align_corners=False)
    return nchw.permute(0, 2, 3, 1).contiguous().clamp(0.0, 1.0)


def _resize_alpha(alpha: Optional[torch.Tensor], new_h: int, new_w: int, n_frames: int) -> Optional[torch.Tensor]:
    if alpha is None:
        return None
    a = alpha.detach().float().cpu()
    if a.ndim == 4 and a.shape[-1] == 1:
        a = a[..., 0]
    if a.ndim != 3:
        # try [B,H,W,C] matte-like
        if a.ndim == 4:
            a = a.mean(dim=-1)
        else:
            return None
    if a.shape[0] != n_frames:
        n = min(a.shape[0], n_frames)
        a = a[:n]
        if a.shape[0] < n_frames:
            pad = a[-1:].expand(n_frames - a.shape[0], -1, -1)
            a = torch.cat([a, pad], dim=0)
    if a.shape[1] != new_h or a.shape[2] != new_w:
        a = F.interpolate(
            a.unsqueeze(1),
            size=(new_h, new_w),
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)
    return a.clamp(0.0, 1.0)


def _build_video(images: torch.Tensor, audio: Optional[dict], fps: float, alpha: Optional[torch.Tensor]):
    if InputImpl is None or Types is None:
        return None
    return InputImpl.VideoFromComponents(
        Types.VideoComponents(
            images=images,
            audio=audio,
            frame_rate=Fraction(fps).limit_denominator(1000),
            alpha=alpha,
        )
    )


class HempdawgVideoResize32:
    """Resize a VIDEO so width and height snap to the nearest multiple of 32."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "INT", "INT")
    RETURN_NAMES = ("video", "ratio", "width", "height")
    OUTPUT_NODE = True
    FUNCTION = "resize"
    CATEGORY = "Hempdawg/Alpha Gen"
    DESCRIPTION = (
        "Resizes the input video so width and height are each the nearest multiple of 32. "
        "Shows the new size/ratio on the node and outputs a STRING for Show Text."
    )

    def resize(self, video):
        images, audio, fps, alpha = _components_from_video(video)
        images = images.detach().float().cpu()
        if images.shape[-1] > 4:
            images = images[..., :4]

        _, src_h, src_w, _ = images.shape
        new_w = _round_to_32(src_w)
        new_h = _round_to_32(src_h)

        rgb = images[..., :3]
        resized = _resize_frames(rgb, new_h, new_w)
        alpha_out = _resize_alpha(alpha, new_h, new_w, resized.shape[0])

        # If source was RGBA and no separate alpha, keep resized alpha from channel
        if alpha_out is None and images.shape[-1] == 4:
            a = images[..., 3:4]
            a = _resize_frames(a.expand(-1, -1, -1, 3), new_h, new_w)[..., 0]
            alpha_out = a

        out_video = _build_video(resized, audio, fps, alpha_out)
        if out_video is None:
            raise RuntimeError("Could not build VIDEO output (Comfy video API unavailable).")

        info = _ratio_string(new_w, new_h)
        if new_w != src_w or new_h != src_h:
            info = f"{src_w}×{src_h} → {info}"
        else:
            info = f"{info} (already ×32)"

        return {
            "ui": {"hemp_resize32_info": [info]},
            "result": (out_video, info, int(new_w), int(new_h)),
        }


NODE_CLASS_MAPPINGS = {
    "HempdawgVideoResize32": HempdawgVideoResize32,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HempdawgVideoResize32": "Hempdawg Video Resize ×32",
}
