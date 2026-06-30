"""Shared state untuk real-time WebSocket hub + cache quote terbaru."""
import asyncio
from typing import Set, Dict, Any
from fastapi import WebSocket

connected_ws: Set[WebSocket] = set()
# quote terbaru per symbol (dipakai untuk ticker list & snapshot WS)
latest_quote: Dict[str, Dict[str, Any]] = {}
main_loop: asyncio.AbstractEventLoop | None = None


async def broadcast(msg: dict):
    dead = set()
    for ws in connected_ws.copy():
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    connected_ws.difference_update(dead)


def push_from_thread(msg: dict):
    """Dipanggil dari Kafka consumer thread → jadwalkan broadcast di event loop."""
    if main_loop and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast(msg), main_loop)
