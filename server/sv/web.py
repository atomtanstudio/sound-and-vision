"""The built web app, as the server hands it out."""
from pathlib import Path


def web_file(web: Path, path: str) -> Path:
    """The web app's own file at `path`, else its index.html (the app routes it). Never a file outside the web folder,
    however the path is spelled: the data folder, with the app's key, sits next to it."""
    root = web.resolve()
    f = (root / path).resolve()
    return f if path and f.is_relative_to(root) and f.is_file() else root / "index.html"
