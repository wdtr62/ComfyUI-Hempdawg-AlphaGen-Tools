# ComfyUI-Hempdawg-AlphaGen-Tools

Custom ComfyUI nodes for **LTX 2.5 Alpha Gen** workflows: prepare frames, overlay mattes with live preview, resize to model-safe dimensions, and save transparent video with audio.

Nodes appear under **Hempdawg → Alpha Gen** in the ComfyUI add-node menu.

---

## Features

| Node | Purpose |
| --- | --- |
| **Hempdawg Black Image (Video Size)** | Takes a `VIDEO`, creates a solid black `IMAGE` at the same size, and outputs the shortest side length. |
| **Hempdawg Mask Overlay Player** | Applies a matte video as alpha on the original (invert option), optional in-node preview (`show_player` on/off — turn off if using Alpha Video Save), `VIDEO` / `RGBA` / `MASK` outputs. |
| **Hempdawg Video Resize ×32** | Resizes a `VIDEO` so width and height snap to the nearest multiple of 32; shows size/ratio on the node. |
| **Hempdawg Alpha Video Save** | Preview RGBA + audio, then **Save File** when ready. Writes **ProRes 4444 MOV** or **WebM VP9** with alpha and audio to a directory you choose. |

---

## Requirements

- **ComfyUI** (recent build with native `VIDEO` / `AUDIO` types)
- **ffmpeg** available to the ComfyUI process (system `ffmpeg` or `imageio-ffmpeg` in the ComfyUI environment)
- GPU optional for these utility nodes (they are CPU/ffmpeg oriented)
- For Alpha Gen itself you still need the LTX 2.5 models and the Alpha Gen IC-LoRA separately (not bundled here)

### Recommended save formats

| Format | Extension | Notes |
| --- | --- | --- |
| `prores4444_mov` | `.mov` | Best for DaVinci Resolve and editors that expect ProRes 4444 + alpha |
| `webm_vp9` | `.webm` | Lighter WebM with VP9 alpha + Opus audio |

Standard MP4 / H.264 generally **cannot** keep transparency.

---

## Installation

### Option A — Git clone

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/wdtr62/ComfyUI-Hempdawg-AlphaGen-Tools.git
```

### Option B — ZIP download

1. Download the repository ZIP from GitHub (**Code → Download ZIP**).
2. Extract it so you have:

```text
ComfyUI/
└── custom_nodes/
    └── ComfyUI-Hempdawg-AlphaGen-Tools/
        ├── __init__.py
        ├── hempdawg_black_image.py
        ├── hempdawg_mask_overlay.py
        ├── hempdawg_video_resize32.py
        ├── hempdawg_alpha_video_save.py
        ├── web/
        └── README.md
```

3. The folder name should be `ComfyUI-Hempdawg-AlphaGen-Tools` (not a nested double folder).

### After install

1. **Restart ComfyUI** completely (server process, not only the browser tab).
2. **Hard-refresh** the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`) so the preview / Save button UI loads.
3. Add nodes from **Hempdawg → Alpha Gen**.

No extra `pip install` is required for these nodes beyond a normal ComfyUI + ffmpeg setup.

---

## Typical Alpha Gen wiring

1. Load RGB source video.
2. (Optional) **Video Resize ×32** so dimensions are safe for LTX.
3. Run your LTX 2.5 Alpha Gen / IC-LoRA graph to produce the matte video.
4. **Mask Overlay Player**: `original_video` + `mask_video` → preview; use `invert_mask` if the subject/background are swapped.
5. Connect overlay **`rgba`** + **`audio`** into **Alpha Video Save**.
6. Set `output_root`, `output_subfolder`, `filename`, and format.
7. **Run** to preview, then click **Save File** when satisfied.

### Path notes (multi-machine)

`output_root` accepts normal absolute paths. Laptop Samba-style paths under `/home/.../CORSAIR/Storage_*` are remapped to Corsair mounts when running on that machine. Prefer a path that exists and is writable on the machine where ComfyUI is running.

---

## Troubleshooting

| Issue | What to try |
| --- | --- |
| Nodes missing from the menu | Confirm the package is directly under `custom_nodes/`, restart ComfyUI, check the server console for import errors. |
| Preview / Save button missing | Hard-refresh the browser after restart (web extensions load from `web/`). |
| Subject is transparent, background stays | Toggle **invert_mask** on Mask Overlay Player. |
| Save fails / no ffmpeg | Install ffmpeg or ensure `imageio-ffmpeg` is in the ComfyUI venv. |
| Saved MP4 has no transparency | Use **Alpha Video Save** with ProRes 4444 or WebM VP9 — not a normal MP4 Save Video node. |
| Save says no preview cached | Run the Alpha Video Save node once before clicking **Save File**. |

---

## Example workflow

A ready graph is included:

`workflows/LTX-2.5_V2V_ICLoRA_AlphaGen_wdtr62_update.json`

In ComfyUI: **Workflow → Open** (or drag the JSON onto the canvas). Install this package first, plus LTX-2.5 models / Alpha Gen IC-LoRA as listed in the workflow **Model Links** note.

## License

Use and modify for personal or commercial projects. If you redistribute, keep credit to **Hempdawg** and leave this README with the package when practical.

---

## Support

Open a GitHub Issue on this repository with:

- ComfyUI version / commit if known  
- OS and GPU  
- Full error text from the ComfyUI console  
- Which node failed  
