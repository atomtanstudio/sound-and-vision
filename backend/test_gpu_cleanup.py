import json
import threading

import httpx
import pytest

from . import gpu_cleanup
from .gpu_cleanup import VideoGpuCleanup

H3 = "http://video.test"
COMFY = "http://renderer.test"


@pytest.fixture
def cleanup(tmp_path, monkeypatch):
    state = {"provider": {"online": True, "busy": False, "activeJobId": None},
             "queue": {"queue_running": [], "queue_pending": []}, "requests": [], "queue_reads": 0}

    def respond(request):
        state["requests"].append((request.method, str(request.url), request.content))
        if str(request.url) == H3 + "/api/machine":
            return httpx.Response(200, json=state["provider"])
        if request.url.path == "/queue":
            state["queue_reads"] += 1
            if state.get("arrives") and state["queue_reads"] == 2:
                return httpx.Response(200, json={"queue_running": [[1, "other-job"]], "queue_pending": []})
            return httpx.Response(200, json=state["queue"])
        if request.url.path == "/free":
            if state.get("fail"):
                raise httpx.ConnectError("Renderer unavailable", request=request)
            if state.get("on_free"):
                state["on_free"]()
            return httpx.Response(200)
        raise AssertionError("Unexpected cleanup endpoint: " + str(request.url))

    original = httpx.Client
    monkeypatch.setattr(gpu_cleanup.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(gpu_cleanup.time, "sleep", lambda seconds: None)
    helper = VideoGpuCleanup(tmp_path, [COMFY], H3)
    monkeypatch.setattr(VideoGpuCleanup, "free_mib", staticmethod(lambda: 26000))
    return helper, state


def posts(state):
    return [(method, url, json.loads(data)) for method, url, data in state["requests"] if method == "POST"]


def test_completed_work_unloads_only_opted_in_idle_renderer(cleanup):
    helper, state = cleanup
    helper.request("film-1")
    helper.run_if_idle(threading.Lock())
    assert posts(state) == [("POST", COMFY + "/free", {"unload_models": True, "free_memory": True})]
    assert not helper.pending.exists()
    receipt = json.loads(helper.receipt.read_text())
    assert receipt["status"] == "release_requested" and receipt["sources"] == ["film-1"]
    assert receipt["free_mib_after"] == 26000


@pytest.mark.parametrize("change", [
    {"provider": {"online": True, "busy": True, "activeJobId": None}},
    {"provider": {"online": True, "busy": False, "activeJobId": "preparing-job"}},
    {"provider": {"online": False, "busy": False}},
    {"queue": {"queue_running": [[1, "other"]], "queue_pending": []}},
    {"queue": {"queue_running": [], "queue_pending": [[1, "other"]]}},
    {"queue": {}},
    {"arrives": True},
])
def test_other_work_or_unverifiable_state_keeps_cleanup_pending(cleanup, change):
    helper, state = cleanup
    state.update(change)
    helper.request("film-1")
    helper.run_if_idle(threading.Lock())
    assert posts(state) == [] and helper.pending.exists()
    assert json.loads(helper.receipt.read_text())["status"] == "deferred"


def test_local_owner_is_not_interrupted(cleanup):
    helper, state = cleanup
    helper.request("film-1")
    lock = threading.Lock()
    lock.acquire()
    helper.run_if_idle(lock)
    assert not state["requests"] and helper.pending.exists()
    lock.release()
    helper.run_if_idle(lock)
    assert len(posts(state)) == 1 and not lock.locked()


def test_network_failure_retries_after_restart_without_touching_finished_media(cleanup, tmp_path):
    helper, state = cleanup
    movie = tmp_path / "movie.mp4"
    movie.write_bytes(b"finished original")
    state["fail"] = True
    helper.request("film-1")
    lock = threading.Lock()
    helper.run_if_idle(lock)
    assert helper.pending.exists() and not lock.locked()
    state["fail"] = False
    restarted = VideoGpuCleanup(tmp_path, [COMFY], H3)
    restarted.run_if_idle(lock)
    assert not restarted.pending.exists() and movie.read_bytes() == b"finished original"


def test_later_request_is_not_lost_during_cleanup(cleanup):
    helper, state = cleanup
    helper.request("film-1")
    state["on_free"] = lambda: helper.request("film-2")
    helper.run_if_idle(threading.Lock())
    assert json.loads(helper.pending.read_text())["sources"] == ["film-2"]


def test_observed_services_are_not_implicitly_unloaded(tmp_path):
    helper = VideoGpuCleanup(tmp_path, [], H3)
    helper.request("film-1")
    helper.run_if_idle(threading.Lock())
    assert not helper.pending.exists() and not helper.receipt.exists()
