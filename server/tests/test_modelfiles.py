"""A job stops before ComfyUI loads a model file that a stopped download left cut short (sv/modelfiles.py)."""
import asyncio

import pytest

from sv.comfy.client import Comfy, ComfyError
from sv.config import ROOT
from sv.modelfiles import ModelFiles

MANIFEST = """# test
pictures|diffusion_models/krea.safetensors|Org/Repo/krea.safetensors|aa|100
pictures|text_encoders/qwen.safetensors|Org/Repo/qwen.safetensors|bb|50
ace|diffusion_models/ace_step_1.5/ace.safetensors|Org/Repo/ace.safetensors|cc|30
songs|loras/soundandvision/yue2/inst.safetensors|Org/Repo/inst.safetensors|dd|20
"""


@pytest.fixture
def files(tmp_path):
    (tmp_path / "models.txt").write_text(MANIFEST)
    models, loras = tmp_path / "models", tmp_path / "models" / "comfyui" / "loras"
    return ModelFiles(models, loras, tmp_path / "models.txt"), models / "comfyui", loras


def put(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def graph(*names):
    return {str(i): {"class_type": "Loader", "inputs": {"name": n, "strength": 1.0}} for i, n in enumerate(names)}


def test_a_cut_short_file_is_named_with_the_set_that_fetches_it(files):
    mf, comfyui, _ = files
    put(comfyui / "diffusion_models" / "krea.safetensors", 40)
    (problem,) = mf.problems(graph("krea.safetensors"))
    assert "krea.safetensors" in problem and "cut short" in problem and "scripts/models.sh pictures" in problem


def test_whole_files_and_files_not_found_pass(files):
    mf, comfyui, loras = files
    put(comfyui / "diffusion_models" / "krea.safetensors", 100)
    put(loras / "soundandvision" / "yue2" / "inst.safetensors", 20)
    assert mf.problems(graph("krea.safetensors", "soundandvision/yue2/inst.safetensors", "qwen.safetensors")) == []


def test_comfyuis_other_folder_names_and_subfolders(files):
    mf, comfyui, loras = files
    put(comfyui / "clip" / "qwen.safetensors", 49)
    put(comfyui / "diffusion_models" / "ace_step_1.5" / "ace.safetensors", 29)
    put(loras / "soundandvision" / "yue2" / "inst.safetensors", 3)
    got = mf.problems(graph("qwen.safetensors", "ace_step_1.5/ace.safetensors", "soundandvision/yue2/inst.safetensors"))
    assert len(got) == 3


def test_no_manifest_checks_nothing(tmp_path):
    put(tmp_path / "comfyui" / "diffusion_models" / "krea.safetensors", 1)
    assert ModelFiles(tmp_path, tmp_path / "loras", tmp_path / "none.txt").problems(graph("krea.safetensors")) == []


def test_the_shipped_manifest_reads(tmp_path):
    mf = ModelFiles(tmp_path, tmp_path / "loras")
    assert mf.files and ROOT.joinpath("scripts", "models.txt").is_file()
    assert "krea2_turbo_fp8_scaled.safetensors" in mf.files


def test_submit_stops_before_comfyui_is_asked(files):
    mf, comfyui, _ = files
    put(comfyui / "diffusion_models" / "krea.safetensors", 40)
    comfy = Comfy("http://127.0.0.1:9", check_graph=mf.problems)   # nothing listens there: it must not be reached

    async def go():
        try:
            with pytest.raises(ComfyError, match="cut short"):
                await comfy.submit(graph("krea.safetensors"), "test")
        finally:
            await comfy.close()

    asyncio.run(go())
