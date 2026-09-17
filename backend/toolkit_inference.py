"""Inference-only facade over an explicitly installed AI Toolkit YuE2 runtime.

No training, package installation, model downloads, or shared model-file writes.
The worker still uses the app's pinned SymbolicPlan/SongResult artifact contract.
"""

import dataclasses
import gc
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open
from safetensors.torch import load_file
from yue2.pipeline import SemanticResult, SymbolicPlan
from yue2.protocol import ABC_END, MUSIC_END, token_prefixes

from .loras import adapter_pairs, fingerprint, read_header, sha256


class ToolkitPipeline:
    def __init__(self, spec, config, cancelled):
        self.config = config
        self.cancelled = cancelled
        self.adapters = []
        self._callback = None
        self._ends = {}
        self._check_cancelled()
        options = spec["engine"]
        root = Path(options["root"])
        sys.path.insert(0, str(root))
        from extensions_built_in.audio_models.yue2.src import pipeline as engine
        from extensions_built_in.audio_models.yue2.src.model import YuE2Model
        from extensions_built_in.audio_models.yue2.src.tokenizer import YuE2TextTokenizer
        from extensions_built_in.audio_models.yue2.src.vae import YuE2VAE
        from toolkit.lora_special import LoRAModule

        torch.set_num_threads(4)
        started = time.monotonic()
        checkpoint = Path(options["checkpoint"])
        stamp = fingerprint(checkpoint)
        checkpoint_sha = sha256(checkpoint)
        state = load_file(str(checkpoint))
        if fingerprint(checkpoint) != stamp:
            raise ValueError("The inference checkpoint changed while loading.")
        self.tokenizer = YuE2TextTokenizer(state.pop("text_encoders.yue2_tokenizer_json").numpy().tobytes())
        self.model = YuE2Model.load_from_state_dict(state, dtype=torch.bfloat16).eval()
        vae_state = {key[len("vae."):]: value for key, value in state.items() if key.startswith("vae.")}
        self.vae = YuE2VAE.load_from_state_dict(vae_state, dtype=torch.float32).eval()
        del state, vae_state
        self._check_cancelled()
        self.model.ar.to("cuda")

        selected = spec["lora"]
        path = Path(spec["lora_path"])
        lora_stamp = fingerprint(path)
        if sha256(path) != selected["sha256"]:
            raise ValueError("LoRA file changed after submission.")
        header, _ = read_header(path)
        pairs, experts = adapter_pairs(header)

        class Network(torch.nn.Module):
            network_type = "lora"
            is_lorm = False
            is_active = True
            is_merged_in = False

            def __init__(self, strength):
                super().__init__()
                self._multiplier = strength
                self.register_buffer("torch_multiplier", torch.tensor([strength], device="cuda", dtype=torch.float32))

        strength = selected["strength"]
        if not math.isfinite(strength) or not 0.1 <= strength <= 2:
            raise ValueError("LoRA strength must be between 0.1 and 2.")
        self.network = Network(strength)
        with safe_open(path, framework="pt", device="cpu") as source:
            for name in pairs:
                self._check_cancelled()
                family, relative = name.split(".", 1)
                expert = self.model.ar if family == "text_encoders" else self.model.nar
                target = expert.get_submodule(relative)
                down = source.get_tensor(name + ".lora_A.weight")
                up = source.get_tensor(name + ".lora_B.weight")
                rank = down.shape[0]
                alpha = float(source.get_tensor(name + ".alpha").item()) if name + ".alpha" in header else rank
                if not math.isfinite(alpha) or alpha <= 0 or not torch.isfinite(down).all() or not torch.isfinite(up).all():
                    raise ValueError("LoRA contains non-finite weights or invalid alpha.")
                adapter = LoRAModule(name, target, lora_dim=rank, alpha=alpha, network=self.network).to(device="cuda", dtype=torch.float32).eval()
                with torch.no_grad():
                    adapter.lora_down.weight.copy_(down)
                    adapter.lora_up.weight.copy_(up)
                adapter.requires_grad_(False)
                adapter.apply_to()
                self.adapters.append(adapter)
        if fingerprint(path) != lora_stamp:
            raise ValueError("LoRA changed while loading.")

        self.adapter = {**selected, "experts": experts, "adapter_modules": len(pairs),
                        "format": "yue2-ai-toolkit-peft", "merge": "unmerged-float32-output-adapters"}
        self.pipeline = engine.YuE2Pipeline(self.model, self.vae)
        self.pipeline.use_cuda_graphs = True
        self.pipeline.do_tiled_decoding = True
        self._engine = engine
        self._original_sampler = engine.sample_logits
        engine.sample_logits = self._sample
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        runtime_files = [root / "extensions_built_in/audio_models/yue2/src" / name
                         for name in ("model.py", "pipeline.py", "tokenizer.py", "vae.py")]
        runtime_files += [root / "toolkit/network_mixins.py", root / "toolkit/lora_special.py",
                          root / "toolkit/util/convrot_quant.py", root / "toolkit/util/comfy_quant_import.py"]
        self.engine_metadata = {"name": "ai-toolkit-yue2", "source_revision": revision.stdout.strip() if revision.returncode == 0 else "unknown",
                                "checkpoint": str(checkpoint), "checkpoint_sha256": checkpoint_sha,
                                "quantization": "convrot8", "adapter_dtype": "float32", "torch": torch.__version__,
                                "runtime_sha256": {str(p.relative_to(root)): sha256(p) for p in runtime_files}}
        self.weights = {"model": {"path": str(checkpoint), "sha256": checkpoint_sha},
                        "vae": {"embedded_in": str(checkpoint), "sha256": checkpoint_sha},
                        "lora": self.adapter, "engine": self.engine_metadata}
        self.load_timing = {"model_and_adapter_seconds": time.monotonic() - started}

    def _check_cancelled(self):
        if self.cancelled():
            raise InterruptedError("Cancelled")

    def _sample(self, *args, **kwargs):
        self._check_cancelled()
        token = self._original_sampler(*args, **kwargs)
        phase = kwargs.get("phase", "semantic")
        if token == (ABC_END if phase == "abc" else MUSIC_END):
            self._ends[phase] = True
        if self._callback:
            self._callback(phase, token)
        return token

    @staticmethod
    def _request(request):
        if request.cfg_scale is not None and request.cfg_scale != 1:
            raise ValueError("The matched LoRA engine requires Guidance 1.")
        return dataclasses.replace(request, cfg_scale=1.0)

    def _generate(self, prefix, phase, sampling, seed, on_token, legacy_off=False):
        self._check_cancelled()
        self._ends[phase] = False
        self._callback = on_token
        started = time.monotonic()
        try:
            with torch.inference_mode():
                embeds = self.model.ar.embed(torch.tensor([prefix], device="cuda"))
                if phase == "abc":
                    # The ABC convenience wrapper fixes min_tokens at 32 and does
                    # not accept that argument. The phase API honors our settings.
                    ids = self.pipeline.generate_tokens(
                        embeds, phase="abc", seed=seed, **dataclasses.asdict(sampling)
                    )
                else:
                    ids = self.pipeline.generate_codec_tokens(
                        embeds, seed=seed, legacy_off=legacy_off,
                        **dataclasses.asdict(sampling),
                    )
            timing = {"seconds": time.monotonic() - started, "prefix_tokens": len(prefix),
                      "content_tokens": len(ids), "output_tokens": len(ids) + int(self._ends[phase])}
            return ids, timing, not self._ends[phase]
        finally:
            self._callback = None

    def plan(self, *, request, cancelled=None, on_token=None):
        request = self._request(request)
        if request.cot == "off":
            return SymbolicPlan(request, None, [], token_prefixes(request, self.tokenizer))
        if request.abc is not None:
            ids = self.tokenizer.encode_abc(request.abc)
            return SymbolicPlan(request, request.abc, ids, token_prefixes(request, self.tokenizer, ids),
                                {"seconds": 0, "external_prefix_tokens": len(ids)})
        ids, timing, truncated = self._generate(token_prefixes(request, self.tokenizer), "abc", self.config.abc, request.seed, on_token)
        return SymbolicPlan(request, self.tokenizer.decode(ids), ids, token_prefixes(request, self.tokenizer, ids), timing, truncated)

    def generate_semantic(self, plan, *, cancelled=None, on_token=None):
        plan.request = self._request(plan.request)
        if plan.prefix != token_prefixes(plan.request, self.tokenizer, plan.abc_ids):
            raise ValueError("Saved plan does not match the exact request tokens.")
        ids, timing, truncated = self._generate(plan.prefix, "semantic", self.config.semantic,
                                               plan.request.seed, on_token, legacy_off=plan.request.cot == "off")
        return SemanticResult(plan, ids, timing, truncated)

    def synthesize(self, semantic, *, cancelled=None):
        self._check_cancelled()
        self.model.nar.to("cuda")
        with torch.inference_mode():
            prefix = self.model.ar.embed(torch.tensor([semantic.plan.prefix], device="cuda"))
            latents = self.pipeline.synthesize(prefix, semantic.tokens, seed=semantic.plan.request.seed,
                                               steps=self.config.ode_steps, step_callback=lambda *_: self._check_cancelled())
            return latents[0].float().cpu().numpy()

    def decode(self, latents):
        self._check_cancelled()
        self.vae.to("cuda")
        with torch.inference_mode():
            tensor = torch.from_numpy(latents)[None].to("cuda", dtype=self.model.nar.dtype)
            return self.pipeline.decode(tensor)[0].T.contiguous().cpu().numpy()

    def effective_config(self, request):
        return {"generation": self.config.to_dict(), "cot": request.cot, "cfg_scale": 1.0,
                "backend": "ai-toolkit-yue2", "quantization": "convrot8", "model_dtype": "bfloat16/convrot8",
                "adapter_dtype": "float32", "vae_dtype": "float32", "vae_decode": "toolkit_tiled",
                "device": "cuda", "engine": self.engine_metadata}

    def close(self):
        if hasattr(self, "_original_sampler"):
            self._engine.sample_logits = self._original_sampler
        for adapter in self.adapters:
            adapter.org_module[0].forward = adapter.org_forward
        self.adapters.clear()
        self.pipeline = self.model = self.vae = self.network = None
        gc.collect()
        torch.cuda.empty_cache()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
