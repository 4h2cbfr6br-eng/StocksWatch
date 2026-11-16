"""Builds the list of US stocks worth scanning, and downloads their history.

Deliberately a WIDE net (price >= $2, >= $3m traded on the latest day). The
real filters (price >= $5, >= $20m a day) are applied later, day by day, using
only what was known on each day.
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd

from . import config, providers
from .providers.alpaca import AlpacaProvider
from .providers.finnhub import FinnhubProvider

KEEP_TYPES = ("Common Stock", "ADR")   # no ETFs, funds, warrants, units, preference shares
WIDE_MIN_PRICE = 2.0
WIDE_MIN_DOLLAR_VOLUME = 3_000_000
BATCH = 100                            # symbols per history request


def _alpaca() -> AlpacaProvider:
    provider = providers.bars_provider("US")
    if not isinstance(provider, AlpacaProvider):
        raise RuntimeError("Alpaca keys are missing from .env; the whole-market steps need them.")
    return provider


def build() -> pd.DataFrame:
    alpaca = _alpaca()
    assets = pd.DataFrame(alpaca.list_assets())

    types = FinnhubProvider(os.getenv("FINNHUB_API_KEY") or "").get_symbol_types()
    if not types:
        raise RuntimeError("Could not load security types from Finnhub (check FINNHUB_API_KEY).")
    assets["type"] = assets["symbol"].map(types)
    assets = assets[assets["type"].isin(KEEP_TYPES)]

    snapshots = alpaca.get_snapshots(assets["symbol"].tolist())
    price, dollar_volume = {}, {}
    for symbol, snap in snapshots.items():
        bar = (snap or {}).get("dailyBar") or {}
        if bar.get("c") and bar.get("v"):
            price[symbol] = bar["c"]
            dollar_volume[symbol] = bar["c"] * bar["v"]
    assets["price"] = assets["symbol"].map(price)
    assets["dollar_volume"] = assets["symbol"].map(dollar_volume)

    universe = assets[(assets["price"] >= WIDE_MIN_PRICE) &
                      (assets["dollar_volume"] >= WIDE_MIN_DOLLAR_VOLUME)]
    universe = universe.sort_values("symbol").reset_index(drop=True)
    config.DATA_DIR.mkdir(exist_ok=True)
    universe.to_parquet(config.UNIVERSE_FILE, index=False)
    return universe


def download_history(progress=print) -> int:
    """Download daily bars for the universe (plus the benchmark). Safe to re-run:
    batches already on disk are skipped."""
    alpaca = _alpaca()
    symbols = pd.read_parquet(config.UNIVERSE_FILE)["symbol"].tolist()
    if config.BENCHMARK not in symbols:
        symbols.append(config.BENCHMARK)
    config.US_BARS_DIR.mkdir(parents=True, exist_ok=True)

    start = date.fromisoformat(config.BACKTEST_START)
    batches = [symbols[i:i + BATCH] for i in range(0, len(symbols), BATCH)]
    total = 0
    for number, batch in enumerate(batches):
        path = config.US_BARS_DIR / ("part-%04d.parquet" % number)
        if path.exists():
            continue
        # "all" also adjusts for dividends, so a payout is not mistaken for a fall.
        bars = alpaca.get_daily_bars(batch, start, date.today(), adjustment="all")
        bars.to_parquet(path, index=False)
        total += len(bars)
        progress("  batch %d of %d: %s to %s, %d rows" % (
            number + 1, len(batches), batch[0], batch[-1], len(bars)))
    return total
