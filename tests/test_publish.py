"""Tests for the wording helpers used when saving alerts (no internet)."""
from datetime import date, datetime

from stockswatch import publish, scanner


def test_clean_name_strips_share_class_wording():
    assert publish.clean_name("NVIDIA Corporation Common Stock") == "NVIDIA Corporation"
    assert publish.clean_name("Heartflow, Inc. Common Stock") == "Heartflow, Inc."
    assert publish.clean_name("Alphabet Inc. Class A Common Stock") == "Alphabet Inc."
    assert publish.clean_name("ASML Holding N.V. American Depositary Shares") == "ASML Holding N.V."
    assert publish.clean_name("Flowers Foods, Inc.") == "Flowers Foods, Inc."


def test_short_name_for_headlines():
    assert publish.short_name("Heartflow, Inc. Common Stock") == "Heartflow"
    assert publish.short_name("NVIDIA Corporation") == "NVIDIA"
    assert publish.short_name("Vir Biotechnology, Inc.") == "Vir Biotechnology"


def test_headline_is_plain_fact_with_no_sales_words():
    text = publish.make_headline("Heartflow, Inc.", -19.1, "its biggest one-day fall since March 2025")
    assert text == "Heartflow falls 19%, its biggest one-day fall since March 2025"
    assert publish.make_headline("Flowers Foods, Inc.", -8.0, None) == "Flowers Foods falls 8%"
    for banned in ("dip", "bargain", "opportunity", "cheap", "oversold", "buy"):
        assert banned not in text.lower()


def test_session_over():
    day = date(2026, 11, 13)
    at = lambda h, m, d=13: datetime(2026, 11, d, h, m, tzinfo=scanner.NEW_YORK)
    assert not publish.session_over(day, at(11, 0))
    assert not publish.session_over(day, at(16, 5))
    assert publish.session_over(day, at(16, 20))
    assert publish.session_over(day, at(3, 0, d=16))


def test_clean_name_tidies_london_listings():
    assert publish.clean_name("SHELL PLC ORD EUR0.07") == "Shell plc"
    assert publish.clean_name("ASTRAZENECA PLC ORD SHS $0.25") == "Astrazeneca plc"
    assert publish.clean_name("NVIDIA Corporation Common Stock") == "NVIDIA Corporation"


def test_series_rows_keep_the_latest_year_oldest_first():
    import pandas as pd
    days = pd.date_range("2025-01-01", periods=300, freq="D")
    bars = pd.DataFrame({"symbol": "AAA", "date": days, "close": range(1, 301)})
    rows = publish.series_rows(bars, {"AAA": 7}, "2026-11-16T00:00:00+00:00")
    assert len(rows) == 1 and rows[0]["instrument_id"] == 7
    assert len(rows[0]["closes"]) == publish.SERIES_DAYS
    assert rows[0]["closes"][-1] == 300.0 and rows[0]["dates"][0] < rows[0]["dates"][-1]
    assert publish.series_rows(bars, {}, "x") == []


def test_halts_feed_lists_only_stocks_still_halted():
    from zoneinfo import ZoneInfo
    from stockswatch import halts
    def item(symbol, halt_time, resume_date="", resume_time="", day="11/16/2026"):
        return ("<item><ndaq:HaltDate>%s</ndaq:HaltDate><ndaq:HaltTime>%s</ndaq:HaltTime>"
                "<ndaq:IssueSymbol>%s</ndaq:IssueSymbol><ndaq:ReasonCode>LUDP</ndaq:ReasonCode>"
                "<ndaq:ResumptionDate>%s</ndaq:ResumptionDate>"
                "<ndaq:ResumptionTradeTime>%s</ndaq:ResumptionTradeTime></item>"
                % (day, halt_time, symbol, resume_date, resume_time))
    xml = ('﻿<?xml version="1.0"?><rss xmlns:ndaq="http://www.nasdaqtrader.com/"><channel>'
           + item("STILL", "10:00:00")
           + item("BACK", "10:00:00", "11/16/2026", "10:10:00")
           + item("SOON", "10:20:00", "11/16/2026", "10:40:00")
           + item("OLD", "10:00:00", day="11/13/2026")
           + "</channel></rss>")
    now = datetime(2026, 11, 16, 10, 30, tzinfo=ZoneInfo("America/New_York"))
    assert halts.parse(xml, now) == {"STILL": "LUDP", "SOON": "LUDP"}
