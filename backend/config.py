from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8080
    db_path: str = "/tmp/arbitrage.db"
    version: str = "0.1.0"

    min_profit_usd: float = 1.0
    min_fill_ratio: float = 0.3
    stale_quote_ms: int = 500
    min_trade_size_btc: float = 0.001  # exchange minimum order size; single source of truth

    circuit_breaker_threshold: float = 0.0005
    circuit_breaker_cooldown_s: int = 30

    demo_mode: bool = False

    # When true, every normalized BBO update is appended to a JSONL recording for
    # later deterministic replay / A-B testing (see scripts/ab_test.py). Off by
    # default — recording adds buffered file I/O to the hot path, so it is a
    # dataset-capture mode, not for production trading.
    record_mode: bool = False
    record_path: str = "data/recordings/market_data.jsonl"


settings = Settings()
