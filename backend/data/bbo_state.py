from __future__ import annotations

import asyncio

from models.market import BBO, Exchange

# In-memory BBO state. Never touches DuckDB in the detection hot path.
_state: dict[Exchange, BBO] = {}
_connected: set[Exchange] = set()
# Lazy: created on first access so it binds to the running event loop.
_update_event: asyncio.Event | None = None


def get_update_event() -> asyncio.Event:
    global _update_event
    if _update_event is None:
        _update_event = asyncio.Event()
    return _update_event


def update(bbo: BBO) -> None:
    _state[bbo.exchange] = bbo
    _connected.add(bbo.exchange)
    if _update_event is not None:
        _update_event.set()


def get(exchange: Exchange) -> BBO | None:
    return _state.get(exchange)


def get_all() -> dict[Exchange, BBO]:
    return dict(_state)


def get_connected() -> list[str]:
    return [e.value for e in _connected]
