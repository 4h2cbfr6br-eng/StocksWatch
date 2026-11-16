"""Alpaca adapter: US prices from all exchanges (free plan, personal use).

The free plan refuses full-market data from the last 15 minutes, so requests
stop 16 minutes before now. It allows 200 requests a minute.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Sequence

import pandas as pd
import requests

from .base import BAR_COLUMNS

DATA_URL = "https://data.alpaca.markets"
TRADING_URL = "https://paper-api.alpaca.markets"
MAIN_EXCHANGES = ("NYSE", "NASDAQ", "ARCA", "AMEX", "BATS")
MIN_GAP_SECONDS = 0.35   # keeps us under 200 requests a minute


class AlpacaProvider:
    name = "alpaca"

    def __init__(self, key: str, secret: str):
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self._last_call = 0.0

    def _get(self, url: str, params: dict) -> dict:
        for attempt in range(5):
            wait = MIN_GAP_SECONDS - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            try:
                response = requests.get(url, headers=self._headers, params=params, timeout=90)
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))   # network blip: wait and try again
                continue
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(15)                  # rate limited or server trouble
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Alpaca did not answer after 5 attempts: %s" % url)

    # --- Daily bars -----------------------------------------------------------

    def get_daily_bars(self, symbols: Sequence[str], start: date, end: date,
                       adjustment: str = "split") -> pd.DataFrame:
        """adjustment: "split" restates old prices for splits; "all" also for dividends."""
        latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=16)
        end_time = min(datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1),
                       latest_allowed)
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": "sip",           # all US exchanges
            "adjustment": adjustment,
            "limit": 10000,
        }
        rows = []
        while True:  # results come in pages; keep asking until there is no next page
            data = self._get(DATA_URL + "/v2/stocks/bars", params)
            for symbol, bars in (data.get("bars") or {}).items():
                for bar in bars:
                    rows.append((symbol, date.fromisoformat(bar["t"][:10]),
                                 bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]))
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return pd.DataFrame(rows, columns=BAR_COLUMNS)

    # --- Whole-market helpers -------------------------------------------------

    def list_assets(self) -> List[dict]:
        """Every active US stock on the main exchanges: symbol, name, exchange."""
        assets = self._get(TRADING_URL + "/v2/assets", {"status": "active", "asset_class": "us_equity"})
        return [{"symbol": a["symbol"], "name": a["name"], "exchange": a["exchange"]}
                for a in assets if a.get("tradable") and a.get("exchange") in MAIN_EXCHANGES]

    def get_snapshots(self, symbols: Sequence[str], feed: str = "delayed_sip",
                      batch: int = 2000) -> Dict[str, dict]:
        """Latest price snapshot per symbol. 15-minute delayed by default."""
        out: Dict[str, dict] = {}
        symbols = list(symbols)
        for i in range(0, len(symbols), batch):
            out.update(self._get(DATA_URL + "/v2/stocks/snapshots",
                                 {"symbols": ",".join(symbols[i:i + batch]), "feed": feed}))
        return out
