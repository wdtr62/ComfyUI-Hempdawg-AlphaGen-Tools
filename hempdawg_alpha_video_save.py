"""Hempdawg Alpha Video Save — preview RGBA+audio, then manual-save to ProRes/WebM with alpha."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import Any, Optional

import numpy as np
import torch
import folder_paths

try:
    from server import PromptServer
    from aiohttp import web
except Exception:  # pragma: no cover
    PromptServer = None
    web = None

# node_id -> pending save payload
_PENDING: dict[str, dict[str, Any]] = {}


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
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in (
        os.path.expanduser("~/bin/ffmpeg"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError("ffmpeg not found")


def _sanitize_name(name: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-")
    return "".join(c if c in allowed else "_" for c in (name or "output"))


def _remap_cross_machine_path(path: str) -> str:
    if not path:
        return path
    p = os.path.expanduser(path)
    norm = p.replace("\\", "/")
    remaps = (
        ("/home/hempydawg/CORSAIR/Storage_2", "/media/hempsack/Storage_2"),
        ("/home/hempydawg/CORSAIR/Storage_1", "/media/hempsack/storage_1"),
        ("/home/hempydawg/CORSAIR/storage_2", "/media/hempsack/Storage_2"),
        ("/home/hempydawg/CORSAIR/storage_1", "/media/hempsack/storage_1"),
        ("/home/hempsack/CORSAIR/Storage_2", "/media/hempsack/Storage_2"),
        ("/home/hempsack/CORSAIR/Storage_1", "/media/hempsack/storage_1"),
    )
    for src, dst in remaps:
        if norm == src or norm.startswith(src + "/"):
            return dst + norm[len(src):]
    return p


def _resolve_output_dir(output_root: str, output_subfolder: str) -> str:
    root = _remap_cross_machine_path(output_root)
    sub = (output_subfolder or "").strip()
    full = os.path.abspath(os.path.join(root, sub)) if sub else os.path.abspath(root)
    if full.startswith("/home/hempydawg") and os.environ.get("USER") != "hempydawg":
        alt = full.replace("/home/hempydawg/CORSAIR/Storage_2", "/media/hempsack/Storage_2", 1)
        alt = alt.replace("/home/hempydawg/CORSAIR/Storage_1", "/media/hempsack/storage_1", 1)
        if alt != full:
            full = alt
        elif not os.path.isdir("/home/hempydawg"):
            raise PermissionError(
                f"Save path is a laptop path that does not exist here: {full}. "
                f"Use /media/hempsack/Storage_2/... on Corsair."
            )
    return full


def _unique_path(folder: str, stem: str, ext: str) -> str:
    counter = 1
    while True:
        fname = f"{stem}{counter:03d}.{ext}"
        full = os.path.join(folder, fname)
        if not os.path.exists(full):
            return full
        counter += 1


def _run_ffmpeg(cmd: list[str]) -> None:
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", errors="replace")[-2500:]
        raise RuntimeError(f"ffmpeg failed ({r.returncode}): {err}")


def _unpack_audio(audio: dict, fallback_sr: int = 44100):
    if not audio or not isinstance(audio, dict):
        return None, fallback_sr
    waveform = audio.get("waveform")
    sr = int(audio.get("sample_rate") or fallback_sr)
    if waveform is None:
        return None, sr
    if isinstance(waveform, torch.Tensor):
        wav = waveform.detach().cpu()
    else:
        wav = torch.as_tensor(waveform)
    if wav.ndim == 3:
        wav = wav[0]
    if wav.ndim != 2:
        return None, sr
    return wav, sr


def _write_audio_wav(audio: dict, out_wav: str) -> Optional[str]:
    wav, sr = _unpack_audio(audio)
    if wav is None:
        return None
    channels = int(wav.shape[0])
    pcm = wav.transpose(0, 1).contiguous().numpy().astype(np.float32, copy=False)
    raw = out_wav + ".f32"
    pcm.tofile(raw)
    try:
        _run_ffmpeg([
            _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "f32le", "-ar", str(sr), "-ac", str(channels),
            "-i", raw, out_wav,
        ])
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass
    return out_wav if os.path.isfile(out_wav) else None


def _rgba_uint8(images: torch.Tensor) -> np.ndarray:
    x = images.detach().float().cpu().clamp(0.0, 1.0)
    if x.ndim != 4:
        raise ValueError(f"Expected IMAGE [B,H,W,C], got {tuple(x.shape)}")
    if x.shape[-1] == 3:
        ones = torch.ones((*x.shape[:-1], 1), dtype=x.dtype)
        x = torch.cat([x, ones], dim=-1)
    elif x.shape[-1] > 4:
        x = x[..., :4]
    elif x.shape[-1] == 1:
        x = x.expand(-1, -1, -1, 3)
        ones = torch.ones((*x.shape[:-1], 1), dtype=x.dtype)
        x = torch.cat([x, ones], dim=-1)
    return (x * 255.0).to(torch.uint8).numpy()


def _checkerboard_composite(rgba: np.ndarray, cell: int = 16) -> np.ndarray:
    """RGBA uint8 [N,H,W,4] -> RGB uint8 preview over checkerboard."""
    n, h, w, _ = rgba.shape
    yy = np.arange(h)[:, None]
    xx = np.arange(w)[None, :]
    board = ((yy // cell) + (xx // cell)) % 2
    light = np.full((h, w, 3), 191, dtype=np.uint8)
    dark = np.full((h, w, 3), 89, dtype=np.uint8)
    bg = np.where(board[..., None].astype(bool), light, dark)
    out = np.empty((n, h, w, 3), dtype=np.uint8)
    for i in range(n):
        a = rgba[i, ..., 3:4].astype(np.float32) / 255.0
        rgb = rgba[i, ..., :3].astype(np.float32)
        comp = rgb * a + bg.astype(np.float32) * (1.0 - a)
        out[i] = np.clip(comp, 0, 255).astype(np.uint8)
    return out


def _write_preview_mp4(rgb: np.ndarray, fps: float, out_path: str, audio: Optional[dict]) -> str:
    fps = max(1.0, float(fps))
    h, w = int(rgb.shape[1]), int(rgb.shape[2])
    if (w % 2) or (h % 2):
        nw, nh = w - (w % 2), h - (h % 2)
        rgb = rgb[:, :nh, :nw, :]
        h, w = nh, nw

    audio_wav = None
    tmp_wav = out_path + ".wav"
    if audio is not None:
        audio_wav = _write_audio_wav(audio, tmp_wav)

    ff = _ffmpeg_exe()
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
    ]
    if audio_wav:
        cmd += [
            "-i", audio_wav,
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
        for i in range(rgb.shape[0]):
            proc.stdin.write(rgb[i].tobytes())
        proc.stdin.close()
        proc.wait(timeout=600)
    finally:
        if proc.poll() is None:
            proc.kill()
        if audio_wav and os.path.isfile(tmp_wav):
            try:
                os.remove(tmp_wav)
            except OSError:
                pass
    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f"preview encode failed ({proc.returncode})")
    return out_path


def _encode_alpha_video(
    rgba: np.ndarray,
    fps: float,
    out_path: str,
    fmt: str,
    audio: Optional[dict],
) -> str:
    """Write ProRes 4444 MOV or WebM VP9 with alpha (+ optional audio)."""
    fps = max(1.0, float(fps))
    n, h, w, _ = rgba.shape
    # VP9 yuva420p wants even dims
    if fmt == "webm_vp9" and ((w % 2) or (h % 2)):
        nw, nh = w - (w % 2), h - (h % 2)
        rgba = rgba[:, :nh, :nw, :]
        h, w = nh, nw

    tmp_dir = tempfile.mkdtemp(prefix="hemp_alpha_")
    try:
        audio_wav = None
        wav_path = os.path.join(tmp_dir, "audio.wav")
        if audio is not None:
            audio_wav = _write_audio_wav(audio, wav_path)

        # Write raw RGBA to disk — avoids pipe/communicate "flush of closed file"
        raw_path = os.path.join(tmp_dir, "frames.rgba")
        rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
        with open(raw_path, "wb") as f:
            f.write(rgba.tobytes())

        ff = _ffmpeg_exe()
        cmd = [
            ff, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{w}x{h}", "-r", str(fps),
            "-i", raw_path,
        ]
        if audio_wav:
            cmd += ["-i", audio_wav]

        if fmt == "prores4444_mov":
            cmd += [
                "-c:v", "prores_ks", "-profile:v", "4444",
                "-pix_fmt", "yuva444p10le",
            ]
            if audio_wav:
                cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
            else:
                cmd += ["-an"]
            cmd += [out_path]
        elif fmt == "webm_vp9":
            cmd += [
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-auto-alt-ref", "0", "-crf", "30", "-b:v", "0",
            ]
            if audio_wav:
                cmd += ["-c:a", "libopus", "-b:a", "128k", "-shortest"]
            else:
                cmd += ["-an"]
            cmd += [out_path]
        else:
            raise ValueError(f"Unknown format: {fmt}")

        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if r.returncode != 0 or not os.path.isfile(out_path):
            err = (r.stderr or b"").decode("utf-8", errors="replace")[-2500:]
            raise RuntimeError(f"alpha encode failed ({r.returncode}): {err}")
        return out_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)



def _do_save(payload: dict[str, Any]) -> str:
    fmt = payload["format"]
    ext = "mov" if fmt == "prores4444_mov" else "webm"
    out_dir = _resolve_output_dir(payload["output_root"], payload["output_subfolder"])
    os.makedirs(out_dir, exist_ok=True)
    stem = _sanitize_name(payload["filename"])
    if payload.get("overwrite"):
        path = os.path.join(out_dir, f"{stem}.{ext}")
    else:
        path = _unique_path(out_dir, stem, ext)

    _encode_alpha_video(
        payload["rgba"],
        payload["fps"],
        path,
        fmt,
        payload.get("audio"),
    )
    return path


def _register_routes():
    if PromptServer is None or web is None:
        return
    routes = PromptServer.instance.routes

    @routes.post("/hempdawg/alpha_video_save")
    async def hemp_alpha_video_save(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        node_id = str(data.get("node_id") or "")
        if not node_id or node_id not in _PENDING:
            return web.json_response(
                {"ok": False, "error": "No preview cached. Run the node first."},
                status=404,
            )
        try:
            path = _do_save(_PENDING[node_id])
            return web.json_response({"ok": True, "path": path})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)


_register_routes()


class HempdawgAlphaVideoSave:
    """Preview RGBA+audio, then save with transparency via button when ready."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "rgba": ("IMAGE",),
                "audio": ("AUDIO",),
                "output_root": ("STRING", {
                    "default": "/media/hempsack/Storage_2/ComfyOutputs",
                    "tooltip": "Root folder. Laptop CORSAIR paths remap on Corsair.",
                }),
                "output_subfolder": ("STRING", {"default": "alpha_video", "tooltip": "Optional sub-folder."}),
                "filename": ("STRING", {"default": "alpha_clip", "tooltip": "Base name without extension."}),
                "format": (
                    ["prores4444_mov", "webm_vp9"],
                    {"default": "prores4444_mov", "tooltip": "ProRes 4444 MOV (Resolve) or WebM VP9+alpha."},
                ),
                "overwrite": ("BOOLEAN", {"default": False}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.01}),
                "loop": ("BOOLEAN", {"default": True}),
                "autoplay": ("BOOLEAN", {"default": True}),
                "mute": ("BOOLEAN", {"default": False}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True
    FUNCTION = "preview"
    CATEGORY = "Hempdawg/Alpha Gen"
    DESCRIPTION = (
        "Preview RGBA + audio (checkerboard = transparent). "
        "Click Save File when happy — writes ProRes 4444 MOV or WebM VP9 with alpha+audio."
    )

    def preview(
        self,
        rgba,
        audio,
        output_root,
        output_subfolder,
        filename,
        format,
        overwrite,
        fps,
        loop,
        autoplay,
        mute,
        unique_id=None,
        **_ignored,
    ):
        node_id = str(unique_id or "0")
        rgba_u8 = _rgba_uint8(rgba)
        preview_rgb = _checkerboard_composite(rgba_u8, cell=16)

        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)
        fname = f"hemp_alpha_preview_{int(time.time() * 1000)}_{os.getpid()}.mp4"
        fpath = os.path.join(temp_dir, fname)
        _write_preview_mp4(preview_rgb, fps, fpath, audio=audio)

        # Cache for manual save (keep CPU numpy + audio dict)
        audio_cache = None
        if audio is not None and isinstance(audio, dict):
            wav, sr = _unpack_audio(audio)
            if wav is not None:
                audio_cache = {"waveform": wav.unsqueeze(0).contiguous(), "sample_rate": int(sr)}

        _PENDING[node_id] = {
            "rgba": rgba_u8.copy(),
            "audio": audio_cache,
            "fps": float(fps),
            "format": format,
            "output_root": output_root,
            "output_subfolder": output_subfolder,
            "filename": filename,
            "overwrite": bool(overwrite),
        }

        fmt_label = "ProRes 4444 MOV" if format == "prores4444_mov" else "WebM VP9"
        status = (
            f"Preview ready ({rgba_u8.shape[0]} frames @ {float(fps):.2f} fps). "
            f"Click Save File → {fmt_label} with alpha+audio."
        )

        preview = {
            "filename": fname,
            "subfolder": "",
            "type": "temp",
            "format": "video/mp4",
            "frame_rate": float(fps),
            "loop": bool(loop),
            "autoplay": bool(autoplay),
            "muted": bool(mute),
            "has_audio": audio_cache is not None,
            "node_id": node_id,
            "save_format": format,
        }

        return {
            "ui": {
                "hemp_alpha_save_videos": [preview],
                "text": [status],
            },
            "result": (status,),
        }


NODE_CLASS_MAPPINGS = {
    "HempdawgAlphaVideoSave": HempdawgAlphaVideoSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HempdawgAlphaVideoSave": "Hempdawg Alpha Video Save",
}
