"""What else a request must show, besides being let in (an open network, or the key): it's addressed to this machine
by a name it knows (an IP address, localhost, the machine's own name, or SV_HOSTS), so a web page can't reach the app
through a domain of its own pointed at the machine (DNS rebinding); and a request that changes something comes from
the app's own page, so another site can't make a browser on the home network send one (cross-site request forgery).
Scripts and the development proxy send no Origin, or carry the key as a bearer header, and aren't affected."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class Guard:
    def __init__(self, hosts: tuple[str, ...] = ()):
        name = socket.gethostname().lower()
        short = name.split(".")[0]
        self.names = {"localhost", name, short, f"{short}.local", *(h.strip().lower() for h in hosts if h.strip())}

    def known_host(self, host: str | None) -> bool:
        """The Host header names this machine: an IP address or a name it knows (the port doesn't matter)."""
        h = (host or "").strip().lower()
        if not h:
            return False
        if h.startswith("["):  # [IPv6]:port
            h = h[1:h.find("]")] if "]" in h else h
        elif h.count(":") == 1:
            h = h.rsplit(":", 1)[0]
        try:
            ipaddress.ip_address(h)
            return True
        except ValueError:
            return h in self.names

    @staticmethod
    def same_origin(headers) -> bool:
        """The request comes from a page the app served (or from something that isn't a browser page at all)."""
        origin = headers.get("origin")
        if origin is None:
            ref = headers.get("referer")
            if not ref:
                return True  # a script, curl, the dev proxy: not a forged browser request
            origin = ref
        if origin == "null":  # a sandboxed or file page
            return False
        return urlparse(origin).netloc.lower() == (headers.get("host") or "").strip().lower()
