from pathlib import Path
from types import SimpleNamespace
import json
import sys

import pytest

from .lora_runtime import load_artifact_runtime, resolve_lora_runtime
from .test_api import client, payload
from .test_loras import adapter


def configured(tmp_path, config):
    config.lora_engine = "ai-toolkit"
    config.lora_toolkit_root = tmp_path / "toolkit"
    folder = config.lora_toolkit_root / "extensions_built_in/audio_models/yue2/src"
    folder.mkdir(parents=True)
    for name in ["model.py", "pipeline.py"]:
        (folder / name).write_text("# test runtime marker\n")
    config.lora_toolkit_python = tmp_path / "venv/bin/python"
    config.lora_toolkit_python.parent.mkdir(parents=True)
    config.lora_toolkit_python.symlink_to(sys.executable)
    config.lora_toolkit_model = tmp_path / "model.safetensors"
    config.lora_toolkit_model.write_bytes(b"test")
    return config


def test_base_model_does_not_depend_on_optional_lora_runtime():
    config = SimpleNamespace(lora_engine="ai-toolkit")
    assert resolve_lora_runtime(config, None) is None
    config.lora_engine = "native"
    assert resolve_lora_runtime(config, {"id": "selected"}) is None
    config.lora_engine = "wrong"
    with pytest.raises(ValueError, match="Unknown"):
        resolve_lora_runtime(config, {"id": "selected"})


def test_artifact_import_does_not_expose_other_virtualenv_packages(tmp_path, monkeypatch):
    package = tmp_path / "site-packages/yue2"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("artifact_version = 'pinned'\n")
    (package.parent / "torch.py").write_text("raise AssertionError('Wrong virtualenv')\n")
    original_path = list(sys.path)
    monkeypatch.setitem(sys.modules, "yue2", sys.modules.get("yue2"))
    loaded = load_artifact_runtime(package.parent)
    assert loaded.artifact_version == "pinned"
    assert loaded.__path__ == [str(package)]
    assert sys.path == original_path


def test_missing_runtime_and_unsupported_guidance_fail_before_queue(client, tmp_path):
    c, store, config = client
    config.lora_engine = "ai-toolkit"
    adapter(config.data.parent / "loras/style.safetensors")
    choice = c.get("/api/loras").json()["groups"][0]["checkpoints"][0]
    request = payload(1)
    request["form"]["lora"] = {"id": choice["id"], "sha256": choice["sha256"], "strength": 1}
    assert c.post("/api/generations", json=request).status_code == 422
    assert not store.rows()
    configured(tmp_path / "runtime", config)
    request["form"]["cfg_scale"] = "1.5"
    response = c.post("/api/generations", json=request)
    assert response.status_code == 422 and "Guidance 1" in response.json()["detail"]
    assert not store.rows()
    # Ordinary generation remains available if the optional engine is absent.
    request["form"]["lora"] = None
    assert c.post("/api/generations", json=request).status_code == 202


def test_matching_runtime_persists_original_selection_and_idempotency(client, tmp_path):
    c, store, config = client
    configured(tmp_path / "runtime", config)
    adapter(config.data.parent / "loras/style.safetensors")
    choice = c.get("/api/loras").json()["groups"][0]["checkpoints"][0]
    request = payload(1)
    selection = {"id": choice["id"], "sha256": choice["sha256"], "strength": 1}
    request["form"]["lora"] = selection
    request["form"]["cfg_scale"] = "1"
    runtime = resolve_lora_runtime(config, selection, "1")
    assert runtime["name"] == "ai-toolkit-yue2"
    assert runtime["python"] == str(config.lora_toolkit_python.absolute())
    assert runtime["python"] != str(config.lora_toolkit_python.resolve())
    assert (Path(runtime["native_source"]) / "yue2/pipeline.py").is_file()
    response = c.post("/api/generations", json=request)
    assert response.status_code == 202, response.text
    take = response.json()["tracks"][0]
    assert take["lora"]["sha256"] == choice["sha256"]
    assert take["form"]["semantic"]["max_tokens"] == 9000
    config.lora_toolkit_model.unlink()
    assert c.post("/api/generations", json=request).json()["reused"]
    request["requestId"] = "different-request-0002"
    assert c.post("/api/generations", json=request).status_code == 422
    assert len(store.rows()) == 1


def test_matched_sampler_reports_end_and_checks_cancellation_before_sampling():
    from .toolkit_inference import ToolkitPipeline
    from yue2.protocol import MUSIC_END

    runtime = object.__new__(ToolkitPipeline)
    runtime.cancelled = lambda: False
    runtime._ends = {}
    calls = []
    runtime._callback = lambda phase, token: calls.append((phase, token))
    runtime._original_sampler = lambda *_a, **_k: MUSIC_END
    assert runtime._sample(None, [], 200, phase="semantic") == MUSIC_END
    assert runtime._ends == {"semantic": True}
    assert calls == [("semantic", MUSIC_END)]
    runtime.cancelled = lambda: True
    with pytest.raises(InterruptedError):
        runtime._sample(None, [], 201, phase="semantic")
    assert len(calls) == 1


@pytest.mark.parametrize("phase", ["abc", "semantic"])
def test_generation_uses_supported_phase_api_and_preserves_sampling(phase, monkeypatch):
    import dataclasses
    from .toolkit_inference import ToolkitPipeline
    from yue2.protocol import GenerationConfig

    runtime = object.__new__(ToolkitPipeline)
    runtime.cancelled = lambda: False
    runtime._ends = {}
    runtime.model = SimpleNamespace(ar=SimpleNamespace(embed=lambda value: value))
    # The test exercises dispatch, without creating a CUDA tensor or loading weights.
    monkeypatch.setattr("backend.toolkit_inference.torch.tensor", lambda data, **kwargs: data)
    calls = []

    def generate_tokens(embeds, phase, max_tokens, seed, temperature, top_p, top_k,
                        repetition_penalty, penalty_window, min_tokens, progress=None,
                        legacy_off=False):
        calls.append((phase, min_tokens, max_tokens, seed, legacy_off))
        runtime._ends[phase] = True
        return [10, 20]

    def generate_codec_tokens(embeds, max_tokens, seed, temperature, top_p, top_k,
                              repetition_penalty, penalty_window, min_tokens,
                              progress=None, legacy_off=False):
        return generate_tokens(embeds, "semantic", max_tokens, seed, temperature,
                               top_p, top_k, repetition_penalty, penalty_window,
                               min_tokens, progress, legacy_off)

    runtime.pipeline = SimpleNamespace(generate_tokens=generate_tokens,
                                       generate_codec_tokens=generate_codec_tokens)
    config = GenerationConfig()
    sampling = dataclasses.replace(config.abc if phase == "abc" else config.semantic,
                                   min_tokens=7, max_tokens=200)
    ids, timing, truncated = runtime._generate([1, 2], phase, sampling, 42, None, legacy_off=True)
    assert calls == [(phase, 7, 200, 42, phase == "semantic")]
    assert ids == [10, 20] and not truncated and timing["output_tokens"] == 3
    assert runtime._callback is None


@pytest.mark.parametrize("adapter_engine", ["toolkit", "native", None])
def test_worker_dispatches_selected_runtime_and_publishes(client, tmp_path, monkeypatch, adapter_engine):
    c, store, config = client
    configured(tmp_path / "runtime", config)
    adapter(config.data.parent / "loras/style.safetensors", metadata={"sound_vision_inference_engine": "native"} if adapter_engine == "native" else None)
    if adapter_engine == "native":
        # A native-trained adapter must still work if the optional Toolkit
        # checkpoint is unavailable, despite the legacy server-wide setting.
        config.lora_toolkit_model.unlink()
    request = payload(1)
    request["form"]["cfg_scale"] = "1"
    if adapter_engine:
        choice = c.get("/api/loras").json()["groups"][0]["checkpoints"][0]
        request["form"]["lora"] = {"id": choice["id"], "sha256": choice["sha256"], "strength": 1}
    take = c.post("/api/generations", json=request).json()["tracks"][0]
    calls = []

    class Worker:
        def __init__(self, command, **kwargs):
            spec = json.loads(Path(command[-1]).read_text())
            calls.append((command, spec, kwargs))
            (Path(spec["output"]) / "delivery.json").write_text(json.dumps({"duration": 319.96, "timing": {"e2e_seconds": 1}}))

        def poll(self):
            return 0

        def wait(self):
            return 0

    monkeypatch.setattr("backend.api.subprocess.Popen", Worker)
    c.app.state.manager.run_take(take["id"])
    command, spec, options = calls[0]
    assert command[0] == (str(config.lora_toolkit_python.absolute()) if adapter_engine == "toolkit" else sys.executable)
    assert command[1:3] == ["-m", "backend.runner"]
    assert options["start_new_session"] is True
    assert spec["generation"]["semantic"]["max_tokens"] == 9000
    assert bool(spec["engine"]) == (adapter_engine == "toolkit")
    if adapter_engine == "toolkit":
        assert spec["engine"]["name"] == "ai-toolkit-yue2"
    if adapter_engine:
        assert spec["song"]["style"].startswith("sv_test, ")
        assert spec["lora"]["strength"] == 1
    if adapter_engine == "native":
        assert spec["lora"]["inference_engine"] == "native"
    assert store.job(take["id"])["state"] == "succeeded"
