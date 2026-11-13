"""Model downloads that can't leave a broken file behind, for audio-separator.

audio-separator's own downloader writes straight to the model's name and only asks whether that name exists, so a
download that stopped (a dropped connection, a stopped container) left a cut-short model that every later analysis
tried to load. This one:
  - downloads into NAME.part, carries on from where a dropped download stopped, and moves the file into place only
    when it has the size the server gave;
  - checks a model that was already there once against the server's size (a cut-short one is fetched again from
    where it stops), then remembers it in .sv-checked.json so later runs don't ask again; with no network it trusts
    the file;
  - says NotThere (a RuntimeError, as audio-separator's own downloader raises) when a URL doesn't have the file, so
    audio-separator goes on to its other URL for it.
Standard library only, so it runs in the analysis image as it is.
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.request

TRIES = 8
HEADERS = {"User-Agent": "sound-and-vision-analysis"}
CHECKED = ".sv-checked.json"
TRUST_WHAT_IS_HERE = False   # set while loading again with the files here, when no URL had one of them


class NotThere(RuntimeError):
    """The server doesn't have the file at this URL."""


def _total(r) -> int | None:
    """The whole file's size from a 200 (Content-Length) or 206 (Content-Range: bytes a-b/total) answer."""
    rng = r.headers.get("Content-Range") or ""
    if "/" in rng:
        t = rng.rsplit("/", 1)[1].strip()
        return int(t) if t.isdigit() else None
    n = r.headers.get("Content-Length") or ""
    return int(n) if r.status == 200 and n.isdigit() else None


def remote_size(url: str, timeout: float = 30) -> int | None:
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=HEADERS), timeout=timeout) as r:
        n = r.headers.get("Content-Length") or ""
        return int(n) if n.isdigit() else None


def fetch(url: str, dest: str, *, tries: int = TRIES, timeout: float = 60, log=print, pause=lambda n: time.sleep(min(30, 5 * n))) -> None:
    """Download url to dest through dest.part, carrying on after drops; dest appears only when whole."""
    part = dest + ".part"
    for attempt in range(1, tries + 1):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = dict(HEADERS, **({"Range": f"bytes={have}-"} if have else {}))
        total = None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                if have and r.status == 200:   # no ranges from this server: start again
                    have = 0
                total = _total(r)
                with open(part, "ab" if have else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:   # asked past the end: the .part may already be whole, or longer than the file
                total = _total(e)
            elif e.code in (401, 403, 404, 410):
                raise NotThere(f"couldn't download {url}: the server answered {e.code}") from e
            else:
                log(f"download of {os.path.basename(dest)}: the server answered {e.code}; trying again ({attempt}/{tries})")
                pause(attempt)
                continue
        except (OSError, http.client.HTTPException) as e:   # dropped, reset, timed out, cut off mid-answer
            log(f"download of {os.path.basename(dest)} stopped ({e.__class__.__name__}); carrying on ({attempt}/{tries})")
            pause(attempt)
            continue
        size = os.path.getsize(part) if os.path.exists(part) else 0
        if total is None or size == total:
            os.replace(part, dest)
            return
        if size > total:
            os.remove(part)
        log(f"download of {os.path.basename(dest)}: {size} of {total} bytes; carrying on ({attempt}/{tries})")
    raise RuntimeError(f"couldn't download {url} after {tries} tries; run the analysis again to carry on")


def _checked(folder: str) -> dict:
    try:
        with open(os.path.join(folder, CHECKED)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _remember(dest: str) -> None:
    folder, name = os.path.split(dest)
    seen = _checked(folder)
    seen[name] = os.path.getsize(dest)
    tmp = os.path.join(folder, CHECKED + ".tmp")
    with open(tmp, "w") as f:
        json.dump(seen, f, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(folder, CHECKED))


def ensure(url: str, dest: str, log=print, **kw) -> None:
    """audio-separator's download_file_if_not_exists, done safely (see the module's notes)."""
    if os.path.isfile(dest):
        size = os.path.getsize(dest)
        if TRUST_WHAT_IS_HERE or _checked(os.path.dirname(dest)).get(os.path.basename(dest)) == size:
            return
        try:
            want = remote_size(url)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):   # not at this URL: let audio-separator check it against its other one
                raise NotThere(f"{url}: the server answered {e.code}") from e
            return
        except Exception:   # offline, or the server won't say: trust the file
            return
        if want is None or size == want:
            _remember(dest)
            return
        log(f"{os.path.basename(dest)} is {size} of {want} bytes: a download that stopped; fetching the rest")
        if size < want and not os.path.exists(dest + ".part"):
            os.replace(dest, dest + ".part")
        else:
            os.remove(dest)
    fetch(url, dest, log=log, **kw)
    _remember(dest)
