import asyncio
import json
import stat

import httpx
import pytest

from sv.mcp import MCPError, Servers, slug


def fake_server(key: str = "Bearer s3cret"):
    """A streamable-HTTP MCP server: a session id on initialize, tools/list answered as an event stream."""
    seen: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200)
        if request.headers.get("authorization") != key:
            return httpx.Response(401)
        msg = json.loads(request.content)
        seen.append({"method": msg.get("method"), "session": request.headers.get("mcp-session-id")})
        if msg.get("method") == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18",
                                  "capabilities": {"tools": {}}, "serverInfo": {"name": "pics"}}}, headers={"Mcp-Session-Id": "sess-1"})
        if "id" not in msg:
            return httpx.Response(202)
        if msg.get("method") == "tools/list":
            body = {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
                {"name": "make_image", "description": "Make a picture from a prompt", "inputSchema": {"type": "object"}}]}}
            return httpx.Response(200, content=f"event: message\ndata: {json.dumps(body)}\n\n".encode(),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no"}})
    return httpx.MockTransport(handle), seen


def test_a_server_is_added_its_tools_listed_and_its_key_kept_private(tmp_path):
    transport, seen = fake_server()
    servers = Servers(tmp_path / "secrets" / "mcp.json", transport=transport)
    rec = asyncio.run(servers.add("My Pictures", "https://pics.example.com/mcp", key="s3cret", paid=True))
    assert rec["ok"] and rec["tools"][0]["name"] == "make_image" and rec["header"] == "Authorization"
    assert "headers" not in rec and "s3cret" not in json.dumps(servers.listed())
    assert [s["session"] for s in seen] == [None, "sess-1", "sess-1"]  # the session id is carried after initialize
    assert stat.S_IMODE((tmp_path / "secrets" / "mcp.json").stat().st_mode) == 0o600
    cfg = asyncio.run(servers.claude_config())
    assert cfg == {"mcpServers": {"my_pictures": {"type": "http", "url": "https://pics.example.com/mcp",
                                                  "headers": {"Authorization": "Bearer s3cret"}}}}
    assert servers.allowed() == ["mcp__my_pictures"] and slug("Pics & More!") == "pics_more"


def test_a_server_that_refuses_or_isnt_one_is_not_added(tmp_path):
    transport, _ = fake_server()
    servers = Servers(tmp_path / "mcp.json", transport=transport)
    with pytest.raises(MCPError, match="refused"):
        asyncio.run(servers.add("Pics", "https://pics.example.com/mcp", key="wrong"))
    with pytest.raises(MCPError, match="https://"):
        asyncio.run(servers.add("Pics", "ftp://pics.example.com"))
    assert servers.listed() == []


def oauth_world():
    """An MCP server behind MCP's OAuth: protected-resource metadata, a sign-in service with registration and PKCE."""
    import base64, hashlib
    from urllib.parse import parse_qs
    state = {"codes": {}, "issued": 0, "registered": []}

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://pics.example.com/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(200, json={"resource": "https://pics.example.com/mcp", "authorization_servers": ["https://auth.example.com/v1"],
                                             "scopes_supported": ["mcp:tools"]})
        if url == "https://auth.example.com/.well-known/oauth-authorization-server/v1":
            return httpx.Response(200, json={"issuer": "https://auth.example.com/v1", "authorization_endpoint": "https://auth.example.com/authorize",
                                             "token_endpoint": "https://auth.example.com/token", "registration_endpoint": "https://auth.example.com/register",
                                             "code_challenge_methods_supported": ["S256"]})
        if url == "https://auth.example.com/register":
            body = json.loads(request.content)
            state["registered"].append(body)
            return httpx.Response(201, json={"client_id": "client-1"})
        if url == "https://auth.example.com/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if form["grant_type"] == "authorization_code":
                want = state["codes"].get(form["code"])
                got = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                if want != got or form["resource"] != "https://pics.example.com/mcp":
                    return httpx.Response(400, json={"error": "invalid_grant"})
            state["issued"] += 1
            return httpx.Response(200, json={"access_token": f"tok-{state['issued']}", "refresh_token": "ref", "expires_in": 3600})
        if url.startswith("https://pics.example.com/mcp"):
            if not request.headers.get("authorization", "").startswith("Bearer tok-"):
                return httpx.Response(401, headers={"www-authenticate": 'Bearer resource_metadata="https://pics.example.com/.well-known/oauth-protected-resource/mcp"'})
            if request.method == "DELETE":
                return httpx.Response(200)
            msg = json.loads(request.content)
            if "id" not in msg:
                return httpx.Response(202)
            result = {"tools": [{"name": "make_image", "description": "x"}]} if msg["method"] == "tools/list" else {}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": result})
        return httpx.Response(404)
    return httpx.MockTransport(handle), state


def test_a_server_that_wants_a_sign_in_is_signed_in_with_pkce_and_its_tokens_renewed(tmp_path):
    from urllib.parse import parse_qs, urlparse
    transport, world = oauth_world()
    servers = Servers(tmp_path / "mcp.json", transport=transport)

    async def https_only(url, allow_host=None):  # (no DNS in tests: the scheme rule only)
        from sv.net import UnsafeURL
        if not url.startswith("https://"):
            raise UnsafeURL("Only https addresses are fetched.")
    servers.vet = https_only

    async def go():
        rec = await servers.add("Pics", "https://pics.example.com/mcp")
        assert rec["needsSignIn"] and rec["signIn"] and not rec["signedIn"] and not rec["ok"]
        url = await servers.begin_signin(rec["id"], "http://192.168.1.5:7660/api/mcp/oauth/callback")
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert url.startswith("https://auth.example.com/authorize?") and q["code_challenge_method"] == "S256"
        assert q["client_id"] == "client-1" and q["resource"] == "https://pics.example.com/mcp" and q["scope"] == "mcp:tools"
        assert world["registered"][0]["redirect_uris"] == ["http://192.168.1.5:7660/api/mcp/oauth/callback"]
        assert servers.waiting(q["state"]) == rec["id"]
        world["codes"]["the-code"] = q["code_challenge"]  # the person approved it
        done = await servers.finish_from_address(f"http://localhost:7660/api/mcp/oauth/callback?code=the-code&state={q['state']}")
        assert done["ok"] and done["signedIn"] and done["tools"][0]["name"] == "make_image"
        assert "tok-" not in json.dumps(servers.listed()) and "client-1" not in json.dumps(servers.listed())
        with pytest.raises(MCPError, match="isn't one this app started"):
            await servers.finish_signin(q["state"], "the-code")  # a state is good once
        cfg = await servers.claude_config()
        assert cfg["mcpServers"]["pics"]["headers"] == {"Authorization": "Bearer tok-1"}
        saved = json.loads((tmp_path / "mcp.json").read_text())  # the token runs out: renewed before it's handed on
        saved[0]["tokens"]["expiresAt"] = 0
        (tmp_path / "mcp.json").write_text(json.dumps(saved))
        cfg = await servers.claude_config()
        assert cfg["mcpServers"]["pics"]["headers"] == {"Authorization": "Bearer tok-2"}
        assert servers.sign_out(rec["id"])["signedIn"] is False and (await servers.claude_config())["mcpServers"] == {}
    asyncio.run(go())


def test_a_server_can_be_kept_from_claude_while_it_directs_unless_chosen_for_the_film(tmp_path):
    transport, _ = fake_server()
    servers = Servers(tmp_path / "mcp.json", transport=transport)
    a = asyncio.run(servers.add("Pics", "https://pics.example.com/mcp", key="s3cret"))
    assert servers.for_directing() == [a["id"]]  # on unless turned off
    servers.update(a["id"], director=False)
    assert servers.for_directing() == [] and servers.for_directing([a["id"]]) == [a["id"]]


def test_a_sign_in_service_that_names_unsafe_addresses_is_refused():
    import ipaddress
    from sv import net

    async def go():
        for bad in ("javascript:alert(1)//", "http://example.com/token", "https://127.0.0.1/token", "https://192.168.1.1/x",
                    "https://169.254.169.254/latest", "https://[::1]/x"):
            with pytest.raises(net.UnsafeURL):
                await net.check(bad)
        await net.check("http://192.168.1.50:8080/authorize", allow_host="192.168.1.50")  # the person's own server
        with pytest.raises(net.UnsafeURL):
            await net.check("http://192.168.1.51/token", allow_host="192.168.1.50")
    asyncio.run(go())
