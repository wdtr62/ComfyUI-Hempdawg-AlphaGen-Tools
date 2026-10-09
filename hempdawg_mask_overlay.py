"""Hempdawg Mask Overlay Player — apply alpha matte to original video, preview + VIDEO out."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from fractions import Fraction
from typing import Any, Optional

import numpy as np
import torch
import torch.nn.functional as F
import folder_paths

try:
    from comfy_api.latest import InputImpl, Types
except Exception:  # pragma: no cover
    InputImpl = None
    Types = None


def _ffmpeg_exe() -> str:
    env = os.environ.get("VHS_FORCE_FFMPEG_PATH") or os.environ.get("HEMP_FFMPEG_PATH")
    if env and os.path.isfile(env):
        return env
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    which = shutil.which("ffmpeg")
    if which:
        return which
    raise FileNotFoundError(
        "ffmpeg not found. Install system ffmpeg or imageio-ffmpeg in the ComfyUI venv."
    )


def _components_from_video(video: Any):
    if video is None:
        raise ValueError("VIDEO input is required")
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


def _mask_from_frames(mask_images: torch.Tensor, target_h: int, target_w: int, n_frames: int) -> torch.Tensor:
    """Return alpha mask [B, H, W] in 0..1 from grayscale/RGB mask frames."""
    m = mask_images.detach().float().cpu()
    if m.ndim != 4:
        raise ValueError(f"Mask frames must be IMAGE-like [B,H,W,C], got {tuple(m.shape)}")
    if m.shape[-1] == 1:
        alpha = m[..., 0]
    else:
        alpha = m[..., :3].mean(dim=-1)
    alpha = alpha.clamp(0.0, 1.0)

    if alpha.shape[0] != n_frames:
        if alpha.shape[0] == 1:
            alpha = alpha.expand(n_frames, -1, -1).contiguous()
        else:
            n = min(alpha.shape[0], n_frames)
            alpha = alpha[:n]
            if alpha.shape[0] < n_frames:
                pad = alpha[-1:].expand(n_frames - alpha.shape[0], -1, -1)
                alpha = torch.cat([alpha, pad], dim=0)

    if alpha.shape[1] != target_h or alpha.shape[2] != target_w:
        alpha = F.interpolate(
            alpha.unsqueeze(1),
            size=(target_h, target_w),
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)

    return alpha.clamp(0.0, 1.0)


def _checkerboard(h: int, w: int, cell: int = 16) -> torch.Tensor:
    yy = torch.arange(h).unsqueeze(1)
    xx = torch.arange(w).unsqueeze(0)
    board = ((yy // cell) + (xx // cell)) % 2
    color = torch.where(board.bool(), torch.tensor(0.75), torch.tensor(0.35)).float()
    return color.unsqueeze(-1).expand(h, w, 3).contiguous()


def _composite_preview(rgb: torch.Tensor, alpha: torch.Tensor, cell: int = 16) -> torch.Tensor:
    b, h, w, _ = rgb.shape
    bg = _checkerboard(h, w, cell=cell).unsqueeze(0).expand(b, -1, -1, -1)
    a = alpha.unsqueeze(-1)
    return (rgb * a + bg * (1.0 - a)).clamp(0.0, 1.0)


def _audio_to_aac(audio: dict, path: str) -> Optional[str]:
    if not audio or not isinstance(audio, dict):
        return None
    waveform = audio.get("waveform")
    sr = int(audio.get("sample_rate") or 0)
    if waveform is None or sr <= 0:
        return None
    if isinstance(waveform, torch.Tensor):
        wav = waveform.detach().cpu()
    else:
        wav = torch.as_tensor(waveform)
    if wav.ndim == 3:
        wav = wav[0]
    if wav.ndim != 2:
        return None
    channels = int(wav.shape[0])
    pcm = wav.transpose(0, 1).contiguous().numpy().astype(np.float32, copy=False)
    raw_path = path + ".f32"
    pcm.tofile(raw_path)
    cmd = [
        _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "f32le", "-ar", str(sr), "-ac", str(channels),
        "-i", raw_path,
        "-c:a", "aac", "-b:a", "192k",
        path,
    ]
    try:
        subprocess.run(cmd, check=True)
    finally:
        try:
            os.remove(raw_path)
        except OSError:
            pass
    return path if os.path.isfile(path) else None


def _write_preview_mp4(
    images: torch.Tensor,
    fps: float,
    out_path: str,
    audio: Optional[dict] = None,
) -> str:
    fps = max(1.0, float(fps))
    frames = (images.detach().cpu().clamp(0.0, 1.0) * 255.0).to(torch.uint8).numpy()
    h, w = int(frames.shape[1]), int(frames.shape[2])
    if (w % 2) or (h % 2):
        nw, nh = w - (w % 2), h - (h % 2)
        frames = frames[:, :nh, :nw, :]
        h, w = nh, nw

    audio_aac = None
    if audio is not None:
        audio_aac = out_path + ".aac"
        if _audio_to_aac(audio, audio_aac) is None:
            audio_aac = None

    ff = _ffmpeg_exe()
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
    ]
    if audio_aac:
        cmd += [
            "-i", audio_aac,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-shortest", "-movflags", "+faststart", out_path,
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "ultrafast", "-crf", "23",
            "-an", "-movflags", "+faststart", out_path,
        ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(frames.shape[0]):
            proc.stdin.write(frames[i].tobytes())
        proc.stdin.close()
        proc.wait(timeout=600)
    finally:
        if proc.poll() is None:
            proc.kill()
        if audio_aac:
            try:
                os.remove(audio_aac)
            except OSError:
                pass
    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f"ffmpeg failed writing preview ({proc.returncode}): {out_path}")
    return out_path


def _build_video(images: torch.Tensor, audio: Optional[dict], fps: float, alpha: Optional[torch.Tensor]):
    if InputImpl is None or Types is None:
        return None
    alpha_out = None
    if alpha is not None:
        alpha_out = alpha.detach().float().cpu().clamp(0.0, 1.0)
        if alpha_out.ndim == 4 and alpha_out.shape[-1] == 1:
            alpha_out = alpha_out[..., 0]
    return InputImpl.VideoFromComponents(
        Types.VideoComponents(
            images=images.detach().float().cpu().clamp(0.0, 1.0),
            audio=audio,
            frame_rate=Fraction(fps).limit_denominator(1000),
            alpha=alpha_out,
        )
    )


class HempdawgMaskOverlayPlayer:
    """Apply mask video as alpha onto original video; preview + pass VIDEO for Save Video."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_video": ("VIDEO",),
                "mask_video": ("VIDEO",),
                "invert_mask": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "On: black subject / white bg mattes. Off: white=keep subject (Alpha Gen docs).",
                }),
                "show_player": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Off: hide in-node preview and skip preview encode (use Alpha Video Save instead).",
                }),
                "loop": ("BOOLEAN", {"default": True}),
                "autoplay": ("BOOLEAN", {"default": True}),
                "mute": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "audio": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("VIDEO", "IMAGE", "MASK", "AUDIO", "FLOAT")
    RETURN_NAMES = ("video", "rgba", "mask", "audio", "fps")
    OUTPUT_NODE = True
    FUNCTION = "overlay"
    CATEGORY = "Hempdawg/Alpha Gen"
    DESCRIPTION = (
        "Apply a matte video as alpha on the original: subject stays, background goes transparent. "
        "Optional AUDIO overrides/adds soundtrack. Toggle show_player off if you only use Alpha Video Save. "
        "VIDEO out for Save Video; rgba is RGBA frames."
    )

    def overlay(
        self,
        original_video,
        mask_video,
        invert_mask,
        show_player=True,
        loop=True,
        autoplay=True,
        mute=False,
        audio=None,
        **_ignored,
    ):
        rgb, v_audio, fps, _ = _components_from_video(original_video)
        mask_frames, _, _mask_fps, _mask_alpha = _components_from_video(mask_video)

        # Prefer explicit audio input; else keep audio from original video.
        out_audio = audio if audio is not None else v_audio

        rgb = rgb.detach().float().cpu()
        if rgb.shape[-1] > 3:
            rgb = rgb[..., :3]

        n, h, w, _ = rgb.shape
        alpha = _mask_from_frames(mask_frames, h, w, n)
        if invert_mask:
            alpha = 1.0 - alpha

        if rgb.shape[0] != alpha.shape[0]:
            n = min(rgb.shape[0], alpha.shape[0])
            rgb = rgb[:n]
            alpha = alpha[:n]

        rgba = torch.cat([rgb, alpha.unsqueeze(-1)], dim=-1)
        out_video = _build_video(rgb, out_audio, fps, alpha)
        if out_video is None:
            raise RuntimeError("Could not build VIDEO output (Comfy video API unavailable).")

        ui_payload = [{"show_player": False}]
        if show_player:
            preview_rgb = _composite_preview(rgb, alpha, cell=16)
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            filename = f"hemp_mask_overlay_{int(time.time() * 1000)}_{os.getpid()}.mp4"
            filepath = os.path.join(temp_dir, filename)
            _write_preview_mp4(preview_rgb, fps, filepath, audio=out_audio)
            ui_payload = [{
                "filename": filename,
                "subfolder": "",
                "type": "temp",
                "format": "video/mp4",
                "frame_rate": fps,
                "loop": bool(loop),
                "autoplay": bool(autoplay),
                "muted": bool(mute),
                "has_audio": out_audio is not None,
                "show_player": True,
            }]

        return {
            "ui": {"hemp_mask_videos": ui_payload},
            "result": (out_video, rgba, alpha, out_audio, float(fps)),
        }


NODE_CLASS_MAPPINGS = {
    "HempdawgMaskOverlayPlayer": HempdawgMaskOverlayPlayer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HempdawgMaskOverlayPlayer": "Hempdawg Mask Overlay Player",
}
