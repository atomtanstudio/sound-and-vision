"""Fetching from addresses the app was handed (a picture's URL from an image service, a sign-in service's endpoints from
an MCP server's own description): only https, only to public hosts, and every redirect checked again, so an address
can't steer the server at the home network or the machine itself."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx


class UnsafeURL(Exception):
    """The address isn't one the app will fetch: not https, or a host on a private network."""


async def check(url: str, allow_host: str | None = None) -> None:
    """Https to a public host; or, for `allow_host` (an MCP server on the home network the person added themselves),
    that host by http or https."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if not host:
        raise UnsafeURL("That isn't a web address.")
    if allow_host and host == allow_host.lower() and u.scheme in ("http", "https"):
        return
    if u.scheme != "https":
        raise UnsafeURL("Only https addresses are fetched.")
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, u.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        raise UnsafeURL(f"{host} couldn't be found.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeURL(f"{host} is on a private network.")


async def get(url: str, *, most: int, timeout: float = 120, hops: int = 5) -> httpx.Response:
    """GET a public https address, following at most `hops` redirects, each checked; the body up to `most` bytes."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as http:
        for _ in range(hops + 1):
            await check(url)
            async with http.stream("GET", url) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > most:
                        raise UnsafeURL("That file is too big.")
                return httpx.Response(r.status_code, headers=r.headers, content=bytes(body), request=r.request)
    raise UnsafeURL("Too many redirects.")


async def download(url: str, dest, *, most: int, timeout: httpx.Timeout | float = 120, hops: int = 5) -> int:
    """Stream a public https address to `dest`, redirects checked; returns the final status (the file is written only
    on 200). Raises UnsafeURL past `most` bytes."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as http:
        for _ in range(hops + 1):
            await check(url)
            async with http.stream("GET", url) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                if r.status_code != 200:
                    return r.status_code
                size = 0
                with open(dest, "wb") as out:
                    async for chunk in r.aiter_bytes(1 << 20):
                        size += len(chunk)
                        if size > most:
                            raise UnsafeURL("That file is too big.")
                        out.write(chunk)
                return 200
    raise UnsafeURL("Too many redirects.")
