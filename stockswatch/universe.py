"""Builds the list of US stocks worth scanning, and downloads their history.

Deliberately a WIDE net (price >= $2, >= $3m traded on the latest day). The
real filters (price >= $5, >= $20m a day) are applied later, day by day, using
only what was known on each day.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

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


def refresh_recent(progress=print) -> int:
    """Daily job: rebuild the stock list and re-download the last ~14 months of
    daily bars. This is what tells the live scan what is "normal" for each stock.
    Takes a couple of minutes. Replaces the previous download."""
    progress("Rebuilding the stock list...")
    build()
    alpaca = _alpaca()
    symbols = pd.read_parquet(config.UNIVERSE_FILE)["symbol"].tolist()
    if config.BENCHMARK not in symbols:
        symbols.append(config.BENCHMARK)
    start = date.today() - timedelta(days=config.RECENT_DAYS)
    frames = []
    batches = [symbols[i:i + BATCH] for i in range(0, len(symbols), BATCH)]
    for number, batch in enumerate(batches):
        frames.append(alpaca.get_daily_bars(batch, start, date.today(), adjustment="all"))
        progress("  batch %d of %d" % (number + 1, len(batches)))
    bars = pd.concat(frames, ignore_index=True)
    config.US_RECENT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = config.US_RECENT_DIR / "bars.tmp"
    bars.to_parquet(temporary, index=False)
    temporary.replace(config.US_RECENT_DIR / "bars.parquet")
    progress("Saved %d rows for %d stocks" % (len(bars), bars["symbol"].nunique()))
    return len(bars)


def recent_is_fresh() -> bool:
    """True if the recent download was made today."""
    path = config.US_RECENT_DIR / "bars.parquet"
    return path.exists() and date.fromtimestamp(path.stat().st_mtime) == date.today()


def bars_source(long_history: bool = False) -> str:
    """The SQL "FROM" source for daily bars. The live scan wants the fresh recent
    file; headline clauses ("biggest fall since...") want the long history too."""
    def quoted(path) -> str:
        return "read_parquet('%s')" % str(path).replace("'", "''")
    columns = "symbol, date, high, low, close, volume"
    recent = config.US_RECENT_DIR / "bars.parquet"
    old = quoted(config.US_BARS_DIR / "*.parquet") if any(config.US_BARS_DIR.glob("*.parquet")) else None
    if recent.exists() and not (long_history and old):
        return quoted(recent)
    if not recent.exists():
        if not old:
            raise RuntimeError("No price history yet. Run: python -m stockswatch refresh")
        return old
    return ("(SELECT %s FROM %s UNION ALL SELECT %s FROM %s WHERE date > (SELECT max(date) FROM %s))"
            % (columns, old, columns, quoted(recent), old))

