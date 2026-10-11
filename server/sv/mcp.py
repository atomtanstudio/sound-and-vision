"""Your MCP servers: tools from other services (pictures, video, anything) that the app and Claude can use.

You add a server by its address (the streamable HTTP transport; most hosted servers speak it) with, if it needs one, a
key sent as a header, or you sign in to it in the browser (MCP's own OAuth: the server names its sign-in service, the
app registers itself there, and the sign-in uses PKCE; tokens are renewed as they run out). The list is kept in
data/secrets/mcp.json (0600): a key or a token is never sent back to a browser. The app
connects to list a server's tools, and hands the servers to Claude (Claude Code's --mcp-config) so it can use them:
while it directs a video, or to make a picture when a server is chosen for pictures (Settings → Pictures).

A server that costs money is marked "paid": the interface asks before each job that would use it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlparse
from pathlib import Path
from typing import Any

import httpx

from . import net

PROTOCOL = "2025-06-18"
CLIENT = {"name": "sound-vision", "title": "Sound / Vision", "version": "1.0.0"}


class MCPError(Exception):
    """Something the user should read: the server didn't answer, refused the key, or isn't an MCP server."""


class NeedsSignIn(MCPError):
    """The server wants a sign-in (401): `metadata` is where its protected-resource metadata is, if it said."""

    def __init__(self, metadata: str | None):
        super().__init__("The server needs you to sign in.")
        self.metadata = metadata


def slug(name: str) -> str:
    """The name Claude Code knows a server by (its tools are mcp__<slug>__<tool>)."""
    return re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_-")[:40] or "server"


class Session:
    """One conversation with a streamable-HTTP MCP server: JSON-RPC by POST, answers as JSON or as an event stream."""

    def __init__(self, url: str, headers: dict[str, str], timeout: float = 30, transport: httpx.AsyncBaseTransport | None = None):
        self.url, self.headers = url, headers
        self.http = httpx.AsyncClient(timeout=timeout, follow_redirects=True, transport=transport)
        self.session: str | None = None
        self.n = 0

    async def __aenter__(self) -> "Session":
        await self.call("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT})
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self.session:
            try:
                await self.http.delete(self.url, headers=self._headers())
            except httpx.HTTPError:
                pass
        await self.http.aclose()

    def _headers(self) -> dict[str, str]:
        return {**self.headers, "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL,
                **({"Mcp-Session-Id": self.session} if self.session else {})}

    async def _post(self, msg: dict) -> dict | None:
        try:
            async with self.http.stream("POST", self.url, json=msg, headers=self._headers()) as r:
                if r.status_code == 401 and not self.headers.get("Authorization"):
                    m = re.search(r'resource_metadata="([^"]+)"', r.headers.get("www-authenticate", ""))
                    raise NeedsSignIn(m.group(1) if m else None)
                if r.status_code in (401, 403):
                    raise MCPError("The server refused the key or the sign-in.")
                if r.status_code == 404 and self.session:
                    raise MCPError("The server ended the session.")
                if r.status_code >= 400:
                    raise MCPError(f"The server answered {r.status_code}.")
                self.session = r.headers.get("mcp-session-id") or self.session
                if "id" not in msg:
                    return None
                kind = r.headers.get("content-type", "")
                if kind.startswith("text/event-stream"):
                    data: list[str] = []
                    async for line in r.aiter_lines():
                        if line.startswith("data:"):
                            data.append(line[5:].strip())
                        elif not line.strip() and data:  # one event
                            got = _json("\n".join(data))
                            data = []
                            if isinstance(got, dict) and got.get("id") == msg["id"]:
                                return got
                    return _json("\n".join(data)) if data else None
                return _json(await r.aread())
        except httpx.HTTPError as exc:
            raise MCPError(f"The server didn't answer ({type(exc).__name__}).") from None

    async def call(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        got = await self._post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        if not isinstance(got, dict):
            raise MCPError("That address didn't answer like an MCP server.")
        if got.get("error"):
            raise MCPError(str((got["error"] or {}).get("message") or "The server said no."))
        return got.get("result") or {}

    async def tools(self) -> list[dict]:
        out, cursor = [], None
        for _ in range(20):
            page = await self.call("tools/list", {"cursor": cursor} if cursor else {})
            out += page.get("tools") or []
            cursor = page.get("nextCursor")
            if not cursor:
                break
        return out


def _json(raw: bytes | str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        raise MCPError("That address didn't answer like an MCP server.") from None


class Servers:
    def __init__(self, file: Path, transport: httpx.AsyncBaseTransport | None = None):
        self.file, self.transport = file, transport  # (a transport only in tests)
        self.vet = net.check  # every address a server's own description hands us (sv/net.py)

    # ---- the list ----------------------------------------------------------------------------
    def _read(self) -> list[dict]:
        try:
            return json.loads(self.file.read_text())
        except (OSError, ValueError):
            return []

    def _write(self, servers: list[dict]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.parent.chmod(0o700)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(servers, indent=1))
        tmp.chmod(0o600)
        tmp.replace(self.file)

    def get(self, sid: str) -> dict | None:
        return next((s for s in self._read() if s["id"] == sid), None)

    def listed(self) -> list[dict]:
        """For the interface: everything but keys and tokens."""
        return [self._public(s) for s in self._read()]

    async def add(self, name: str, url: str, header: str = "", key: str = "", paid: bool = True) -> dict:
        name, url = " ".join(name.split())[:40], url.strip()
        if not name:
            raise MCPError("Give the server a name.")
        if not re.match(r"^https?://\S+$", url):
            raise MCPError("The address must start with https:// (or http:// on your own network).")
        servers = self._read()
        if any(slug(s["name"]) == slug(name) for s in servers):
            raise MCPError("There's already a server with that name.")
        header = header.strip() or ("Authorization" if key.strip() else "")
        if header and not re.fullmatch(r"[A-Za-z0-9-]{1,60}", header):
            raise MCPError("That header name isn't valid.")
        value = key.strip()
        if header.lower() == "authorization" and value and " " not in value:
            value = f"Bearer {value}"
        rec = {"id": uuid.uuid4().hex[:10], "name": name, "url": url, "headers": {header: value} if header and value else {},
               "paid": bool(paid), "added": time.time()}
        rec |= await self._check(rec)
        if not rec.get("ok") and not rec.get("needsSignIn"):
            raise MCPError(rec.get("error") or "That server didn't answer.")
        self._write([*servers, rec])  # (one that needs a sign-in is kept: the interface signs in next)
        return self._public(rec)

    def update(self, sid: str, paid: bool | None = None, director: bool | None = None) -> dict:
        servers = self._read()
        rec = next((s for s in servers if s["id"] == sid), None)
        if rec is None:
            raise MCPError("There's no such server.")
        if paid is not None:
            rec["paid"] = bool(paid)
        if director is not None:
            rec["director"] = bool(director)
        self._write(servers)
        return self._public(rec)

    def remove(self, sid: str) -> None:
        self._write([s for s in self._read() if s["id"] != sid])

    async def check(self, sid: str) -> dict:
        servers = self._read()
        rec = next((s for s in servers if s["id"] == sid), None)
        if rec is None:
            raise MCPError("There's no such server.")
        rec |= await self._check(rec)
        self._write(servers)
        return self._public(rec)

    async def _check(self, rec: dict) -> dict:
        """Connect and list its tools: {ok, tools: [{name, description}], checked, error, needsSignIn}."""
        try:
            async with Session(rec["url"], await self._headers(rec), transport=self.transport) as s:
                tools = await s.tools()
            return {"ok": True, "error": None, "needsSignIn": False, "checked": time.time(),
                    "tools": [{"name": t.get("name", ""), "description": (t.get("description") or "")[:300]} for t in tools]}
        except NeedsSignIn as exc:
            if rec.get("headers"):
                return {"ok": False, "error": "The server refused the key.", "checked": time.time()}
            return {"ok": False, "needsSignIn": True, "error": "Sign in to use it.", "checked": time.time(),
                    "oauth": {**(rec.get("oauth") or {}), "metadataUrl": exc.metadata}, "tokens": None}
        except MCPError as exc:
            return {"ok": False, "error": str(exc), "checked": time.time()}

    @staticmethod
    def _public(rec: dict) -> dict:
        out = {k: v for k, v in rec.items() if k not in ("headers", "tokens", "oauth")}
        return out | {"header": next(iter(rec.get("headers") or {}), None),
                      "signIn": "oauth" in rec, "signedIn": bool(rec.get("tokens"))}

    # ---- signing in (MCP's OAuth: protected-resource metadata, client registration, PKCE) -------------------
    async def _headers(self, rec: dict) -> dict[str, str]:
        """What to send: its key, or a sign-in token (renewed first when it's about to run out)."""
        tokens = rec.get("tokens")
        if not tokens:
            return dict(rec.get("headers") or {})
        if tokens.get("expiresAt") is not None and tokens["expiresAt"] < time.time() + 60 and tokens.get("refresh"):
            tokens = await self._refresh(rec)
        return {"Authorization": f"Bearer {tokens['access']}"}

    async def _discover(self, rec: dict) -> dict:
        """The server's sign-in service: its resource name and the service's own metadata."""
        o = rec.get("oauth") or {}
        if o.get("server"):
            return o
        base = urlparse(rec["url"])
        mine = base.hostname  # the server the person added: its own host may be on their network; nothing else may
        where = o.get("metadataUrl") or f"{base.scheme}://{base.netloc}/.well-known/oauth-protected-resource{base.path.rstrip('/')}"
        async with httpx.AsyncClient(timeout=20, transport=self.transport, follow_redirects=False) as http:
            try:
                await self.vet(where, mine)
                res = (await http.get(where)).json()
                issuer = (res.get("authorization_servers") or [None])[0]
                if not issuer:
                    raise MCPError("The server doesn't say where to sign in.")
                await self.vet(issuer, mine)
                iss = urlparse(issuer)
                tries = [f"{iss.scheme}://{iss.netloc}/.well-known/oauth-authorization-server{iss.path.rstrip('/')}",
                         f"{iss.scheme}://{iss.netloc}/.well-known/openid-configuration{iss.path.rstrip('/')}",
                         f"{issuer.rstrip('/')}/.well-known/oauth-authorization-server"]
                meta = None
                for t in tries:
                    r = await http.get(t)
                    if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                        meta = r.json()
                        break
            except net.UnsafeURL as exc:
                raise MCPError(f"The server's sign-in service isn't one the app will use: {exc}") from None
            except (httpx.HTTPError, ValueError):
                raise MCPError("Couldn't reach the server's sign-in service.") from None
        if not meta or not meta.get("authorization_endpoint") or not meta.get("token_endpoint"):
            raise MCPError("The server's sign-in service didn't describe itself.")
        for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):  # (a javascript: address, or
            if meta.get(key):                                                                # one on the home network)
                try:
                    await self.vet(str(meta[key]), mine)
                except net.UnsafeURL as exc:
                    raise MCPError(f"The server's sign-in service gave an address the app won't use: {exc}") from None
        if "S256" not in (meta.get("code_challenge_methods_supported") or ["S256"]):
            raise MCPError("The server's sign-in service doesn't support PKCE (S256).")
        return {"metadataUrl": where, "resource": res.get("resource") or rec["url"], "server": meta,
                "scopes": res.get("scopes_supported") or meta.get("scopes_supported") or []}

    async def begin_signin(self, sid: str, redirect: str) -> str:
        """The address to sign in at (opened in the person's browser). `redirect` is where the browser comes back."""
        servers = self._read()
        rec = next((x for x in servers if x["id"] == sid), None)
        if rec is None or "oauth" not in rec:
            raise MCPError("That server doesn't sign in this way.")
        o = await self._discover(rec)
        meta = o["server"]
        if not o.get("client") or o["client"].get("redirect") != redirect:  # register this app once per return address
            if not meta.get("registration_endpoint"):
                raise MCPError("The server's sign-in service doesn't let apps register themselves.")
            async with httpx.AsyncClient(timeout=20, transport=self.transport) as http:
                try:
                    r = await http.post(meta["registration_endpoint"], json={
                        "client_name": "Sound / Vision", "redirect_uris": [redirect], "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": " ".join(o["scopes"])})
                    reg = r.json()
                except (httpx.HTTPError, ValueError):
                    raise MCPError("The sign-in service didn't answer the app's registration.") from None
            if r.status_code >= 400 or not reg.get("client_id"):
                raise MCPError(f"The sign-in service refused the app's registration: {reg.get('error_description') or reg.get('error') or r.status_code}")
            o["client"] = {"id": reg["client_id"], "secret": reg.get("client_secret"), "redirect": redirect}
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(24)
        o["pending"] = {"state": state, "verifier": verifier, "at": time.time()}
        rec["oauth"] = o
        self._write(servers)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        q = {"response_type": "code", "client_id": o["client"]["id"], "redirect_uri": redirect, "state": state,
             "code_challenge": challenge, "code_challenge_method": "S256", "resource": o["resource"]}
        if o["scopes"]:
            q["scope"] = " ".join(o["scopes"])
        return meta["authorization_endpoint"] + ("&" if "?" in meta["authorization_endpoint"] else "?") + urlencode(q)

    def waiting(self, state: str) -> str | None:
        """Which server a sign-in that came back with this state belongs to."""
        return next((x["id"] for x in self._read() if ((x.get("oauth") or {}).get("pending") or {}).get("state") == state), None)

    async def finish_signin(self, state: str, code: str) -> dict:
        servers = self._read()
        rec = next((x for x in servers if ((x.get("oauth") or {}).get("pending") or {}).get("state") == state), None)
        if rec is None:
            raise MCPError("That sign-in isn't one this app started (or it was already used).")
        o = rec["oauth"]
        pending = o.pop("pending")
        if time.time() - pending["at"] > 900:
            self._write(servers)
            raise MCPError("That sign-in took too long. Start it again.")
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": o["client"]["redirect"],
                "client_id": o["client"]["id"], "code_verifier": pending["verifier"], "resource": o["resource"]}
        rec["tokens"] = await self._token(o, form)
        rec |= await self._check(rec)
        self._write(servers)
        return self._public(rec)

    async def finish_from_address(self, address: str) -> dict:
        """The address the browser ended on, pasted (when it couldn't come back to the app by itself)."""
        q = parse_qs(urlparse(address.strip()).query)
        if q.get("error"):
            raise MCPError(f"The sign-in didn't go through: {q.get('error_description', q['error'])[0]}")
        if not q.get("code") or not q.get("state"):
            raise MCPError("That address doesn't carry a sign-in code.")
        return await self.finish_signin(q["state"][0], q["code"][0])

    async def _token(self, o: dict, form: dict) -> dict:
        if o["client"].get("secret"):
            form["client_secret"] = o["client"]["secret"]
        async with httpx.AsyncClient(timeout=20, transport=self.transport) as http:
            try:
                r = await http.post(o["server"]["token_endpoint"], data=form, headers={"Accept": "application/json"})
                got = r.json()
            except (httpx.HTTPError, ValueError):
                raise MCPError("The sign-in service didn't answer.") from None
        if r.status_code >= 400 or not got.get("access_token"):
            raise MCPError(f"The sign-in service said no: {got.get('error_description') or got.get('error') or r.status_code}")
        return {"access": got["access_token"], "refresh": got.get("refresh_token") or form.get("refresh_token"),
                "expiresAt": time.time() + float(got["expires_in"]) if got.get("expires_in") else None}

    async def _refresh(self, rec: dict) -> dict:
        servers = self._read()
        cur = next((x for x in servers if x["id"] == rec["id"]), rec)
        o = cur["oauth"]
        try:
            cur["tokens"] = await self._token(o, {"grant_type": "refresh_token", "refresh_token": cur["tokens"]["refresh"],
                                                  "client_id": o["client"]["id"], "resource": o["resource"]})
        except MCPError:
            cur["tokens"] = None  # signed out at their end: sign in again
            self._write(servers)
            raise MCPError("The sign-in ran out: sign in to the server again.") from None
        self._write(servers)
        rec["tokens"] = cur["tokens"]
        return cur["tokens"]

    def sign_out(self, sid: str) -> dict:
        servers = self._read()
        rec = next((x for x in servers if x["id"] == sid), None)
        if rec is None:
            raise MCPError("There's no such server.")
        rec["tokens"], rec["ok"] = None, False
        self._write(servers)
        return self._public(rec)

    # ---- for Claude ---------------------------------------------------------------------------
    def _usable(self, ids: list[str] | None) -> list[dict]:
        return [s for s in self._read() if (ids is None or s["id"] in ids) and (s.get("tokens") or "oauth" not in s)]

    def for_directing(self, also: list[str] = ()) -> list[str]:
        """The servers a film's Claude session gets: those the person lets Claude use while directing (on unless they
        turned it off), and any chosen for that film's pictures or clips."""
        return [s["id"] for s in self._read() if s.get("director", True) or s["id"] in also]

    async def claude_config(self, ids: list[str] | None = None) -> dict:
        """Claude Code's --mcp-config for these servers (all of them when `ids` is None; one that needs a sign-in is
        left out). Sign-in tokens are renewed first, so they last the run."""
        out = {}
        for s in self._usable(ids):
            try:
                headers = await self._headers(s)
            except MCPError:
                continue
            out[slug(s["name"])] = {"type": "http", "url": s["url"], **({"headers": headers} if headers else {})}
        return {"mcpServers": out}

    def allowed(self, ids: list[str] | None = None) -> list[str]:
        """Claude Code's --allowedTools entries that let it use every tool of these servers."""
        return [f"mcp__{slug(s['name'])}" for s in self._usable(ids)]
