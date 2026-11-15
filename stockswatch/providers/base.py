"""The one interface every data provider must offer.

The rest of the app only ever talks to this shape, so swapping Yahoo for
Alpaca (or a licensed feed at launch) means writing one new adapter file and
changing nothing else.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Protocol, Sequence

import pandas as pd

# Columns every provider returns from get_daily_bars, one row per symbol per day.
BAR_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume"]


class DataProvider(Protocol):
    name: str

    def get_daily_bars(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        """Daily prices, already adjusted for stock splits, with BAR_COLUMNS."""
        ...

    def get_fundamentals(self, symbols: Sequence[str]) -> Dict[str, dict]:
        """Per symbol: name, currency, market_cap, pe_ratio (any may be None)."""
        ...
