"""Tests for the drop rules, using real historical days as fixtures.

Prices are official closing prices in the units quoted at the time.
"""
import pytest

from stockswatch import rules


# --- Known real days ---------------------------------------------------------

def test_nvidia_deepseek_day_27_jan_2025():
    # Closed 142.62 on 24 Jan 2025, 118.42 on 27 Jan 2025.
    pct = rules.pct_change(118.42, 142.62)
    assert pct == pytest.approx(-16.97, abs=0.01)
    assert rules.tier_for(pct) == "Major"
    # NVDA's normal daily move was roughly 2.5% then, so this was ~7x normal.
    z = rules.z_score(pct, 0.025)
    verdict = rules.evaluate_watchlist(pct, z)
    assert verdict.alert and verdict.tier == "Major"
    assert rules.evaluate_market(pct, z, vs_index=pct - (-1.46)).alert


def test_meta_results_day_3_feb_2022():
    # Closed 323.00 on 2 Feb 2022, 237.76 on 3 Feb 2022.
    pct = rules.pct_change(237.76, 323.00)
    assert pct == pytest.approx(-26.39, abs=0.01)
    assert rules.tier_for(pct) == "Severe"
    assert rules.evaluate_watchlist(pct, rules.z_score(pct, 0.02)).alert


def test_nvidia_10_for_1_split_must_not_alert():
    # Closed 1208.88 on 7 Jun 2024; split 10-for-1; closed 121.79 on 10 Jun 2024.
    raw_pct = rules.pct_change(121.79, 1208.88)
    assert raw_pct == pytest.approx(-89.9, abs=0.1)

    # Without the split information: held back, never alerted.
    naive = rules.evaluate_watchlist(raw_pct, z=-40.0)
    assert not naive.alert
    assert naive.held is not None

    # With the split applied to the previous close: a small rise, no alert.
    prev = rules.adjust_prev_close(1208.88, split_ratio=10)
    pct = rules.pct_change(121.79, prev)
    assert pct == pytest.approx(0.75, abs=0.01)
    verdict = rules.evaluate_watchlist(pct, rules.z_score(pct, 0.03))
    assert not verdict.alert and verdict.held is None


def test_pence_pounds_mixup_is_held_not_alerted():
    # Yesterday's close arrives in pence (5200p), today's price in pounds (52.10).
    bogus_pct = rules.pct_change(52.10, 5200.0)
    assert bogus_pct < -98
    verdict = rules.evaluate_watchlist(bogus_pct, z=-50.0)
    assert not verdict.alert
    assert "second-source" in verdict.held

    # Once both are in the same unit, it is a small rise.
    pct = rules.pct_change(52.10, rules.to_major_units(5200.0, "GBX"))
    assert pct == pytest.approx(0.19, abs=0.01)
    assert not rules.evaluate_watchlist(pct, z=0.1).alert


# --- Volatility (sigma) ------------------------------------------------------

def test_sigma_needs_enough_history():
    assert rules.robust_sigma([0.01] * 59) is None


def test_sigma_of_steady_swings():
    returns = [0.015, -0.015] * 30
    assert rules.robust_sigma(returns) == pytest.approx(1.4826 * 0.015)


def test_sigma_floor_for_very_quiet_stocks():
    returns = [0.001, -0.001] * 30
    assert rules.robust_sigma(returns) == 0.01


def test_sigma_ignores_one_old_crash():
    returns = [0.01, -0.01] * 30
    with_crash = returns[:-1] + [-0.30]
    assert rules.robust_sigma(with_crash) == pytest.approx(rules.robust_sigma(returns), rel=0.05)


def test_sigma_uses_only_the_most_recent_window():
    old_wild = [0.08, -0.08] * 30
    recent_calm = [0.012, -0.012] * 30
    assert rules.robust_sigma(old_wild + recent_calm) == pytest.approx(1.4826 * 0.012)


def test_daily_returns():
    assert rules.daily_returns([100.0, 110.0, 99.0]) == pytest.approx([0.10, -0.10])


# --- Thresholds --------------------------------------------------------------

def test_watchlist_breach_on_percent_alone():
    verdict = rules.evaluate_watchlist(-4.5, z=-1.0)
    assert verdict.alert and len(verdict.reasons) == 1


def test_watchlist_breach_on_z_alone():
    # A quiet stock down 3% is unusual even though it is under the % threshold.
    verdict = rules.evaluate_watchlist(-3.0, z=-3.0)
    assert verdict.alert and verdict.tier is None


def test_watchlist_no_breach_for_small_moves_or_rises():
    assert not rules.evaluate_watchlist(-1.0, z=-0.8).alert
    assert not rules.evaluate_watchlist(6.0, z=4.0).alert


def test_watchlist_uses_custom_thresholds():
    assert not rules.evaluate_watchlist(-4.5, z=-1.0, threshold_pct=-8.0).alert
    assert rules.evaluate_watchlist(-2.5, z=-1.0, threshold_pct=-2.0).alert


def test_watchlist_works_without_enough_history_for_z():
    assert rules.evaluate_watchlist(-6.0, z=None).alert
    assert not rules.evaluate_watchlist(-2.0, z=None).alert


def test_market_rule_needs_all_three_checks():
    assert rules.evaluate_market(-6.0, z=-3.5, vs_index=-5.0).alert
    assert not rules.evaluate_market(-6.0, z=-2.0, vs_index=-5.0).alert   # normal for a wild stock
    assert not rules.evaluate_market(-6.0, z=-3.5, vs_index=-1.0).alert   # whole market fell
    assert not rules.evaluate_market(-4.0, z=-3.5, vs_index=-4.0).alert   # too small
    assert not rules.evaluate_market(-6.0, z=None, vs_index=-5.0).alert   # new listing


def test_tiers():
    assert rules.tier_for(-4.9) is None
    assert rules.tier_for(-5.0) == "Notable"
    assert rules.tier_for(-10.0) == "Major"
    assert rules.tier_for(-20.0) == "Severe"


def test_split_like_falls():
    assert rules.looks_like_split(-50.2)
    assert rules.looks_like_split(-89.9)
    assert not rules.looks_like_split(-17.0)
    assert not rules.looks_like_split(-26.4)


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        rules.pct_change(10.0, 0.0)
    with pytest.raises(ValueError):
        rules.adjust_prev_close(10.0, split_ratio=0)
