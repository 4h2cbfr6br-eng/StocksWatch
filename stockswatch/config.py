"""Where files live and the settings shared across the app."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"

BARS_FILE = DATA_DIR / "daily_bars.parquet"
FUNDAMENTALS_FILE = DATA_DIR / "fundamentals.json"
WATCHLIST_FILE = ROOT / "watchlist.csv"
REPORT_FILE = OUT_DIR / "index.html"

# Whole-US-market files used by the backtester.
UNIVERSE_FILE = DATA_DIR / "us_universe.parquet"
US_BARS_DIR = DATA_DIR / "us_daily"            # one Parquet file per batch of symbols
BACKTEST_START = "2018-10-01"                  # gives a full year of run-in before 2020
BACKTEST_REPORT = OUT_DIR / "backtest.txt"
BENCHMARK = "SPY"                              # S&P 500 tracker, used as "the index"

# How much daily history to keep.
HISTORY_YEARS = 5

# The index each market is compared against (Yahoo symbols).
INDEX_FOR_MARKET = {"US": "^GSPC", "UK": "^FTSE"}
INDEX_NAMES = {"^GSPC": "S&P 500", "^FTSE": "FTSE 100"}
