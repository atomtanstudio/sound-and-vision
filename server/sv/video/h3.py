"""MiniMax H3 through our ComfyUI: a still as the first frame, the end left free, so the motion only ever goes forward
(loops.close makes it repeat; pinning the still at both ends made the motion slow to a stop and come back on itself,
which looked like playing in reverse). `end` pins a last frame when one is wanted (a morph to another picture). The graph is the user's saved "Photogenic H3 FL2VA 6-step" setup (the fused RefDelta + Turbo8
+ Mystic INT8 model, sparse attention at 10%, res_multistep, simple schedule, shift 12), as the old app's lab proved
it (soundandvision.old/lab/living-album/la/h3.py), with the audio side left out: the song supplies the sound.
"""

from __future__ import annotations

UNET = "minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors"
TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
FPS = 24

# H3 reads a still as the first shot of a scene and, given long enough, edits it: a push-in, or a cut to a close-up
# and back (measured 2026-10-04 on figures: 7 of 12 twelve-second clips cut, 1 of 9 six-second clips). So the words
# lead with one continuous shot, and a loop longer than 8 s is made of 6 s pieces played one after another.
SHOT = ("One continuous static shot from a locked-off camera, with no cuts: the framing stays exactly the same from "
        "the first frame to the last, and everything is seen from the same distance the whole time. No zoom, push-in, "
        "pan or tilt, and no close-ups.")
FLOW = ("The motion flows steadily onward the whole time, as if it could go on forever: it never reverses, never settles "
        "back and never comes to a stop. Nothing new enters the frame. The picture keeps its grain and its colors. Audio: "
        "faint ambient tone only. No dialogue, no music, no text or subtitles.")
FEEL = {
    "still": "The motion is very slow and very small: at a glance the picture looks almost still, and only on a second "
             "look do you notice it breathing. Figures hold their pose exactly.",
    "subtle": "The motion is slow and small, never sudden: the picture stays itself, just quietly alive.",
    "gentle": "The motion is slow and gentle, with a little more life, never sudden, and the picture stays itself.",
}
PIECE, PIECE_MAX = 6.0, 8.0


def snap_length(seconds: float) -> int:
    """The model's frame grid: 17k + 5 frames (6 s is 141)."""
    return 17 * max(1, round((seconds * FPS - 5) / 17)) + 5


def prompt(motion: str, feel: str) -> str:
    return f"{SHOT} {' '.join(motion.split())} {FEEL.get(feel, FEEL['still'])}\n\n{FLOW}"


def graph(image: str, text: str, side: int, length: int, seed: int, prefix: str, steps: int = 6,
          end: str | None = None, height: int | None = None) -> dict:
    """`side` is the width, and the height too unless `height` is given (a music video's shots are 16:9)."""
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "BlockSparseAttention", "inputs": {
            "model": ["1", 0], "selection": "sla", "selection.keep_percent": 10.0, "start_percent": 0.0,
            "end_percent": 1.0, "dense_blocks": "", "min_tokens": 12288, "extra_tokens": 256,
            "sink_conditioning": "exact_kv_and_rows", "verbose": False}},
        "3": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["2", 0], "shift_video": 12.0, "shift_audio": 3.0}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": TEXT_ENCODER, "type": "minimax", "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "6": {"class_type": "LoadImage", "inputs": {"image": image}},
        "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["4", 0], "vae": ["5", 0], "prompt": text, "width": side, "height": height or side, "length": length,
            "first_frame": ["6", 0]}},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "BasicGuider", "inputs": {"model": ["3", 0], "conditioning": ["7", 0]}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "11": {"class_type": "BasicScheduler", "inputs": {"model": ["3", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["8", 0], "guider": ["9", 0], "sampler": ["10", 0], "sigmas": ["11", 0], "latent_image": ["7", 1]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["5", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": float(FPS)}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": prefix, "format": "mp4", "codec": "h264"}},
    }
    if end:
        g["16"] = {"class_type": "LoadImage", "inputs": {"image": end}}
        g["7"]["inputs"]["last_frame"] = ["16", 0]
    return g
