import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MIN_PLAYER_H = 72;
const EMPTY_PLAYER_H = 88;
const LABEL_STATUS = 36; // label + status + padding inside player

function getShowPlayerWidget(node) {
  return node.widgets?.find((w) => w.name === "show_player");
}

function nonPlayerHeight(node, playerWidget) {
  // Space used by title/slots/other widgets — leftover is for the player.
  let chrome = 52;
  const slots = Math.max(node.inputs?.length || 0, node.outputs?.length || 0);
  chrome += Math.min(slots, 8) * 6;
  for (const w of node.widgets || []) {
    if (!w || w === playerWidget) continue;
    if (typeof w.computeSize === "function") {
      try {
        const sz = w.computeSize(node.size?.[0] || 320);
        chrome += Array.isArray(sz) ? Number(sz[1]) || 22 : 22;
        continue;
      } catch (_) {}
    }
    chrome += 22;
  }
  return chrome;
}

function playerHeightForNode(node, playerWidget) {
  if (node._hempMaskPlayerVisible === false) return 0;
  const nodeH = Math.max(120, node.size?.[1] || 280);
  const avail = nodeH - nonPlayerHeight(node, playerWidget);
  return Math.max(MIN_PLAYER_H, avail);
}

function layoutPlayer(node) {
  const wrap = node._hempMaskWrapEl;
  const video = node._hempMaskVideoEl;
  const media = node._hempMaskMediaEl;
  const widget = node._hempMaskPlayerWidget;
  if (!wrap || !video || !widget) return;
  if (node._hempMaskPlayerVisible === false) {
    wrap.style.display = "none";
    wrap.style.height = "0px";
    widget.computedHeight = 0;
    return;
  }

  const playerH = playerHeightForNode(node, widget);
  widget.computedHeight = playerH;

  wrap.style.display = "flex";
  wrap.style.flexDirection = "column";
  wrap.style.width = "100%";
  wrap.style.height = `${playerH}px`;
  wrap.style.maxHeight = `${playerH}px`;
  wrap.style.overflow = "hidden";
  wrap.style.boxSizing = "border-box";

  const mediaH = Math.max(40, playerH - LABEL_STATUS);
  if (media) {
    media.style.height = `${mediaH}px`;
    media.style.maxHeight = `${mediaH}px`;
    media.style.minHeight = "0";
    media.style.flex = "1 1 auto";
    media.style.overflow = "hidden";
  }
  video.style.width = "100%";
  video.style.height = "100%";
  video.style.maxWidth = "100%";
  video.style.maxHeight = "100%";
  video.style.objectFit = "contain";
  video.style.display = "block";
}

function playerComputeSize(node) {
  return function (width) {
    const w = Math.max(200, (width || node.size?.[0] || 320) - 20);
    if (node._hempMaskPlayerVisible === false) {
      this.computedHeight = 0;
      return [w, 0];
    }
    const h = playerHeightForNode(node, this);
    this.computedHeight = h;
    return [w, h];
  };
}

function setPlayerVisible(node, visible) {
  const wrap = node._hempMaskWrapEl;
  const widget = node._hempMaskPlayerWidget;
  const video = node._hempMaskVideoEl;
  const status = node._hempMaskStatusEl;
  if (!wrap || !widget) return;

  node._hempMaskPlayerVisible = !!visible;

  if (!visible) {
    try {
      video?.pause?.();
    } catch (_) {}
    if (video) {
      video.removeAttribute("src");
      video.load?.();
    }
    wrap.style.display = "none";
    wrap.style.height = "0px";
    widget.computedHeight = 0;
    if (status) status.textContent = "Player off — outputs still update on run.";
    const width = Math.max(280, node.size?.[0] || 320);
    const computed = node.computeSize();
    node.setSize([width, computed[1]]);
  } else {
    wrap.style.display = "flex";
    if (status && (!video?.src || status.textContent.startsWith("Player off"))) {
      status.textContent = "Connect original + mask videos, then run.";
    }
    if (!widget.computedHeight || widget.computedHeight < MIN_PLAYER_H) {
      widget.computedHeight = EMPTY_PLAYER_H;
    }
  }

  widget.computeSize = playerComputeSize(node);
  layoutPlayer(node);
  app.graph?.setDirtyCanvas?.(true, true);
}

function wireShowPlayerToggle(node) {
  const w = getShowPlayerWidget(node);
  if (!w || w._hempShowPlayerWired) return;
  w._hempShowPlayerWired = true;
  const prev = w.callback;
  w.callback = function (v) {
    const r = prev?.apply(this, arguments);
    setPlayerVisible(node, !!v);
    return r;
  };
  setPlayerVisible(node, w.value !== false);
}

function attachPlayer(node) {
  if (node._hempMaskPlayerReady) return;
  node._hempMaskPlayerReady = true;

  const wrap = document.createElement("div");
  wrap.className = "hemp-mask-overlay-player";
  wrap.style.cssText =
    "width:100%;height:88px;max-height:100%;overflow:hidden;padding:4px 0 2px;box-sizing:border-box;position:relative;display:flex;flex-direction:column;";

  const label = document.createElement("div");
  label.textContent = "Mask Overlay Preview";
  label.style.cssText =
    "flex:0 0 auto;font-size:11px;letter-spacing:0.04em;text-transform:uppercase;color:#9aa7b5;margin:0 0 4px 2px;";

  const media = document.createElement("div");
  media.className = "hemp-mask-overlay-media";
  media.style.cssText =
    "flex:1 1 auto;min-height:0;width:100%;overflow:hidden;background:#0b0f14;border-radius:6px;";

  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.style.cssText =
    "width:100%;height:100%;max-width:100%;max-height:100%;background:#0b0f14;display:block;outline:none;object-fit:contain;";

  const status = document.createElement("div");
  status.style.cssText =
    "flex:0 0 auto;font-size:11px;color:#7d8793;margin-top:4px;min-height:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
  status.textContent = "Connect original + mask videos, then run.";

  media.append(video);
  wrap.append(label, media, status);

  const widget = node.addDOMWidget("hemp_mask_overlay_player", "hemp_mask_player", wrap, {
    serialize: false,
    hideOnZoom: false,
  });

  widget.computedHeight = EMPTY_PLAYER_H;
  widget.computeSize = playerComputeSize(node);

  node._hempMaskWrapEl = wrap;
  node._hempMaskMediaEl = media;
  node._hempMaskVideoEl = video;
  node._hempMaskStatusEl = status;
  node._hempMaskPlayerWidget = widget;
  node._hempMaskPlayerVisible = true;

  video.addEventListener("loadedmetadata", () => {
    if (node._hempMaskPlayerVisible === false) return;
    layoutPlayer(node);
    app.graph?.setDirtyCanvas?.(true, true);
  });

  const prevResize = node.onResize;
  node.onResize = function () {
    const r = prevResize?.apply(this, arguments);
    layoutPlayer(this);
    app.graph?.setDirtyCanvas?.(true, true);
    return r;
  };

  layoutPlayer(node);
  wireShowPlayerToggle(node);
  queueMicrotask(() => wireShowPlayerToggle(node));
  setTimeout(() => wireShowPlayerToggle(node), 0);
}

function setPreview(node, meta) {
  attachPlayer(node);
  wireShowPlayerToggle(node);

  const show = meta?.show_player !== false && !!meta?.filename;
  const widget = getShowPlayerWidget(node);
  if (widget && meta && typeof meta.show_player === "boolean") {
    if (widget.value !== meta.show_player) {
      widget.value = meta.show_player;
    }
  }
  setPlayerVisible(node, show);
  if (!show) return;

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
    if (node._hempMaskPlayerVisible === false) return;
    layoutPlayer(node);
    app.graph?.setDirtyCanvas?.(true, true);
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
      wireShowPlayerToggle(this);
      return r;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const r = onConfigure?.apply(this, arguments);
      attachPlayer(this);
      wireShowPlayerToggle(this);
      const w = getShowPlayerWidget(this);
      setPlayerVisible(this, w ? w.value !== false : true);
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
