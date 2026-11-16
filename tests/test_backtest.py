"""Tests that the fast whole-table rules match the one-at-a-time rules, and that
the backtester never uses information from the future."""
import numpy as np
import pandas as pd
import pytest

from stockswatch import backtest, rules


def random_returns(n, seed):
    return np.random.default_rng(seed).normal(0, 0.02, n)


# --- Fast versions give identical answers -------------------------------------

def test_rolling_sigma_matches_the_simple_version():
    returns = random_returns(200, seed=1)
    returns[0] = np.nan                       # the first day has no previous close
    fast = rules.rolling_sigma(returns)
    for i in range(len(returns)):
        slow = rules.robust_sigma(list(returns[:i]))
        if slow is None:
            assert np.isnan(fast[i])
        else:
            assert fast[i] == pytest.approx(slow)


def test_rolling_sigma_never_sees_today_or_the_future():
    returns = random_returns(150, seed=2)
    before = rules.rolling_sigma(returns)
    changed = returns.copy()
    changed[100:] = -0.5                      # rewrite day 100 onwards
    after = rules.rolling_sigma(changed)
    assert np.allclose(before[:101], after[:101], equal_nan=True)   # day 100's sigma is untouched


def test_market_mask_matches_the_simple_rule():
    rng = np.random.default_rng(3)
    pct = rng.uniform(-95, 10, 3000)
    z = rng.uniform(-12, 3, 3000)
    vs = rng.uniform(-30, 5, 3000)
    z[::50] = np.nan
    vs[::70] = np.nan
    fast = rules.market_rule_mask(pct, z, vs)
    slow = [rules.evaluate_market(p, None if np.isnan(a) else a, None if np.isnan(b) else b).alert
            for p, a, b in zip(pct, z, vs)]
    assert fast.tolist() == slow


# --- The backtester itself ----------------------------------------------------

def make_bars(crash_day=150, crash=-0.12, days=260):
    """Three made-up stocks plus the index. STOCK_A falls sharply on one day."""
    dates = pd.bdate_range("2022-01-03", periods=days)
    frames = []
    for symbol, seed in (("SPY", 10), ("STOCK_A", 11), ("STOCK_B", 12), ("PENNY", 13)):
        returns = np.random.default_rng(seed).normal(0.0003, 0.008, days)
        if symbol == "STOCK_A":
            returns[crash_day] = crash
        start = 2.0 if symbol == "PENNY" else 100.0
        close = start * np.cumprod(1 + returns)
        frames.append(pd.DataFrame({
            "symbol": symbol, "date": dates, "low": close * 0.99, "close": close,
            "volume": np.where(np.arange(days) == crash_day, 5_000_000, 1_000_000),
        }))
    return pd.concat(frames, ignore_index=True)


def test_backtest_finds_the_planted_fall_and_nothing_else():
    panel = backtest.build_panel(make_bars())
    alerts = backtest.find_alerts(panel, backtest.VARIANTS[0])
    assert alerts["symbol"].tolist() == ["STOCK_A"]
    row = alerts.iloc[0]
    assert row["pct"] == pytest.approx(-12.0, abs=0.01)
    assert row["tier"] == "Major"
    assert row["n"] == 150


def test_penny_stock_is_filtered_out_even_when_it_crashes():
    bars = make_bars()
    penny = bars["symbol"] == "PENNY"
    bars.loc[penny & (bars["date"] == bars["date"].unique()[200]), "close"] *= 0.7
    alerts = backtest.find_alerts(backtest.build_panel(bars), backtest.VARIANTS[1])
    assert "PENNY" not in alerts["symbol"].tolist()


def test_forward_returns_are_measured_from_the_alert_close():
    bars = make_bars()
    panel = backtest.build_panel(bars)
    row = backtest.find_alerts(panel, backtest.VARIANTS[0]).iloc[0]
    closes = bars[bars["symbol"] == "STOCK_A"]["close"].to_numpy()
    assert row["fwd_5"] == pytest.approx(closes[155] / closes[150] - 1)
    assert row["fwd_20"] == pytest.approx(closes[170] / closes[150] - 1)


def test_inputs_on_alert_day_do_not_change_when_the_future_changes():
    bars = make_bars()
    later = bars.copy()
    cutoff = bars["date"].unique()[150]
    later.loc[later["date"] > cutoff, "close"] *= 3.0       # rewrite everything after the alert
    a = backtest.build_panel(bars)
    b = backtest.build_panel(later)
    cols = ["pct", "z", "sigma", "adv20", "rel_volume", "vs_index", "eligible"]
    pick = lambda p: p[(p["symbol"] == "STOCK_A") & (p["date"] == cutoff)][cols].iloc[0]
    assert pick(a).equals(pick(b))


def test_next_day_repeat_is_suppressed_unless_tier_rises():
    bars = make_bars()
    a = bars["symbol"] == "STOCK_A"
    dates = bars["date"].unique()
    bars.loc[a & (bars["date"] >= dates[151]), "close"] *= 0.93     # another -7% the next day
    bars.loc[a & (bars["date"] == dates[151]), "volume"] = 5_000_000
    alerts = backtest.find_alerts(backtest.build_panel(bars), backtest.VARIANTS[0])
    assert alerts["n"].tolist() == [150]       # day 151 is Notable, lower than Major: no repeat


def test_report_runs_and_carries_the_warnings():
    text = backtest.run(backtest.build_panel(make_bars()))
    assert "Survivorship bias" in text
    assert "not for publication" in text
