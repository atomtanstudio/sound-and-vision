"""Add-ons: your own Python files, loaded when the app starts, for things that belong to your setup, not the app.

SV_ADDONS names a folder. Every *.py file in it is imported, and its register(app) is called. `app.cfg` is the app's
settings, and `app.influence` is the Influence Engine. Today an add-on can give the Influence Engine a song finder
(`app.influence.finder`, see influence_engine.SongFinder): something that gets the songs a training run needs into
your music, so you don't add their audio by hand.

An add-on that fails to load is logged and skipped; the app starts without it.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

log = logging.getLogger("sv.addons")


def load(folder: str, app) -> list[str]:
    """Load the add-ons in `folder` (empty: none). Their names, as loaded."""
    if not folder:
        return []
    root = Path(folder).expanduser()
    if not root.is_dir():
        log.warning("SV_ADDONS isn't a folder: %s", root)
        return []
    loaded = []
    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"sv_addon_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if callable(getattr(module, "register", None)):
                module.register(app)
            loaded.append(path.stem)
        except Exception:
            log.exception("Add-on %s didn't load", path.name)
    if loaded:
        log.info("Add-ons: %s", ", ".join(loaded))
    return loaded
