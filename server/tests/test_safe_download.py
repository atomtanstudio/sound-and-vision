"""The analysis worker's model downloads (infra/legion/analysis/worker/safe_download.py) against a server that drops
connections: nothing cut short is ever left under a model's name, and one left by an older download is repaired."""
import http.server
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "infra" / "legion" / "analysis" / "worker"))
import safe_download  # noqa: E402

DATA = os.urandom(300_000)


class Flaky(http.server.ThreadingHTTPServer):
    """Serves DATA at /model.ckpt with Range support; the first `drops` GETs send `cut` bytes and hang up."""

    def __init__(self, drops=0, cut=100_000):
        self.drops, self.cut, self.gets = drops, cut, 0
        super().__init__(("127.0.0.1", 0), Handler)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}/model.ckpt"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self._answer(False)

    def do_GET(self):
        self._answer(True)

    def _answer(self, body):
        if self.path != "/model.ckpt":
            self.send_response(404)
            self.end_headers()
            return
        start = 0
        if (rng := self.headers.get("Range", "")).startswith("bytes="):
            start = int(rng[6:].split("-")[0])
            if start >= len(DATA):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(DATA)}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(DATA) - 1}/{len(DATA)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(DATA) - start))
        self.end_headers()
        if not body:
            return
        self.server.gets += 1
        if self.server.gets <= self.server.drops:
            self.wfile.write(DATA[start:start + self.server.cut])
            self.wfile.flush()
            self.connection.shutdown(2)
            return
        self.wfile.write(DATA[start:])


@pytest.fixture
def serve():
    servers = []

    def start(**kw):
        s = Flaky(**kw)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        servers.append(s)
        return s

    yield start
    for s in servers:
        s.shutdown()


QUIET = dict(log=lambda *_: None, pause=lambda n: None)


def test_carries_on_after_drops(serve, tmp_path):
    s = serve(drops=2, cut=100_000)
    dest = str(tmp_path / "model.ckpt")
    safe_download.fetch(s.url, dest, **QUIET)
    assert Path(dest).read_bytes() == DATA
    assert s.gets == 3 and not Path(dest + ".part").exists()


def test_never_leaves_a_cut_short_model_under_its_name(serve, tmp_path):
    s = serve(drops=99, cut=50_000)
    dest = str(tmp_path / "model.ckpt")
    with pytest.raises(RuntimeError, match="after 3 tries"):
        safe_download.fetch(s.url, dest, tries=3, **QUIET)
    assert not Path(dest).exists()
    assert 0 < Path(dest + ".part").stat().st_size < len(DATA)   # kept, so the next run carries on from it


def test_repairs_a_model_an_older_download_cut_short(serve, tmp_path):
    s = serve()
    dest = tmp_path / "model.ckpt"
    dest.write_bytes(DATA[:120_000])
    safe_download.ensure(s.url, str(dest), **QUIET)
    assert dest.read_bytes() == DATA
    assert s.gets == 1   # only the rest was fetched


def test_a_checked_model_is_not_asked_about_again(serve, tmp_path):
    s = serve()
    dest = tmp_path / "model.ckpt"
    dest.write_bytes(DATA)
    safe_download.ensure(s.url, str(dest), **QUIET)   # checked against the server's size, and remembered
    s.shutdown()
    safe_download.ensure(s.url, str(dest), **QUIET)   # no server now: still fine, nothing asked
    assert dest.read_bytes() == DATA


def test_offline_trusts_a_model_it_cannot_check(tmp_path):
    dest = tmp_path / "model.ckpt"
    dest.write_bytes(b"x" * 10)
    safe_download.ensure("http://127.0.0.1:9/model.ckpt", str(dest), **QUIET)
    assert dest.read_bytes() == b"x" * 10


def test_a_part_longer_than_the_file_starts_again(serve, tmp_path):
    s = serve()
    dest = str(tmp_path / "model.ckpt")
    Path(dest + ".part").write_bytes(os.urandom(len(DATA) + 5))
    safe_download.fetch(s.url, dest, **QUIET)
    assert Path(dest).read_bytes() == DATA


def test_a_missing_file_stops_at_once(serve, tmp_path):
    s = serve()
    with pytest.raises(RuntimeError, match="404"):
        safe_download.fetch(s.url.replace("model.ckpt", "gone.ckpt"), str(tmp_path / "gone.ckpt"), **QUIET)


def test_a_url_without_the_file_says_so_so_the_other_url_is_tried(serve, tmp_path):
    # audio-separator asks a first URL that may not have the model, then its other one: both on a model already here
    s = serve()
    dest = tmp_path / "model.ckpt"
    dest.write_bytes(DATA[:120_000])
    with pytest.raises(safe_download.NotThere):
        safe_download.ensure(s.url.replace("model.ckpt", "elsewhere.ckpt"), str(dest), **QUIET)
    assert dest.read_bytes() == DATA[:120_000]                     # untouched by the URL that hasn't got it
    safe_download.ensure(s.url, str(dest), **QUIET)                # the other URL: repaired
    assert dest.read_bytes() == DATA


def test_when_no_url_has_it_the_file_here_is_used(serve, tmp_path):
    s = serve()
    dest = tmp_path / "model.ckpt"
    dest.write_bytes(b"made by hand")
    safe_download.TRUST_WHAT_IS_HERE = True
    try:
        safe_download.ensure(s.url.replace("model.ckpt", "gone.ckpt"), str(dest), **QUIET)
    finally:
        safe_download.TRUST_WHAT_IS_HERE = False
    assert dest.read_bytes() == b"made by hand"
