"""Which US stocks are halted (trading paused by the exchange) right now.

Source: Nasdaq Trader's public trade-halts feed, which lists the current day's
halts for Nasdaq, NYSE and NYSE American stocks. A halted stock's price is
frozen, then often jumps when trading resumes, so an alert is not confirmed or
sent while its stock is halted.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict
from zoneinfo import ZoneInfo

import requests

FEED = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
NS = {"ndaq": "http://www.nasdaqtrader.com/"}
NEW_YORK = ZoneInfo("America/New_York")


def parse(xml_text: str, now: datetime) -> Dict[str, str]:
    """{symbol: reason code} for stocks halted at `now`. Times in the feed are New York time."""
    now = now.astimezone(NEW_YORK)
    today = now.strftime("%m/%d/%Y")
    halted: Dict[str, str] = {}
    root = ET.fromstring(xml_text.lstrip("﻿"))
    for item in root.iter("item"):
        def field(name: str) -> str:
            return (item.findtext("ndaq:" + name, default="", namespaces=NS) or "").strip()
        symbol = field("IssueSymbol")
        if not symbol or field("HaltDate") != today:
            continue
        resumed = False
        resume_date, resume_time = field("ResumptionDate"), field("ResumptionTradeTime")
        if resume_date and resume_time:
            try:
                at = datetime.strptime("%s %s" % (resume_date, resume_time[:8]), "%m/%d/%Y %H:%M:%S")
                resumed = at.replace(tzinfo=NEW_YORK) <= now
            except ValueError:
                resumed = False
        if resumed:
            halted.pop(symbol, None)       # a later entry for the same stock wins
        else:
            halted[symbol] = field("ReasonCode") or "halt"
    return halted


def current(now: datetime) -> Dict[str, str]:
    """Fetch the feed. If it cannot be read, report nothing halted rather than stop the scan."""
    try:
        response = requests.get(FEED, timeout=20, headers={"User-Agent": "stockswatch/1.0"})
        response.raise_for_status()
        return parse(response.text, now)
    except (requests.RequestException, ET.ParseError):
        return {}
