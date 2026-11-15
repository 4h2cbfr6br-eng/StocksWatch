"""Drop-detection rules.

Everything here is a pure function: numbers in, answer out. No internet, no
files. That is deliberate, because the live scanner and the backtester must
both run exactly this code (see PLAN.md, sections 4, 5 and 7).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

# --- Defaults from PLAN.md section 4 -----------------------------------------

SIGMA_WINDOW = 60          # trading days of history used for "normal" volatility
SIGMA_FLOOR = 0.01         # never treat a stock's normal daily move as below 1%
SUSPECT_DROP_PCT = -60.0   # falls beyond this are held for a second-source check
SPLIT_LIKE_DROPS = (-50.0, -66.67, -75.0, -80.0, -90.0)  # 2:1, 3:1, 4:1, 5:1, 10:1

# Tier name and the fall (in %) needed to reach it, biggest first.
TIERS = (("Severe", -20.0), ("Major", -10.0), ("Notable", -5.0))

WATCHLIST_THRESHOLD_PCT = -4.0
WATCHLIST_THRESHOLD_Z = -2.5

MARKET_MIN_DROP_PCT = -5.0
MARKET_MIN_Z = -3.0
MARKET_MIN_VS_INDEX = -3.0  # percentage points worse than the index


# --- Building blocks ---------------------------------------------------------

def pct_change(price: float, prev_close: float) -> float:
    """Percentage move from the previous close. -5.0 means down 5%."""
    if prev_close <= 0:
        raise ValueError("previous close must be positive")
    return (price / prev_close - 1.0) * 100.0


def adjust_prev_close(prev_close: float, split_ratio: float = 1.0,
                      cash_dividend: float = 0.0) -> float:
    """Previous close restated for a split and/or dividend taking effect today.

    A 10-for-1 split has split_ratio=10: yesterday's 1,200 is today's 120.
    """
    if split_ratio <= 0:
        raise ValueError("split ratio must be positive")
    return prev_close / split_ratio - cash_dividend


def to_major_units(price: float, unit: str) -> float:
    """Convert a price to pounds/dollars. London quotes many shares in pence (GBX)."""
    return price / 100.0 if unit.upper() in ("GBX", "GBP_PENCE") else price


def daily_returns(closes: Sequence[float]) -> list:
    """Day-to-day returns as fractions (0.02 = up 2%)."""
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


def robust_sigma(returns: Sequence[float], window: int = SIGMA_WINDOW,
                 floor: float = SIGMA_FLOOR) -> Optional[float]:
    """A stock's normal daily move, as a fraction.

    Uses the median absolute deviation instead of the ordinary standard
    deviation, so one old crash does not inflate "normal". The 1.4826 factor
    scales it to match a standard deviation for normally distributed data.
    Returns None when there is not enough history.
    """
    recent = [r for r in returns[-window:] if r is not None and not math.isnan(r)]
    if len(recent) < window:
        return None
    median = statistics.median(recent)
    mad = statistics.median(abs(r - median) for r in recent)
    return max(1.4826 * mad, floor)


def z_score(pct: float, sigma: float) -> float:
    """How many "normal daily moves" today's move is. -6 means six times normal, downward."""
    return (pct / 100.0) / sigma


def tier_for(pct: float) -> Optional[str]:
    for name, threshold in TIERS:
        if pct <= threshold:
            return name
    return None


def looks_like_split(pct: float, tolerance: float = 1.0) -> bool:
    """True when a fall sits suspiciously close to a common split ratio."""
    return any(abs(pct - level) <= tolerance for level in SPLIT_LIKE_DROPS)


# --- Verdicts ----------------------------------------------------------------

@dataclass(frozen=True)
class Verdict:
    alert: bool                 # should this be shown as a breach?
    tier: Optional[str]         # Notable / Major / Severe, if any
    reasons: Tuple[str, ...]    # which thresholds were crossed
    held: Optional[str] = None  # why a candidate was held back instead of alerted


def _sanity_hold(pct: float) -> Optional[str]:
    if pct <= SUSPECT_DROP_PCT:
        return ("fall beyond 60%: needs a second-source check "
                "(possible pence/pounds mix-up or bad data)")
    if looks_like_split(pct):
        return "fall is close to a stock-split ratio: check for a split first"
    return None


def evaluate_watchlist(pct: float, z: Optional[float],
                       threshold_pct: float = WATCHLIST_THRESHOLD_PCT,
                       threshold_z: float = WATCHLIST_THRESHOLD_Z) -> Verdict:
    """Watchlist rule: breach if the fall passes EITHER the % or the z threshold."""
    held = _sanity_hold(pct)
    if held:
        return Verdict(False, None, (), held)
    reasons = []
    if pct <= threshold_pct:
        reasons.append("down %.1f%% (threshold %.1f%%)" % (abs(pct), abs(threshold_pct)))
    if z is not None and z <= threshold_z:
        reasons.append("%.1fx its normal daily move (threshold %.1fx)" % (abs(z), abs(threshold_z)))
    return Verdict(bool(reasons), tier_for(pct) if reasons else None, tuple(reasons))


def evaluate_market(pct: float, z: Optional[float], vs_index: Optional[float],
                    min_drop_pct: float = MARKET_MIN_DROP_PCT,
                    min_z: float = MARKET_MIN_Z,
                    min_vs_index: float = MARKET_MIN_VS_INDEX) -> Verdict:
    """Whole-market rule: ALL of the %, z and market-relative checks must hold.

    Volume and two-scans-in-a-row checks are added in Phase 1, when the
    scanner has intraday data.
    """
    held = _sanity_hold(pct)
    if held:
        return Verdict(False, None, (), held)
    if z is None or vs_index is None:
        return Verdict(False, None, ())
    if pct <= min_drop_pct and z <= min_z and vs_index <= min_vs_index:
        reasons = (
            "down %.1f%%" % abs(pct),
            "%.1fx its normal daily move" % abs(z),
            "%.1f points worse than its index" % abs(vs_index),
        )
        return Verdict(True, tier_for(pct), reasons)
    return Verdict(False, None, ())
