import { app } from "../../scripts/app.js";

function attachInfo(node) {
  if (node._hempResize32Ready) return;
  node._hempResize32Ready = true;

  const wrap = document.createElement("div");
  wrap.className = "hemp-video-resize32-info";
  wrap.style.cssText = "width:100%;padding:4px 2px 2px;box-sizing:border-box;";

  const label = document.createElement("div");
  label.textContent = "Size / Ratio";
  label.style.cssText =
    "font-size:11px;letter-spacing:0.04em;text-transform:uppercase;color:#9aa7b5;margin:0 0 4px 2px;";

  const info = document.createElement("div");
  info.style.cssText =
    "font-size:13px;color:#d7dee7;background:#121820;border:1px solid #243041;border-radius:6px;padding:8px 10px;min-height:18px;";
  info.textContent = "Run to see resized size / ratio";

  wrap.append(label, info);

  const widget = node.addDOMWidget("hemp_resize32_info_widget", "hemp_resize32", wrap, {
    serialize: false,
    hideOnZoom: false,
  });
  widget.computeSize = function (width) {
    return [width, 64];
  };

  node._hempResize32InfoEl = info;
  node._hempResize32Widget = widget;
}

app.registerExtension({
  name: "Hempdawg.VideoResize32",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== "HempdawgVideoResize32") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated?.apply(this, arguments);
      attachInfo(this);
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);
      attachInfo(this);
      const text = message?.hemp_resize32_info?.[0];
      if (text && this._hempResize32InfoEl) {
        this._hempResize32InfoEl.textContent = text;
      }
    };
  },
});
