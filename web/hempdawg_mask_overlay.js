import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const CHROME = 52; // label + status + padding inside widget

function fitNodeToWidget(node) {
  const widget = node._hempMaskPlayerWidget;
  if (!widget) return;
  const width = Math.max(280, node.size?.[0] || 320);
  const size = widget.computeSize(width);
  const computed = node.computeSize();
  // Keep current width; grow/shrink height to fit widgets + slots.
  const newH = Math.max(computed[1], size[1] + 120);
  node.setSize([width, newH]);
  app.graph?.setDirtyCanvas?.(true, true);
}

function layoutPlayer(node) {
  const wrap = node._hempMaskWrapEl;
  const video = node._hempMaskVideoEl;
  const widget = node._hempMaskPlayerWidget;
  if (!wrap || !video || !widget) return;

  const width = Math.max(200, (node.size?.[0] || 320) - 20);
  let widgetH = widget.computedHeight || 88;
  if (typeof widget.computeSize === "function") {
    widgetH = widget.computeSize(width)[1];
  }
  wrap.style.width = "100%";
  wrap.style.height = `${Math.max(72, widgetH)}px`;
  wrap.style.overflow = "hidden";
  wrap.style.boxSizing = "border-box";

  const mediaH = Math.max(48, widgetH - CHROME);
  video.style.width = "100%";
  video.style.height = `${mediaH}px`;
  video.style.maxWidth = "100%";
  video.style.maxHeight = `${mediaH}px`;
  video.style.objectFit = "contain";
  video.style.display = "block";
}

function attachPlayer(node) {
  if (node._hempMaskPlayerReady) return;
  node._hempMaskPlayerReady = true;

  const wrap = document.createElement("div");
  wrap.className = "hemp-mask-overlay-player";
  wrap.style.cssText =
    "width:100%;height:88px;overflow:hidden;padding:4px 0 2px;box-sizing:border-box;position:relative;";

  const label = document.createElement("div");
  label.textContent = "Mask Overlay Preview";
  label.style.cssText =
    "font-size:11px;letter-spacing:0.04em;text-transform:uppercase;color:#9aa7b5;margin:0 0 4px 2px;";

  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.style.cssText =
    "width:100%;height:48px;max-width:100%;background:#0b0f14;border-radius:6px;display:block;outline:none;object-fit:contain;";

  const status = document.createElement("div");
  status.style.cssText =
    "font-size:11px;color:#7d8793;margin-top:4px;min-height:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
  status.textContent = "Connect original + mask videos, then run.";

  wrap.append(label, video, status);

  const widget = node.addDOMWidget("hemp_mask_overlay_player", "hemp_mask_player", wrap, {
    serialize: false,
    hideOnZoom: false,
  });

  widget.computeSize = function (width) {
    const w = Math.max(200, (width || node.size?.[0] || 320) - 20);
    if (!video.src || !video.videoWidth || !video.videoHeight) {
      this.computedHeight = 88;
      return [w, 88];
    }
    const ratio = video.videoWidth / Math.max(1, video.videoHeight);
    // Fit inside node width; cap height so it stays manageable.
    const mediaH = Math.min(360, Math.max(100, w / ratio));
    const h = Math.round(mediaH + CHROME);
    this.computedHeight = h;
    return [w, h];
  };

  node._hempMaskWrapEl = wrap;
  node._hempMaskVideoEl = video;
  node._hempMaskStatusEl = status;
  node._hempMaskPlayerWidget = widget;

  video.addEventListener("loadedmetadata", () => {
    layoutPlayer(node);
    fitNodeToWidget(node);
    layoutPlayer(node);
  });

  const prevResize = node.onResize;
  node.onResize = function (size) {
    const r = prevResize?.apply(this, arguments);
    layoutPlayer(this);
    return r;
  };

  layoutPlayer(node);
}

function setPreview(node, meta) {
  attachPlayer(node);
  const video = node._hempMaskVideoEl;
  const status = node._hempMaskStatusEl;
  if (!video || !meta?.filename) return;

  const params = new URLSearchParams({
    filename: meta.filename,
    subfolder: meta.subfolder || "",
    type: meta.type || "temp",
  });
  const url = api.apiURL(`/view?${params.toString()}`);

  video.loop = meta.loop !== false;
  video.muted = !!meta.muted;
  video.autoplay = meta.autoplay !== false;
  video.src = url;
  video.load();

  const tryPlay = () => {
    layoutPlayer(node);
    fitNodeToWidget(node);
    layoutPlayer(node);
    if (!video.autoplay) return;
    const p = video.play();
    if (p && typeof p.catch === "function") {
      p.catch(() => {
        status.textContent = "Preview ready — press play (autoplay blocked).";
      });
    }
  };
  video.oncanplay = tryPlay;

  const fps = meta.frame_rate != null ? Number(meta.frame_rate).toFixed(2) : "?";
  const aud = meta.has_audio ? (meta.muted ? "audio muted" : "audio on") : "no audio";
  status.textContent = `Preview · ${fps} fps · ${aud} · checkerboard = transparent`;
}

app.registerExtension({
  name: "Hempdawg.MaskOverlayPlayer",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "HempdawgMaskOverlayPlayer") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated?.apply(this, arguments);
      attachPlayer(this);
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);
      const clip = message?.hemp_mask_videos?.[0];
      if (clip) setPreview(this, clip);
    };
  },
});
