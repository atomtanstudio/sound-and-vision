import asyncio
import json
import sys
from pathlib import Path

import pytest

from sv.writers.openai import ChatGPT
from sv.writers.providers import WriterError

FAKE = Path(__file__).parent / "fakes" / "fake_codex.py"


@pytest.fixture
def chatgpt(tmp_path, monkeypatch):
    shim = tmp_path / "codex"
    shim.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    shim.chmod(0o755)
    monkeypatch.setenv("FAKE_CODEX_LOG", str(tmp_path / "requests.log"))
    return ChatGPT(shim, tmp_path / "accounts" / "codex-home")


def sent(tmp_path, method):
    return [m["params"] for m in map(json.loads, (tmp_path / "requests.log").read_text().splitlines()) if m.get("method") == method]


async def signed_in(c: ChatGPT) -> dict:
    st = await c.begin_login()
    assert st["login"]["code"] == "ABCD-1234" and st["login"]["url"].startswith("https://auth.openai.com/")
    for _ in range(50):
        await asyncio.sleep(0.05)
        st = await c.status()
        if st["connected"]:
            return st
    raise AssertionError("never signed in")


def test_sign_in_write_paint_and_sign_out(chatgpt, tmp_path):
    async def go():
        assert (await chatgpt.status())["connected"] is False
        st = await signed_in(chatgpt)
        assert st["account"] == "you@example.com"
        assert st["models"][0]["efforts"] == ["low", "medium", "high"]
        # a turn with the model's own reasoning level, and every tool switched off
        assert await chatgpt.complete("You write.", "Say ok.", {"type": "object"}, effort="high") == {"ok": True}
        assert sent(tmp_path, "turn/start")[-1]["effort"] == "high"
        assert sent(tmp_path, "thread/start")[-1]["config"]["features"]["shell_tool"] is False
        # a picture: ChatGPT's image tool on for that turn only; Codex's own copy is removed
        picture = await chatgpt.picture("a lighthouse", shape="16:9")
        assert picture.startswith(b"\x89PNG")
        assert sent(tmp_path, "thread/start")[-1]["config"]["features"]["image_generation"] is True
        assert "16:9 landscape" in sent(tmp_path, "turn/start")[-1]["input"][0]["text"]
        assert not any((chatgpt.home / "generated_images").glob("*"))
        # anything that isn't text is stopped
        with pytest.raises(WriterError, match="tool"):
            await chatgpt.complete("You write.", "TOOL please", {"type": "object"})
        assert sent(tmp_path, "turn/interrupt")
        assert (await chatgpt.logout())["connected"] is False
        await chatgpt.close()
    asyncio.run(go())


def test_not_installed_says_how(tmp_path):
    st = asyncio.run(ChatGPT(tmp_path / "missing-codex", tmp_path / "home").status())
    assert st["installed"] is False and st["canSignIn"] is True
