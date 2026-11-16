"""Tests for the whole-market scanner, using made-up snapshots (no internet)."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from stockswatch import rules, scanner

DAY = "2026-11-13T05:00:00Z"
AFTER_CLOSE = datetime(2026, 11, 13, 17, 0, tzinfo=scanner.NEW_YORK)


def snap(price, prev_close, volume=3_000_000, day=DAY):
    return {"dailyBar": {"t": day, "c": price, "v": volume},
            "prevDailyBar": {"t": "2026-11-12T05:00:00Z", "c": prev_close, "v": 1_000_000}}


def make_stats(**dollar_volume):
    """Every stock: normal move 2%, 1m shares a day. dollar_volume sets its size."""
    rows = {s: {"sigma": 0.02, "dollar_volume": v, "avg_volume": 1_000_000,
                "high_52w": 150.0, "low_52w": 60.0, "last_date": date(2026, 11, 12)}
            for s, v in dollar_volume.items()}
    return pd.DataFrame.from_dict(rows, orient="index")


def run(snapshots, stats, now=AFTER_CLOSE):
    snapshots = dict(snapshots)
    snapshots.setdefault("SPY", snap(500.0, 500.0))
    return scanner.evaluate(snapshots, stats, {}, now)


def test_big_company_fall_is_flagged_for_push():
    result = run({"BIG": snap(88.0, 100.0), "CALM": snap(99.5, 100.0)},
                 make_stats(BIG=900e6, CALM=900e6))
    assert [c.symbol for c in result.alerts] == ["BIG"]
    alert = result.alerts[0]
    assert alert.push and alert.tier == "Major"
    assert alert.pct == pytest.approx(-12.0)
    assert alert.z == pytest.approx(-6.0)
    assert not result.sell_off


def test_smaller_company_is_front_page_only():
    result = run({"MID": snap(88.0, 100.0)}, make_stats(MID=60e6))
    assert len(result.alerts) == 1 and not result.alerts[0].push


def test_tiny_and_penny_stocks_are_ignored():
    result = run({"TINY": snap(88.0, 100.0), "PENNY": snap(3.0, 4.0)},
                 make_stats(TINY=5e6, PENNY=900e6))
    assert result.alerts == []


def test_fall_on_normal_volume_does_not_alert():
    result = run({"QUIET": snap(88.0, 100.0, volume=1_000_000)}, make_stats(QUIET=900e6))
    assert result.alerts == []


def test_fall_in_line_with_the_market_does_not_alert():
    result = run({"BIG": snap(94.0, 100.0), "SPY": snap(480.0, 500.0)}, make_stats(BIG=900e6))
    assert result.alerts == []          # down 6% while the index is down 4%: only 2 points worse
    assert result.sell_off              # but the index fall itself triggers sell-off mode


def test_many_alerts_at_once_trigger_sell_off_mode():
    names = ["S%02d" % i for i in range(30)]
    result = run({n: snap(90.0, 100.0) for n in names}, make_stats(**{n: 900e6 for n in names}))
    assert len(result.alerts) == 30 and result.sell_off


def test_split_like_fall_is_held_not_alerted():
    result = run({"SPLIT": snap(10.0, 100.0)}, make_stats(SPLIT=900e6))
    assert result.alerts == []
    assert len(result.held) == 1 and "SPLIT" in result.held[0]


def test_volume_is_scaled_by_time_of_day():
    # One hour into the session, 0.5m shares is already 3x the normal pace.
    morning = datetime(2026, 11, 13, 10, 30, tzinfo=scanner.NEW_YORK)
    assert scanner.session_fraction(date(2026, 11, 13), morning) == pytest.approx(60 / 390)
    result = run({"BIG": snap(88.0, 100.0, volume=500_000)}, make_stats(BIG=900e6), now=morning)
    assert len(result.alerts) == 1
    assert result.alerts[0].rel_volume == pytest.approx(0.5 / (60 / 390))
    # The same volume by the close is only half a normal day: no alert.
    assert run({"BIG": snap(88.0, 100.0, volume=500_000)}, make_stats(BIG=900e6)).alerts == []


def test_stocks_that_have_not_traded_today_are_skipped():
    stale = snap(50.0, 100.0, day="2026-11-10T05:00:00Z")
    result = run({"STALE": stale, "BIG": snap(99.0, 100.0), "OK": snap(100.0, 100.0)},
                 make_stats(STALE=900e6, BIG=900e6, OK=900e6))
    assert result.bar_date == date(2026, 11, 13)
    assert result.alerts == [] and result.held == []


def test_stats_use_the_shared_sigma_rule():
    days = pd.bdate_range("2025-01-01", periods=300)
    returns = np.random.default_rng(5).normal(0, 0.015, 300)
    close = 100 * np.cumprod(1 + returns)
    bars = pd.DataFrame({"symbol": "X", "date": days, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": 2_000_000})
    stats = scanner.stats_from_bars(bars)
    assert stats.at["X", "sigma"] == pytest.approx(rules.robust_sigma(list(returns[1:])))
    assert stats.at["X", "avg_volume"] == 2_000_000
    assert stats.at["X", "high_52w"] == pytest.approx((close[-252:] * 1.01).max())
