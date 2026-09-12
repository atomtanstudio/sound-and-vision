---
license: cc-by-nc-4.0
library_name: transformers
tags:
- audio
- autoencoder
- yue2
---
<p align="center">
  <img src="assets/logo.png" alt="YuE logo" width="144" />
</p>
<h1 align="center">🤗 YuE2-Vae</h1>

<p align="center">
  <a href="https://github.com/multimodal-art-projection/YuE"><img alt="GitHub" src="https://img.shields.io/badge/GitHub-YuE-181717?logo=github&amp;logoColor=white" height="20" /></a>
  &nbsp;
  <a href="https://discord.gg/ssAyWMnMzu"><img alt="Join Discord" src="https://img.shields.io/discord/842440537755353128?label=Discord&amp;color=5865F2&amp;logo=discord&amp;logoColor=white" height="20" /></a>
</p>
<p align="center">
  <a href="https://map-yue2.github.io/">🎧&nbsp;Demo</a>
  ·
  <a href="#quick-start">🚀&nbsp;Quick&nbsp;start</a>
  ·
  <a href="#speed-and-resources" title="Speed and resources">⚡&nbsp;Speed</a>
  ·
  <a href="https://huggingface.co/m-a-p/YuE2-3B#benchmarks">📊&nbsp;Benchmarks</a>
  ·
  <a href="#citation">📚&nbsp;Citation</a>
</p>
<p align="center">
  <a href="https://huggingface.co/m-a-p/YuE2-3B"><img alt="🤗 YuE2-3B" src="https://img.shields.io/badge/YuE2--3B-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
  &nbsp;
  <a href="https://huggingface.co/m-a-p/YuE2-Vae"><img alt="🤗 YuE2-Vae" src="https://img.shields.io/badge/YuE2--Vae-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
  &nbsp;
  <a href="https://huggingface.co/m-a-p/YuE2-Vae-legacy"><img alt="🤗 YuE2-Vae-legacy" src="https://img.shields.io/badge/YuE2--Vae--legacy-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
  &nbsp;
  <a href="https://huggingface.co/m-a-p/MERT-v2-30s"><img alt="🤗 MERT-v2-30s" src="https://img.shields.io/badge/MERT--v2--30s-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
  &nbsp;
  <a href="https://huggingface.co/m-a-p/MERT-v2-FullSong"><img alt="🤗 MERT-v2-FullSong" src="https://img.shields.io/badge/MERT--v2--FullSong-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
  &nbsp;
  <a href="https://huggingface.co/datasets/m-a-p/WildSongBench"><img alt="🤗 WildSongBench" src="https://img.shields.io/badge/WildSongBench-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
  &nbsp;
  <a href="https://huggingface.co/m-a-p/SheetSage2"><img alt="SheetSage2" src="https://img.shields.io/badge/SheetSage2-374151?logo=huggingface&amp;logoColor=FFD21E" height="20" /></a>
</p>

**YuE2-Vae turns acoustic latents into 48 kHz stereo music.** It is the default decoder for song generation and listening, with full-song decoding, an audio encoder, and Hugging Face loading.

Use it with **[🤗 YuE2-3B](https://huggingface.co/m-a-p/YuE2-3B)** for full-song generation, or load it on its own to encode and decode audio. [🤗 Alternative decoder: YuE2-Vae-legacy](https://huggingface.co/m-a-p/YuE2-Vae-legacy).

<a id="listen"></a>

## 🎧 Listen to YuE2

<a id="text-to-music"></a>

### 🎶 Text-to-music

Original songs generated from lyrics and a style prompt.

**Cyber Metal · English · 5:00**

<audio controls preload="none" aria-label="Cyber Metal" src="https://huggingface.co/m-a-p/YuE2-3B/resolve/main/assets/audio/cyber-metal.mp3"></audio>

**今晚不眠 · Mandarin funk / nu-disco · 3:24**

<audio controls preload="none" aria-label="今晚不眠" src="https://huggingface.co/m-a-p/YuE2-3B/resolve/main/assets/audio/tonight-awake.mp3"></audio>

**Passion · English rock · 3:55**

<audio controls preload="none" aria-label="Passion" src="https://huggingface.co/m-a-p/YuE2-3B/resolve/main/assets/audio/passion.mp3"></audio>

*All three songs use [🤗 YuE2-Vae](https://huggingface.co/m-a-p/YuE2-Vae).*

![YuE2 song quality and text alignment on WildSongBench](assets/figure1.png)

*Complete YuE2 system results on 192 WildSongBench prompts, using symbolic planning. Bo8 means best-of-8.*

![YuE2 architecture and audio decoder](assets/architecture.png)

*The VAE turns YuE2's acoustic latents into stereo audio.*

<a id="quick-start"></a>

## 🚀 Quick start

For full-song generation, follow the [YuE2-3B quick start](https://huggingface.co/m-a-p/YuE2-3B#quick-start) and select `vae="m-a-p/YuE2-Vae"` in `YuE2Pipeline.from_pretrained(...)`.

<a id="decode-saved-acoustic-latents"></a>

### 🔊 Decode saved acoustic latents

Install the tested standalone dependencies:

```bash
python -m pip install torch==2.10.0 transformers==4.57.6 huggingface-hub==0.36.2 safetensors==0.7.0 numpy==2.2.6 soundfile==0.13.1
```

Use `latent.npy` saved by `song.save_artifacts("outputs/song")`:

```python
import numpy as np
import soundfile as sf
import torch
from transformers import AutoModel

# Tested FP32 CUDA settings; YuE2Pipeline sets these automatically.
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.allow_tf32 = torch.backends.cuda.matmul.allow_tf32 = False
torch.set_float32_matmul_precision("highest")

repo = "m-a-p/YuE2-Vae"
vae = AutoModel.from_pretrained(
    repo, trust_remote_code=True, decoder_only=True, device="cuda",
)
z = torch.from_numpy(np.load("outputs/song/latent.npy"))  # [T, 64]
audio = vae.decode_tiled(z.T.unsqueeze(0))                # [1, 2, samples], CPU
sf.write("decoded.flac", audio[0].T.clamp(-1, 1).numpy(), 48000, subtype="PCM_24")
```

<details>
<summary>⚙️ Encoding audio and decoding options</summary>

`decode_tiled` bounds memory with 1024-frame cores and 16-frame context. `vae.decode(z.T.unsqueeze(0))` offers full decoding; both preserve the natural output length `1920 × T − 64`. Keep the VAE in FP32.

**🎙️ Encode a short audio clip**


```python
encoder = AutoModel.from_pretrained(repo, trust_remote_code=True, device="cpu")
z = encoder.encode(audio[..., :48000])  # First second of the decoded audio
```

Encoding accepts `[batch, 2, samples]` audio already at 48 kHz and returns the posterior mean by default. Set `sample=True, generator=...` for posterior sampling.

</details>

<a id="speed-and-resources"></a>

## ⚡ Speed and resources

**About 3.6 seconds to decode a 3.6-minute song on an RTX 4090.** Each checkpoint is **530.5 MB**; decoder-only FP32 weights occupy **253.2 MiB**, before activations.

| GPU | Decoder | Warm samples | VAE stage / audio duration |
|---|---|---:|---:|
| RTX 4090 24GB | YuE2-Vae | 32 | 3.63 / 214.85 s |
| RTX 4090 24GB | YuE2-Vae-legacy | 32 | 3.47 / 214.85 s |
| H800 80GB | YuE2-Vae | 1 | 3.04 / 224.96 s |

<details>
<summary>🔎 Measurement details</summary>

PyTorch 2.10, FP32, tiled decoding; timings include device transfers. 4090 values average 32 full-CoT songs; H800 is a one-song check. Full-pipeline 4090 peaks were 11.18 GiB with YuE2-Vae and 11.19 GiB with legacy; standalone decoder peak memory was not isolated.

</details>

**[Full-song speed and GPU requirements](https://huggingface.co/m-a-p/YuE2-3B#speed-and-resources)** · **[WildSongBench and SHS100K results](https://huggingface.co/m-a-p/YuE2-3B#benchmarks)**. System benchmark scores use YuE2-Vae-legacy; YuE2-Vae is the default listening decoder.

<details>
<summary>🔊 Choosing a VAE</summary>

In our comparisons, [🤗 YuE2-Vae-legacy](https://huggingface.co/m-a-p/YuE2-Vae-legacy) achieves higher musicality scores on benchmarks, while [🤗 YuE2-Vae](https://huggingface.co/m-a-p/YuE2-Vae) delivers better perceptual audio quality. We recommend YuE2-Vae by default; use YuE2-Vae-legacy when reproducing the paper's benchmark results.

</details>

<a id="citation"></a>

## 📚 Citation

**Technical report coming soon.** For now, please cite [YuE](https://arxiv.org/abs/2503.08638) when using YuE2-Vae in your research.

```bibtex
@article{yuan2025yue,
  title = {{YuE}: Scaling Open Foundation Models for Long-Form Music Generation},
  author = {Yuan, Ruibin and Lin, Hanfeng and Guo, Shuyue and Zhang, Ge and Pan, Jiahao and Zang, Yongyi and Liu, Haohe and Liang, Yiming and Ma, Wenye and Du, Xingjian and Du, Xinrun and Ye, Zhen and Zheng, Tianyu and Jiang, Zhengxuan and Ma, Yinghao and Liu, Minghao and Tian, Zeyue and Zhou, Ziya and Xue, Liumeng and Qu, Xingwei and Li, Yizhi and Wu, Shangda and Shen, Tianhao and Ma, Ziyang and Zhan, Jun and Wang, Chunhui and Wang, Yatian and Chi, Xiaowei and Zhang, Xinyue and Yang, Zhenzhu and Wang, Xiangzhou and Liu, Shansong and Mei, Lingrui and Li, Peng and Wang, Junjie and Yu, Jianwei and Pang, Guojian and Li, Xu and Wang, Zihao and Zhou, Xiaohuan and Yu, Lijun and Benetos, Emmanouil and Chen, Yong and Lin, Chenghua and Chen, Xie and Xia, Gus and Zhang, Zhaoxiang and Zhang, Chao and Chen, Wenhu and Zhou, Xinyu and Qiu, Xipeng and Dannenberg, Roger and Liu, Jiaheng and Yang, Jian and Huang, Wenhao and Xue, Wei and Tan, Xu and Guo, Yike},
  journal = {arXiv preprint arXiv:2503.08638},
  year = {2025},
  eprint = {2503.08638},
  archivePrefix = {arXiv},
  url = {https://arxiv.org/abs/2503.08638}
}
```

Weights: [CC BY-NC 4.0](LICENSE). [Third-party code licenses](THIRD_PARTY_NOTICES.md).
