import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const MIN_PLAYER_H = 100;
const EMPTY_PLAYER_H = 120;
const CHROME = 56; // label + save row + padding inside player

function nonPlayerHeight(node, playerWidget) {
  let chrome = 52;
  const slots = Math.max(node.inputs?.length || 0, node.outputs?.length || 0);
  chrome += Math.min(slots, 8) * 6;
  for (const w of node.widgets || []) {
    if (!w || w === playerWidget) continue;
    if (typeof w.computeSize === "function") {
      try {
        const sz = w.computeSize(node.size?.[0] || 360);
        chrome += Array.isArray(sz) ? Number(sz[1]) || 22 : 22;
        continue;
      } catch (_) {}
    }
    chrome += 22;
  }
  return chrome;
}

function playerHeightForNode(node, playerWidget) {
  const nodeH = Math.max(160, node.size?.[1] || 320);
  const avail = nodeH - nonPlayerHeight(node, playerWidget);
  return Math.max(MIN_PLAYER_H, avail);
}

function layoutPlayer(node) {
  const wrap = node._hempAlphaWrapEl;
  const video = node._hempAlphaVideoEl;
  const media = node._hempAlphaMediaEl;
  const widget = node._hempAlphaSaveWidget;
  if (!wrap || !video || !widget) return;

  const playerH = playerHeightForNode(node, widget);
  widget.computedHeight = playerH;

  wrap.style.display = "flex";
  wrap.style.flexDirection = "column";
  wrap.style.width = "100%";
  wrap.style.height = `${playerH}px`;
  wrap.style.maxHeight = `${playerH}px`;
  wrap.style.overflow = "hidden";
  wrap.style.boxSizing = "border-box";

  const mediaH = Math.max(48, playerH - CHROME);
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

async function saveFromNode(node) {
  const status = node._hempAlphaStatusEl;
  const nodeId = node._hempAlphaNodeId;
  if (!nodeId) {
    if (status) status.textContent = "Run the node first to build a preview.";
    return;
  }
  if (status) status.textContent = "Saving alpha video…";
  try {
    const res = await api.fetchApi("/hempdawg/alpha_video_save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId }),
    });
    const data = await res.json();
    if (!data?.ok) {
      if (status) status.textContent = `Save failed: ${data?.error || res.status}`;
      return;
    }
    if (status) status.textContent = `Saved: ${data.path}`;
  } catch (err) {
    if (status) status.textContent = `Save failed: ${err}`;
  }
}

function attachUI(node) {
  if (node._hempAlphaSaveReady) return;
  node._hempAlphaSaveReady = true;

  const wrap = document.createElement("div");
  wrap.className = "hemp-alpha-video-save";
  wrap.style.cssText =
    "width:100%;height:120px;max-height:100%;overflow:hidden;padding:4px 0 2px;box-sizing:border-box;position:relative;display:flex;flex-direction:column;";

  const label = document.createElement("div");
  label.textContent = "Alpha Video Preview";
  label.style.cssText =
    "flex:0 0 auto;font-size:11px;letter-spacing:0.04em;text-transform:uppercase;color:#9aa7b5;margin:0 0 4px 2px;";

  const media = document.createElement("div");
  media.className = "hemp-alpha-video-media";
  media.style.cssText =
    "flex:1 1 auto;min-height:0;width:100%;overflow:hidden;background:#0b0f14;border-radius:6px;";

  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.style.cssText =
    "width:100%;height:100%;max-width:100%;max-height:100%;background:#0b0f14;display:block;outline:none;object-fit:contain;";

  const row = document.createElement("div");
  row.style.cssText =
    "flex:0 0 auto;display:flex;gap:8px;align-items:center;margin-top:6px;min-height:28px;";

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Save File";
  saveBtn.style.cssText =
    "cursor:pointer;background:#2f6fed;color:#fff;border:none;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:600;flex:0 0 auto;";
  saveBtn.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    saveFromNode(node);
  };

  const status = document.createElement("div");
  status.style.cssText =
    "font-size:11px;color:#7d8793;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
  status.textContent = "Connect rgba + audio, run to preview, then Save File.";

  row.append(saveBtn, status);
  media.append(video);
  wrap.append(label, media, row);

  const widget = node.addDOMWidget("hemp_alpha_video_save", "hemp_alpha_save", wrap, {
    serialize: false,
    hideOnZoom: false,
  });

  widget.computedHeight = EMPTY_PLAYER_H;
  widget.computeSize = function (width) {
    const w = Math.max(220, (width || node.size?.[0] || 360) - 20);
    const h = playerHeightForNode(node, this);
    this.computedHeight = h;
    return [w, h];
  };

  node._hempAlphaWrapEl = wrap;
  node._hempAlphaMediaEl = media;
  node._hempAlphaVideoEl = video;
  node._hempAlphaStatusEl = status;
  node._hempAlphaSaveWidget = widget;

  video.addEventListener("loadedmetadata", () => {
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
}

function setPreview(node, meta) {
  attachUI(node);
  const video = node._hempAlphaVideoEl;
  const status = node._hempAlphaStatusEl;
  if (!video || !meta?.filename) return;

  node._hempAlphaNodeId = meta.node_id;

  const params = new URLSearchParams({
    filename: meta.filename,
    subfolder: meta.subfolder || "",
    type: meta.type || "temp",
  });
  video.loop = meta.loop !== false;
  video.muted = !!meta.muted;
  video.autoplay = meta.autoplay !== false;
  video.src = api.apiURL(`/view?${params.toString()}`);
  video.load();

  video.oncanplay = () => {
    layoutPlayer(node);
    app.graph?.setDirtyCanvas?.(true, true);
    if (!video.autoplay) return;
    const p = video.play();
    if (p && typeof p.catch === "function") {
      p.catch(() => {
        if (status) status.textContent = "Preview ready — press play, then Save File when happy.";
      });
    }
  };

  const fps = meta.frame_rate != null ? Number(meta.frame_rate).toFixed(2) : "?";
  const fmt = meta.save_format === "webm_vp9" ? "WebM VP9" : "ProRes 4444";
  if (status) {
    status.textContent = `Preview · ${fps} fps · ${fmt} · click Save File when ready`;
  }
}

app.registerExtension({
  name: "Hempdawg.AlphaVideoSave",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "HempdawgAlphaVideoSave") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated?.apply(this, arguments);
      attachUI(this);
      return r;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const r = onConfigure?.apply(this, arguments);
      attachUI(this);
      layoutPlayer(this);
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);
      const clip = message?.hemp_alpha_save_videos?.[0];
      if (clip) setPreview(this, clip);
      if (message?.text?.[0] && this._hempAlphaStatusEl && !clip) {
        this._hempAlphaStatusEl.textContent = message.text[0];
      }
    };
  },
});
