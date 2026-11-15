"""Chooses which data provider serves which market.

US prices come from Alpaca and US key numbers from Finnhub when their keys
are in the .env file. London shares and the index levels come from Yahoo.
Without keys, everything falls back to Yahoo.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from .. import config
from .alpaca import AlpacaProvider
from .finnhub import FinnhubProvider
from .yahoo import YahooProvider

load_dotenv(config.ROOT / ".env")


def bars_provider(market: str):
    """market is "US", "UK" or "INDEX"."""
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
    if market == "US" and key and secret:
        return AlpacaProvider(key, secret)
    return YahooProvider()


def fundamentals_provider(market: str):
    key = os.getenv("FINNHUB_API_KEY")
    if market == "US" and key:
        return FinnhubProvider(key)
    return YahooProvider()
