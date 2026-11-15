"""Finnhub adapter: key numbers for US companies (free plan, personal use).

The free plan allows 60 calls a minute and does not cover London shares.
"""
from __future__ import annotations

import time
from typing import Dict, Sequence

import requests

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubProvider:
    name = "finnhub"

    def __init__(self, key: str):
        self._key = key

    def _get(self, path: str, **params) -> dict:
        try:
            response = requests.get(BASE_URL + path, params=dict(params, token=self._key), timeout=30)
            if response.status_code == 429:  # too many calls: wait for the next minute and retry once
                time.sleep(61)
                response = requests.get(BASE_URL + path, params=dict(params, token=self._key), timeout=30)
            response.raise_for_status()
            return response.json() or {}
        except (requests.RequestException, ValueError):
            return {}  # a missing number must not stop the run

    def get_fundamentals(self, symbols: Sequence[str]) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for symbol in symbols:
            profile = self._get("/stock/profile2", symbol=symbol)
            metric = self._get("/stock/metric", symbol=symbol, metric="all").get("metric") or {}
            cap_millions = profile.get("marketCapitalization")
            out[symbol] = {
                "name": profile.get("name"),
                "currency": profile.get("currency"),
                "market_cap": cap_millions * 1e6 if cap_millions else None,
                "pe_ratio": metric.get("peTTM"),
                "sector": profile.get("finnhubIndustry"),
            }
        return out
