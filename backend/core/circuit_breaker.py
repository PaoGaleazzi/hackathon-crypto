from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from enum import Enum

from models.trade import Trade

logger = logging.getLogger(__name__)

STALE_THRESHOLD = 3          # consecutive ABORTED_STALE before opening
LOSS_WINDOW_SECS = 300       # 5-minute rolling window
LOSS_THRESHOLD_USD = 50.0    # net loss in window that trips the breaker
COOLDOWN_SECS = 60           # OPEN → HALF_OPEN after this many seconds


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Three-state circuit breaker for the arbitrage execution pipeline.

    Trip conditions (CLOSED → OPEN):
      - 3 consecutive ABORTED_STALE trades
      - Net loss > $50 in any rolling 5-minute window

    Recovery path:
      OPEN → (60s cooldown) → HALF_OPEN → (one successful trade) → CLOSED
      HALF_OPEN → (any failure) → OPEN (timer resets)
    """

    def __init__(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_stale = 0
        self._loss_window: deque[tuple[datetime, float]] = deque()
        self._opened_at: datetime | None = None

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def allow_trade(self, now: datetime | None = None) -> bool:
        """Return True when the pipeline may proceed (CLOSED or HALF_OPEN)."""
        self._maybe_transition(now or datetime.now(timezone.utc))
        return self._state != CircuitBreakerState.OPEN

    def record_trade(self, trade: Trade, now: datetime | None = None) -> bool:
        """
        Update internal counters based on trade outcome.
        Returns True if the breaker just tripped (CLOSED/HALF_OPEN → OPEN).
        """
        _now = now or datetime.now(timezone.utc)
        self._maybe_transition(_now)
        self._evict_stale(_now)

        if trade.status == "ABORTED_STALE":
            self._consecutive_stale += 1
        else:
            self._consecutive_stale = 0

        if trade.net_profit < 0:
            self._loss_window.append((_now, trade.net_profit))

        if self._state == CircuitBreakerState.CLOSED:
            stale_trip = self._consecutive_stale >= STALE_THRESHOLD
            loss_trip = self._rolling_loss() <= -LOSS_THRESHOLD_USD
            if stale_trip or loss_trip:
                self._open(_now, reason="stale" if stale_trip else "loss")
                return True

        elif self._state == CircuitBreakerState.HALF_OPEN:
            if trade.status == "EXECUTED":
                self._close()
            else:
                self._open(_now, reason="failed probe")
                return True

        return False

    def countdown_secs(self, now: datetime | None = None) -> float | None:
        """Seconds remaining until OPEN transitions to HALF_OPEN. None when not OPEN."""
        if self._state != CircuitBreakerState.OPEN or self._opened_at is None:
            return None
        _now = now if now is not None else datetime.now(timezone.utc)
        elapsed = (_now - self._opened_at).total_seconds()
        return max(0.0, COOLDOWN_SECS - elapsed)

    def as_dict(self, now: datetime | None = None) -> dict:
        _now = now or datetime.now(timezone.utc)
        return {
            "state": self._state.value,
            "consecutive_stale": self._consecutive_stale,
            "rolling_loss_usd": round(self._rolling_loss(), 4),
            "countdown_secs": self.countdown_secs(_now),
        }

    # ── private helpers ───────────────────────────────────────────────────────

    def _open(self, now: datetime, *, reason: str) -> None:
        self._state = CircuitBreakerState.OPEN
        self._opened_at = now
        logger.warning("Circuit breaker OPEN (%s)", reason)

    def _close(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_stale = 0
        self._loss_window.clear()
        self._opened_at = None
        logger.info("Circuit breaker CLOSED (recovered)")

    def _maybe_transition(self, now: datetime) -> None:
        """OPEN → HALF_OPEN after cooldown expires."""
        if (
            self._state == CircuitBreakerState.OPEN
            and self._opened_at is not None
            and (now - self._opened_at).total_seconds() >= COOLDOWN_SECS
        ):
            self._state = CircuitBreakerState.HALF_OPEN
            logger.info("Circuit breaker HALF_OPEN (probing)")

    def _evict_stale(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=LOSS_WINDOW_SECS)
        while self._loss_window and self._loss_window[0][0] < cutoff:
            self._loss_window.popleft()

    def _rolling_loss(self) -> float:
        return sum(p for _, p in self._loss_window)


# ── module-level singleton ────────────────────────────────────────────────────

_instance: CircuitBreaker | None = None


def get_circuit_breaker() -> CircuitBreaker:
    global _instance
    if _instance is None:
        _instance = CircuitBreaker()
    return _instance
