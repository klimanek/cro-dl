"""Which requests this server answers: the ones that come from itself.

Its own pages, in other words. A form post has no CORS to stop it, so every route
that writes asks this question, and the trusted-host middleware in `app.py` asks
it of every request - reads included, because a page the user visits could
otherwise read the library through their browser (a name that merely resolves to
127.0.0.1 is exactly what DNS rebinding arranges).
"""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

#: The names that mean "this machine". `[::1]` is how a browser writes the
#: address of the IPv6 loopback.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def check_same_origin(request: Request) -> None:
    """
    Refuse a write that did not come from a page on this very server.

    Two things are checked, because either alone is too weak: the request must
    have been addressed to the loopback interface (so a name that merely
    resolves to 127.0.0.1 - DNS rebinding - does not pass) and, when the browser
    sends an `Origin`, it must be this server's own origin. Comparing against
    the request's own host rather than a configured port matters: the server can
    perfectly well be started on another one.
    """
    host = request.headers.get("host", "")
    hostname = urlsplit(f"//{host}").hostname or ""

    if hostname not in LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="Not a local request")

    origin = request.headers.get("origin")

    if origin is not None and origin != f"{request.url.scheme}://{host}":
        raise HTTPException(status_code=403, detail="Cross-origin request refused")
