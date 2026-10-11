import re
from pathlib import Path

SV = Path(__file__).resolve().parent.parent / "sv"


def test_everything_the_jobs_ask_the_app_for_is_set_on_it():
    """Each part reaches the others through the app holder (self.app.<name>); a name app.py never sets fails only
    when a job gets there, mid-film."""
    given = set(re.findall(r"^APP\.(\w+)\s*=", (SV / "app.py").read_text(), re.M))
    given |= {n for line in re.findall(r"^APP\.\w+(?:\s*,\s*APP\.\w+)+\s*=", (SV / "app.py").read_text(), re.M)
              for n in re.findall(r"APP\.(\w+)", line)}
    asked = {n for f in SV.rglob("*.py") for n in re.findall(r"self\.app\.(\w+)", f.read_text())}
    assert asked - given == set()


def test_a_driver_that_needs_a_restart_is_said_plainly():
    from sv.studio import machine_trouble
    seen = ("docker: Error response from daemon: failed to create task for container: failed to create shim task: OCI "
            "runtime create failed: runc create failed: unable to start container process: error during container init: "
            "failed to fulfil mount request: open /usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.595.91.07: no such file")
    assert "restart" in machine_trouble(seen)
    assert machine_trouble("npm ERR! network timeout") is None


def test_the_web_app_never_hands_out_a_file_outside_its_folder(tmp_path):
    """The data folder, with the app's key, sits next to the web folder; the page fallback is open to the network."""
    from sv.web import web_file
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("app")
    (web / "assets" / "a.js").write_text("js")
    (tmp_path / "data" / "secrets").mkdir(parents=True)
    (tmp_path / "data" / "secrets" / "api-token").write_text("key")
    index = (web / "index.html").resolve()
    assert web_file(web, "assets/a.js") == (web / "assets" / "a.js").resolve()
    assert web_file(web, "music/abc") == index  # the app's own routes
    assert web_file(web, "") == index
    for sneaky in ("../data/secrets/api-token", "assets/../../data/secrets/api-token", str(tmp_path / "data/secrets/api-token")):
        assert web_file(web, sneaky) == index


def test_requests_must_name_this_machine_and_changes_must_come_from_its_own_page():
    from sv.guard import Guard
    g = Guard(("studio.lan",))
    for ok in ("192.168.1.100:7660", "127.0.0.1", "[::1]:7660", "localhost:7660", "studio.lan:7660"):
        assert g.known_host(ok), ok
    for bad in ("evil.example.com", "evil.example.com:7660", "192.168.1.100.evil.com", "", None):
        assert not g.known_host(bad), bad   # a page's own domain pointed at the machine (DNS rebinding)
    host = {"host": "192.168.1.100:7660"}
    assert g.same_origin({**host, "origin": "http://192.168.1.100:7660"})
    assert g.same_origin(host)  # curl, scripts: no Origin, no Referer
    assert not g.same_origin({**host, "origin": "https://evil.example.com"})
    assert not g.same_origin({**host, "origin": "null"})
    assert not g.same_origin({**host, "referer": "https://evil.example.com/page"})
