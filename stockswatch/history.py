"""Download daily price history into a Parquet file and read it back.

Parquet is a compact file format for tables. DuckDB is a small database
engine that can query Parquet files directly, with no server to run.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Dict, List

import duckdb
import pandas as pd

from . import config, providers, rules


@dataclass(frozen=True)
class WatchItem:
    symbol: str
    market: str          # "US" or "UK"
    threshold_pct: float
    threshold_z: float


def load_watchlist() -> List[WatchItem]:
    items = []
    with open(config.WATCHLIST_FILE, newline="") as f:
        for row in csv.DictReader(f):
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol or symbol.startswith("#"):
                continue
            market = (row.get("market") or "").strip().upper() or ("UK" if symbol.endswith(".L") else "US")
            if market not in config.INDEX_FOR_MARKET:
                raise ValueError("watchlist.csv: market for %s must be US or UK, not %r" % (symbol, market))
            items.append(WatchItem(
                symbol=symbol,
                market=market,
                threshold_pct=-abs(float(row.get("threshold_pct") or rules.WATCHLIST_THRESHOLD_PCT)),
                threshold_z=-abs(float(row.get("threshold_z") or rules.WATCHLIST_THRESHOLD_Z)),
            ))
    return items


def update(watchlist: Optional[List[WatchItem]] = None) -> pd.DataFrame:
    """Fetch history for every watchlist stock plus the indices, and save it."""
    watchlist = watchlist if watchlist is not None else load_watchlist()
    groups = {market: [w.symbol for w in watchlist if w.market == market]
              for market in sorted({w.market for w in watchlist})}
    indices = sorted({config.INDEX_FOR_MARKET[market] for market in groups})

    end = date.today()
    start = end - timedelta(days=365 * config.HISTORY_YEARS + 10)

    frames = []
    fundamentals: Dict[str, dict] = {}
    for market, symbols in list(groups.items()) + [("INDEX", indices)]:
        provider = providers.bars_provider(market)
        bars = provider.get_daily_bars(symbols, start, end)
        bars["source"] = provider.name   # remember where each row came from
        frames.append(bars)
        if market != "INDEX":
            fundamentals.update(providers.fundamentals_provider(market).get_fundamentals(symbols))

    all_bars = pd.concat(frames, ignore_index=True)
    config.DATA_DIR.mkdir(exist_ok=True)
    all_bars.to_parquet(config.BARS_FILE, index=False)
    config.FUNDAMENTALS_FILE.write_text(json.dumps(fundamentals, indent=2))
    return all_bars


def load_bars() -> pd.DataFrame:
    if not config.BARS_FILE.exists():
        raise FileNotFoundError("No price history yet. Run: python -m stockswatch update")
    path = str(config.BARS_FILE).replace("'", "''")
    bars = duckdb.sql(
        "SELECT * FROM read_parquet('%s') ORDER BY symbol, date" % path
    ).df()
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    return bars


def load_fundamentals() -> Dict[str, dict]:
    if not config.FUNDAMENTALS_FILE.exists():
        return {}
    return json.loads(config.FUNDAMENTALS_FILE.read_text())
