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
