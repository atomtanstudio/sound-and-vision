import json
import struct
from pathlib import Path

import pytest

from sv import influences
from sv.influences import InfluenceError


def fake_safetensors(path: Path, keys: dict[str, list[int]], meta: dict | None = None) -> Path:
    header: dict = {k: {"dtype": "BF16", "shape": shape, "data_offsets": [0, 2]} for k, shape in keys.items()}
    if meta:
        header["__metadata__"] = meta
    raw = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\0\0")
    return path


YUE2_KEYS = {
    "text_encoders.model.layers.0.mlp.gate_up_proj.lora_A.weight": [32, 2048],
    "text_encoders.model.layers.0.mlp.gate_up_proj.lora_B.weight": [11264, 32],
    "diffusion_model.model.layers.0.self_attn.qkv_proj.lora_A.weight": [32, 2048],
}


def test_a_yue2_lora_is_recognised(tmp_path):
    f = fake_safetensors(tmp_path / "a.safetensors", YUE2_KEYS, {"ss_tag_frequency": json.dumps({"1_x": {"sv_dreampop": 1}})})
    info = influences.inspect(f)
    assert info["model"] == "yue2" and info["rank"] == 32 and info["trigger"] == "sv_dreampop" and info["loraTensors"] == 3


def test_a_file_without_lora_weights_is_refused(tmp_path):
    f = fake_safetensors(tmp_path / "b.safetensors", {"model.layers.0.weight": [10, 10]})
    with pytest.raises(InfluenceError, match="isn't a LoRA"):
        influences.inspect(f)


def test_a_pickle_or_junk_file_is_refused(tmp_path):
    f = tmp_path / "c.safetensors"
    f.write_bytes(b"\x80\x04\x95" + b"x" * 64)
    with pytest.raises(InfluenceError, match="isn't a .safetensors"):
        influences.inspect(f)


def test_add_files_it_with_a_description_and_lists_it(tmp_path):
    loras = tmp_path / "loras"
    f = fake_safetensors(tmp_path / "in.safetensors", YUE2_KEYS)
    rec = influences.add(loras, f, name="Night Drive", kind="Genre", about="synthwave", model="yue2", source="upload: x")
    assert rec["id"] == "night_drive" and (loras / "soundandvision/yue2/night_drive.safetensors").exists()
    assert not f.exists()
    listed = influences.listed(loras, "yue2")
    assert [r["name"] for r in listed] == ["Night Drive"] and listed[0]["kind"] == "Genre"
    f2 = fake_safetensors(tmp_path / "in2.safetensors", YUE2_KEYS)
    assert influences.add(loras, f2, name="Night Drive", kind="Genre", about="", model="yue2", source="x")["id"] == "night_drive_2"


@pytest.mark.parametrize("url, ok", [
    ("https://huggingface.co/someone/repo/blob/main/style.safetensors", True),
    ("https://hf.co/someone/repo/resolve/main/style.safetensors", True),
    ("https://huggingface.co/someone/repo/blob/main/style.ckpt", False),
    ("http://huggingface.co/someone/repo/resolve/main/style.safetensors", False),
    ("https://evil.example/someone/repo/resolve/main/style.safetensors", False),
])
def test_only_hugging_face_safetensors_links(url, ok):
    if ok:
        assert influences.hf_url(url).startswith("https://huggingface.co/someone/repo/resolve/main/")
    else:
        with pytest.raises(InfluenceError):
            influences.hf_url(url)


def test_move_into_crosses_disks(tmp_path, monkeypatch):
    import errno
    from pathlib import Path

    src, dest = tmp_path / "a" / "x.safetensors", tmp_path / "b" / "y.safetensors"
    src.parent.mkdir()
    dest.parent.mkdir()
    src.write_bytes(b"weights")
    real = Path.replace

    def no_cross(self, target):  # the first rename (src -> library) is across disks on Legion
        if self == src:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", no_cross)
    influences.move_into(src, dest)
    assert dest.read_bytes() == b"weights" and not src.exists()
    assert not list(dest.parent.glob(".*.part"))
