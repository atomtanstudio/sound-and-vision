"""Sound / Vision's own ComfyUI nodes (sv-comfy only).

SVAudioRangeMask: marks a stretch of an audio latent for re-generation. ComfyUI's
SetLatentNoiseMask reshapes every mask to an image (B, 1, H, W), which the sampler
can't fit to an audio latent (B, C, T); this sets a (B, 1, T) mask instead, with
short linear fades so the new part blends into what's kept. The sampler then keeps
the source outside the range at every step (ComfyUI's inpainting path).
"""

import torch


class SVAudioRangeMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "samples": ("LATENT",),
            "start_s": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.01}),
            "end_s": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 3600.0, "step": 0.01}),
            "fade_s": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 10.0, "step": 0.01}),
            "latent_fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 1000.0, "step": 0.01,
                                     "tooltip": "Latent frames per second (ACE-Step 1.5: 48000 / 1920 = 25)."}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "mask"
    CATEGORY = "sound_vision"

    def mask(self, samples, start_s, end_s, fade_s, latent_fps):
        x = samples["samples"]
        if x.ndim != 3:
            raise ValueError(f"SVAudioRangeMask wants an audio latent (B, C, T); got shape {tuple(x.shape)}")
        n = x.shape[-1]
        t = torch.arange(n, dtype=torch.float32) / latent_fps
        a, b = min(start_s, end_s), max(start_s, end_s)
        if fade_s > 0:
            m = torch.clamp((t - (a - fade_s)) / fade_s, 0, 1) * torch.clamp(((b + fade_s) - t) / fade_s, 0, 1)
        else:
            m = ((t >= a) & (t < b)).float()
        out = samples.copy()
        out["noise_mask"] = m.reshape(1, 1, n)
        return (out,)


NODE_CLASS_MAPPINGS = {"SVAudioRangeMask": SVAudioRangeMask}
NODE_DISPLAY_NAME_MAPPINGS = {"SVAudioRangeMask": "Audio Range Mask (Sound / Vision)"}
