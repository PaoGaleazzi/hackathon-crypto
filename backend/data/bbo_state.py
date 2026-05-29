from __future__ import annotations

import asyncio
from collections.abc import Callable

from models.market import BBO, Exchange

# In-memory BBO state. Never touches DuckDB in the detection hot path.
_state: dict[Exchange, BBO] = {}
_connected: set[Exchange] = set()
# Lazy: created on first access so it binds to the running event loop.
_update_event: asyncio.Event | None = None
# Optional sink for every BBO update (e.g. the JSONL recorder in RECORD_MODE).
# Kept here — the single chokepoint all adapters pass through — so recording sees
# every tick without coupling the data layer to core (would be a circular import).
_listener: Callable[[BBO], None] | None = None


def get_update_event() -> asyncio.Event:
    global _update_event
    if _update_event is None:
        _update_event = asyncio.Event()
    return _update_event


def set_update_listener(listener: Callable[[BBO], None] | None) -> None:
    """Register (or clear with None) a callback invoked on every BBO update."""
    global _listener
    _listener = listener


def update(bbo: BBO) -> None:
    _state[bbo.exchange] = bbo
    _connected.add(bbo.exchange)
    if _listener is not None:
        _listener(bbo)
    if _update_event is not None:
        _update_event.set()


def get(exchange: Exchange) -> BBO | None:
    return _state.get(exchange)


def get_all() -> dict[Exchange, BBO]:
    return dict(_state)


def get_connected() -> list[str]:
    return [e.value for e in _connected]
