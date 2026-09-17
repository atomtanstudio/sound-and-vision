import json
from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file

from .loras import LoraLibrary, merge_adapter, sha256, target_weights, triggered_style
from .test_api import client, payload

torch.set_num_threads(2)
AR = "text_encoders.model.layers.0.self_attn.qkv_proj"
NAR = "diffusion_model.model.layers.0.mlp.gate_up_proj"


def adapter(path, *, step=600, prefixes=(AR,), bad=False, metadata=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tensors = {}
    for prefix in prefixes:
        rows = 4096 if "qkv" in prefix else 12288
        tensors[prefix + ".lora_A.weight"] = torch.ones(1, 2048) * 0.02
        tensors[prefix + ".lora_B.weight"] = torch.arange(rows, dtype=torch.float32).reshape(rows, 1) / rows
    if bad:
        tensors[AR + ".lora_A.weight"][0, 0] = float("nan")
    save_file(tensors, str(path), metadata={"training_info": json.dumps({"step": step}), "ss_tag_frequency": '{"1_test": {"sv_test": 1}}', **(metadata or {})})
    return path


def test_scan_groups_refresh_metadata_and_partial_files(tmp_path):
    library = LoraLibrary(tmp_path / "loras")
    folder = library.root / "styles" / "DreamPop"
    adapter(folder / "step-0600.safetensors")
    (folder / "lora.json").write_text(json.dumps({"name": "DreamPop", "trigger": "sv_dreampop", "preferred_step": 600, "generation": {"cot": "off", "cfg_scale": 1}}))
    first = library.scan()
    assert len(first["groups"]) == 1 and not first["issues"]
    assert first["groups"][0]["trigger"] == "sv_dreampop"
    assert first["groups"][0]["preferredStep"] == 600
    adapter(folder / "step-1000.safetensors", step=1000)
    artist = adapter(library.root / "artists" / "Artist name" / "artist.safetensors")
    (folder / "copying.safetensors").write_bytes(b"partial")
    second = library.scan()
    assert len(second["groups"]) == 2
    assert second["groups"][0]["kind"] == "artist"
    assert second["groups"][0]["trigger"] == "sv_test"
    assert [c["step"] for c in second["groups"][1]["checkpoints"]] == [600, 1000]
    assert len(second["issues"]) == 1
    artist.unlink()
    assert len(library.scan()["groups"]) == 1


def test_unsupported_symlink_and_changed_checkpoint(tmp_path):
    library = LoraLibrary(tmp_path / "loras")
    path = adapter(library.root / "valid.safetensors")
    selected = {**library.scan()["groups"][0]["checkpoints"][0], "strength": 1}
    adapter(path, step=700)
    with pytest.raises(ValueError, match="changed"):
        library.resolve(selected)
    save_file({"flux.weight": torch.zeros(1)}, str(library.root / "wrong.safetensors"))
    external = adapter(tmp_path / "outside.safetensors")
    (library.root / "outside.safetensors").symlink_to(external)
    scan = library.scan()
    assert len(scan["groups"]) == 1 and len(scan["issues"]) == 2


def test_native_route_comes_from_checkpoint_metadata_not_selection(tmp_path):
    library = LoraLibrary(tmp_path / "loras")
    path = adapter(library.root / "native.safetensors", metadata={"sound_vision_inference_engine": "native"})
    selected = {**library.scan()["groups"][0]["checkpoints"][0], "strength": 1}
    assert library.resolve(selected)["inference_engine"] == "native"
    adapter(path, metadata={"sound_vision_inference_engine": "untrusted-command"})
    scan = library.scan()
    assert not scan["groups"] and "inference engine" in scan["issues"][0]["message"]
    adapter(path)
    clean = library.scan()["groups"][0]["checkpoints"][0]
    resolved = library.resolve({**clean, "strength": 1, "inference_engine": "native"})
    assert "inference_engine" not in resolved


def test_persist_selection_idempotency_and_fail_closed(client):
    c, store, config = client
    path = adapter(config.data.parent / "loras" / "styles" / "DreamPop" / "step-600.safetensors")
    assert c.get("/api/loras", headers={"Authorization": "bad"}).status_code == 401
    checkpoint = c.get("/api/loras").json()["groups"][0]["checkpoints"][0]
    request = payload(count=1)
    request["form"]["lora"] = {"id": checkpoint["id"], "sha256": checkpoint["sha256"], "strength": 0.8}
    response = c.post("/api/generations", json=request)
    assert response.status_code == 202, response.text
    take = response.json()["tracks"][0]
    assert take["lora"]["step"] == 600 and take["lora"]["strength"] == 0.8
    assert take["lora"]["trigger"] == "sv_test"
    assert json.loads(store.job(take["id"])["lora_json"]) == take["lora"]
    path.unlink()
    # An ambiguous submission can still retrieve its existing take after the file moves.
    assert c.post("/api/generations", json=request).json()["reused"]
    request["requestId"] = "new-request-0002"
    assert c.post("/api/generations", json=request).status_code == 422
    assert len(store.rows()) == 1
    assert c.get("/api/library").json()["tracks"][0]["lora"]["step"] == 600
    request["form"]["lora"]["id"] = "../../outside"
    assert c.post("/api/generations", json=request).status_code == 422


def test_trigger_added_once_and_only_when_selected():
    assert triggered_style("Hazy guitars", "sv_test") == "sv_test, Hazy guitars"
    assert triggered_style("sv_test, hazy guitars", "sv_test") == "sv_test, hazy guitars"
    assert triggered_style("In the style of SV_TEST.", "sv_test") == "In the style of SV_TEST."
    assert triggered_style("Hazy guitars", "") == "Hazy guitars"


def test_fused_ar_nar_weights_merge_and_base_file_stays_unchanged(tmp_path):
    path = adapter(tmp_path / "both.safetensors", prefixes=(AR, NAR))
    weights = {name: torch.nn.Parameter(torch.zeros(rows, 2048), requires_grad=False)
               for prefix in (AR, NAR) for name, rows in target_weights(prefix)}
    class Model:
        def get_parameter(self, name):
            return weights[name]
    digest = sha256(path)
    receipt = merge_adapter(Model(), path, digest, 0.5)
    assert receipt["experts"] == ["AR", "NAR"] and receipt["model_weights_updated"] == 5
    # Confirm fused Q/K/V and gate/up boundaries independently, including the NAR expert.
    assert weights["model.layers.0.self_attn.k_proj.weight"][0, 0].item() == pytest.approx(0.005)
    assert weights["model.layers.0.self_attn.v_proj.weight"][0, 0].item() == pytest.approx(0.0075)
    assert weights["model.layers.0.nar_mlp.up_proj.weight"][0, 0].item() == pytest.approx(0.005)
    assert sha256(path) == digest
    with pytest.raises(ValueError, match="changed"):
        merge_adapter(Model(), path, "0" * 64, 1)
    path = adapter(tmp_path / "nan.safetensors", bad=True)
    before = weights["model.layers.0.self_attn.q_proj.weight"].clone()
    with pytest.raises(ValueError, match="non-finite"):
        merge_adapter(Model(), path, sha256(path), 1)
    assert torch.equal(before, weights["model.layers.0.self_attn.q_proj.weight"])
