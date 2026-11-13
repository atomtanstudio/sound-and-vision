"""The whole app imports and builds with a fresh data folder: a wiring mistake (a setting that isn't there, say)
fails here rather than when the service starts."""
import importlib
import sys


def test_the_app_starts(tmp_path, monkeypatch):
    monkeypatch.setenv("SV_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SV_MODELS", str(tmp_path / "models"))
    for name in [m for m in sys.modules if m == "sv.app"]:
        del sys.modules[name]
    app = importlib.import_module("sv.app")
    assert app.cfg.models == tmp_path / "models"
    assert app.comfy.check_graph is not None
