"""Alpaca adapter: US daily prices from all exchanges (free plan, personal use).

The free plan refuses full-market data from the last 15 minutes, so requests
stop 16 minutes before now.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import pandas as pd
import requests

from .base import BAR_COLUMNS

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, key: str, secret: str):
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def get_daily_bars(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=16)
        end_time = min(datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1),
                       latest_allowed)
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": "sip",           # all US exchanges
            "adjustment": "split",   # restate old prices for stock splits
            "limit": 10000,
        }
        rows = []
        while True:  # results come in pages; keep asking until there is no next page
            response = requests.get(BARS_URL, headers=self._headers, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            for symbol, bars in (data.get("bars") or {}).items():
                for bar in bars:
                    rows.append((symbol, date.fromisoformat(bar["t"][:10]),
                                 bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]))
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return pd.DataFrame(rows, columns=BAR_COLUMNS)
