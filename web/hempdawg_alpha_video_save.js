import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const CHROME = 96; // label + status + save row + padding

function fitNodeToWidget(node) {
  const widget = node._hempAlphaSaveWidget;
  if (!widget) return;
  const width = Math.max(320, node.size?.[0] || 360);
  const size = widget.computeSize(width);
  const computed = node.computeSize();
  const newH = Math.max(computed[1], size[1] + 140);
  node.setSize([width, newH]);
  app.graph?.setDirtyCanvas?.(true, true);
}

function layoutPlayer(node) {
  const wrap = node._hempAlphaWrapEl;
  const video = node._hempAlphaVideoEl;
  const widget = node._hempAlphaSaveWidget;
  if (!wrap || !video || !widget) return;

  const width = Math.max(220, (node.size?.[0] || 360) - 20);
  let widgetH = widget.computedHeight || 120;
  if (typeof widget.computeSize === "function") {
    widgetH = widget.computeSize(width)[1];
  }
  wrap.style.width = "100%";
  wrap.style.height = `${Math.max(100, widgetH)}px`;
  wrap.style.overflow = "hidden";
  wrap.style.boxSizing = "border-box";

  const mediaH = Math.max(64, widgetH - CHROME);
  video.style.width = "100%";
  video.style.height = `${mediaH}px`;
  video.style.maxWidth = "100%";
  video.style.maxHeight = `${mediaH}px`;
  video.style.objectFit = "contain";
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
    "width:100%;height:120px;overflow:hidden;padding:4px 0 2px;box-sizing:border-box;position:relative;";

  const label = document.createElement("div");
  label.textContent = "Alpha Video Preview";
  label.style.cssText =
    "font-size:11px;letter-spacing:0.04em;text-transform:uppercase;color:#9aa7b5;margin:0 0 4px 2px;";

  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.style.cssText =
    "width:100%;height:64px;max-width:100%;background:#0b0f14;border-radius:6px;display:block;outline:none;object-fit:contain;";

  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:8px;align-items:center;margin-top:6px;";

  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Save File";
  saveBtn.style.cssText =
    "cursor:pointer;background:#2f6fed;color:#fff;border:none;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:600;";
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
  wrap.append(label, video, row);

  const widget = node.addDOMWidget("hemp_alpha_video_save", "hemp_alpha_save", wrap, {
    serialize: false,
    hideOnZoom: false,
  });

  widget.computeSize = function (width) {
    const w = Math.max(220, (width || node.size?.[0] || 360) - 20);
    if (!video.src || !video.videoWidth || !video.videoHeight) {
      this.computedHeight = 120;
      return [w, 120];
    }
    const ratio = video.videoWidth / Math.max(1, video.videoHeight);
    const mediaH = Math.min(320, Math.max(100, w / ratio));
    const h = Math.round(mediaH + CHROME);
    this.computedHeight = h;
    return [w, h];
  };

  node._hempAlphaWrapEl = wrap;
  node._hempAlphaVideoEl = video;
  node._hempAlphaStatusEl = status;
  node._hempAlphaSaveWidget = widget;

  video.addEventListener("loadedmetadata", () => {
    layoutPlayer(node);
    fitNodeToWidget(node);
    layoutPlayer(node);
  });

  const prevResize = node.onResize;
  node.onResize = function () {
    const r = prevResize?.apply(this, arguments);
    layoutPlayer(this);
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
    fitNodeToWidget(node);
    layoutPlayer(node);
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
