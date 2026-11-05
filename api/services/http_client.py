"""
One shared outbound HTTP client per event loop.

`httpx.AsyncClient()` loads the system's TLS certificates synchronously when it
is built: 200-450 ms on this laptop, on the event loop. Building one per
request froze everything the loop serves for that long, including every live
view's video WebSocket, so the picture hitched each time a casualty raised an
alert. The client here is built once, off the loop, and reused (which also
keeps connections alive between requests). Pass per-request settings
(timeout, headers) to the request call.

Keyed by loop because a client's connection pool belongs to the loop that
opened it; tests run each case in a fresh loop.
"""
from __future__ import annotations

import asyncio
import weakref

import httpx

_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()


async def get_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        built = await asyncio.to_thread(httpx.AsyncClient, timeout=10.0)
        # Another caller may have built one while this one was building.
        client = _clients.get(loop)
        if client is None or client.is_closed:
            client = _clients[loop] = built
        else:
            await built.aclose()
    return client
