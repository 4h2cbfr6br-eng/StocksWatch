"""Yahoo Finance adapter (through the unofficial yfinance library).

Needs no API key, covers US and London shares. It is unofficial and for
personal use only (PLAN.md section 3.3), so it must be replaced before anyone
else sees the data.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Sequence

import pandas as pd
import yfinance as yf

from .base import BAR_COLUMNS


class YahooProvider:
    name = "yahoo"

    def get_daily_bars(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        frames = self._download(list(symbols), start, end)
        # Yahoo sometimes drops a symbol for no good reason; ask once more for any that are missing.
        missing = [s for s in symbols if s not in {f["symbol"].iloc[0] for f in frames}]
        if missing:
            frames += self._download(missing, start, end)
        if not frames:
            return pd.DataFrame(columns=BAR_COLUMNS)
        return pd.concat(frames, ignore_index=True)[BAR_COLUMNS]

    def _download(self, symbols: list, start: date, end: date) -> list:
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # Yahoo's end date is exclusive
            auto_adjust=False,   # keep the real traded close (split-adjusted, not dividend-adjusted)
            group_by="ticker",
            progress=False,
            threads=False,       # one at a time: parallel downloads trip over yfinance's own cache
        )
        frames = []
        for symbol in symbols:
            try:
                one = raw[symbol]
            except KeyError:
                continue
            one = one.dropna(subset=["Close"])
            if one.empty:
                continue
            frames.append(pd.DataFrame({
                "symbol": symbol,
                "date": pd.to_datetime(one.index).date,
                "open": one["Open"].to_numpy(),
                "high": one["High"].to_numpy(),
                "low": one["Low"].to_numpy(),
                "close": one["Close"].to_numpy(),
                "volume": one["Volume"].to_numpy(),
            }))
        return frames

    def get_fundamentals(self, symbols: Sequence[str]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for symbol in symbols:
            try:
                info = yf.Ticker(symbol).info
            except Exception:  # Yahoo is flaky; a missing number must not stop the run
                info = {}
            out[symbol] = {
                "name": info.get("shortName") or info.get("longName"),
                "currency": info.get("currency"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
            }
        return out
