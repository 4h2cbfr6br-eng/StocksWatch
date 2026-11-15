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

# How much daily history to keep.
HISTORY_YEARS = 5

# The index each market is compared against (Yahoo symbols).
INDEX_FOR_MARKET = {"US": "^GSPC", "UK": "^FTSE"}
INDEX_NAMES = {"^GSPC": "S&P 500", "^FTSE": "FTSE 100"}
