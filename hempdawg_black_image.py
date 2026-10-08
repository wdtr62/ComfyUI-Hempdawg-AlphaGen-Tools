import torch


class HempdawgBlackImage:
    """Take a VIDEO, make a solid black IMAGE matching its width/height.
    Also outputs the shortest side (min of width/height; either if square).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT")
    RETURN_NAMES = ("image", "shortest")
    FUNCTION = "make_black"
    CATEGORY = "Hempdawg/Alpha Gen"

    def make_black(self, video):
        width, height = video.get_dimensions()
        w = max(1, int(width))
        h = max(1, int(height))
        shortest = min(w, h)
        # ComfyUI IMAGE: [B, H, W, C], float 0..1 — one black frame at video size
        black = torch.zeros((1, h, w, 3), dtype=torch.float32, device="cpu")
        return (black, shortest)


NODE_CLASS_MAPPINGS = {
    "HempdawgBlackImage": HempdawgBlackImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HempdawgBlackImage": "Hempdawg Black Image (Video Size)",
}
