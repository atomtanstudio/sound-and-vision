"""Resolve an operator-configured LoRA runtime without importing GPU packages."""

import importlib.util
import os
import sys
from pathlib import Path


def load_artifact_runtime(source):
    """Load only the pinned artifact package, never its venv's other libraries."""
    package = Path(source) / "yue2"
    spec = importlib.util.spec_from_file_location(
        "yue2", package / "__init__.py", submodule_search_locations=[str(package)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["yue2"] = module
    spec.loader.exec_module(module)
    return module


def resolve_lora_runtime(settings, lora, guidance=""):
    if not lora or settings.lora_engine == "native":
        return None
    if settings.lora_engine != "ai-toolkit":
        raise ValueError("Unknown configured LoRA inference engine.")
    if lora.get("inference_engine") == "native":
        return None
    if guidance and float(guidance) != 1:
        raise ValueError("The matched LoRA engine requires Guidance 1. Set Guidance to 1 or leave it blank.")
    paths = {
        "root": settings.lora_toolkit_root,
        "python": settings.lora_toolkit_python,
        "checkpoint": settings.lora_toolkit_model,
    }
    if any(value is None for value in paths.values()):
        raise ValueError("The matched LoRA engine is not configured on this server.")
    # Resolving a venv interpreter symlink would launch the system Python instead.
    paths = {key: Path(value).absolute() if key == "python" else Path(value).resolve()
             for key, value in paths.items()}
    source = paths["root"] / "extensions_built_in/audio_models/yue2/src"
    required = [paths["python"], paths["checkpoint"], source / "pipeline.py", source / "model.py"]
    if any(not path.is_file() for path in required):
        raise ValueError("The matched LoRA runtime or checkpoint is missing. Ask the server operator to restore it.")
    if not os.access(paths["python"], os.X_OK):
        raise ValueError("The configured LoRA Python interpreter is not executable.")
    package = importlib.util.find_spec("yue2")
    if package is None or not package.origin:
        raise ValueError("The app's YuE2 artifact runtime is missing.")
    return {"name": "ai-toolkit-yue2", **{key: str(value) for key, value in paths.items()},
            "native_source": str(Path(package.origin).resolve().parent.parent)}
