"""Paths kept in a record (a cover's picture, a clip, a loop's video) are the song's own files: they're resolved inside
the song's folder, and one that would land anywhere else (an absolute path, one that climbs out) is treated as gone."""

from __future__ import annotations

from pathlib import Path


def under(root: Path, rel: object) -> Path | None:
    """`rel` inside `root`, resolved; None when it's empty or would be outside."""
    if not rel:
        return None
    r = root.resolve()
    f = (r / str(rel)).resolve()
    return f if f.is_relative_to(r) else None


def drop(root: Path, rel: object) -> None:
    """Delete a song's own file, if it is one."""
    if (f := under(root, rel)) is not None:
        f.unlink(missing_ok=True)
