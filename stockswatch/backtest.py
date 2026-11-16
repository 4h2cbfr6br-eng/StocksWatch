"""Backtester: replay history to see how often each rule fires and what happened next.

For private threshold tuning only (PLAN.md sections 7 and 10). The results are
never shown to users as a reason to buy anything.

Honest limits, printed on every report:
  * Survivorship bias: only companies still listed today are in the data, so
    firms that later went bust are missing. This flatters "after the fall".
  * Daily bars: an alert is judged at that day's CLOSE, and "what happened
    next" is measured from that close.
  * Company size is approximated by how much money trades per day, because
    free data has no historical market cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import duckdb
import numpy as np
import pandas as pd

from . import config, rules

HORIZONS = (1, 5, 20, 60)             # trading days after the alert
MIN_PRICE = rules.MIN_PRICE
MIN_DOLLAR_VOLUME = rules.MIN_DOLLAR_VOLUME   # average traded per day over the previous 20 days
TUNE_PERIOD = ("2020-01-01", "2023-12-31")
TEST_PERIOD = ("2024-01-01", "2100-01-01")
TIER_RANK = {None: 0, "Notable": 1, "Major": 2, "Severe": 3}


@dataclass(frozen=True)
class Variant:
    name: str
    min_drop_pct: float
    min_z: float
    min_vs_index: float
    min_rel_volume: float


VARIANTS = [
    Variant("A  plan default  (-5%, 3x, -3pt, vol 1.5x)", -5.0, -3.0, -3.0, 1.5),
    Variant("B  looser        (-4%, 2.5x, -2pt, vol 1x)", -4.0, -2.5, -2.0, 1.0),
    Variant("C  bigger falls  (-7%, 3x, -3pt, vol 1.5x)", -7.0, -3.0, -3.0, 1.5),
    Variant("D  more unusual  (-5%, 4x, -3pt, vol 1.5x)", -5.0, -4.0, -3.0, 1.5),
    Variant("E  majors only   (-10%, 4x, -5pt, vol 1.5x)", -10.0, -4.0, -5.0, 1.5),
]


# --- Building the table of every stock-day ------------------------------------

def load_us_bars() -> pd.DataFrame:
    pattern = str(config.US_BARS_DIR / "*.parquet").replace("'", "''")
    bars = duckdb.sql(
        "SELECT symbol, date, low, close, volume FROM read_parquet('%s') "
        "WHERE close > 0 ORDER BY symbol, date" % pattern
    ).df()
    bars["date"] = pd.to_datetime(bars["date"])
    return bars


def build_panel(bars: pd.DataFrame, benchmark: str = config.BENCHMARK) -> pd.DataFrame:
    """One row per stock per day, with everything the rules need.

    Every "normal level" column (sigma, average volume) is built only from days
    BEFORE the row's own day. Forward returns look ahead on purpose: they are
    the outcome being measured, never an input to a rule.
    """
    bars = bars.sort_values(["symbol", "date"]).reset_index(drop=True)
    by = bars.groupby("symbol", sort=False)

    bars["n"] = by.cumcount()
    bars["prev_close"] = by["close"].shift(1)
    bars["ret"] = bars["close"] / bars["prev_close"] - 1.0
    bars["pct"] = bars["ret"] * 100.0
    bars["low_pct"] = (bars["low"] / bars["prev_close"] - 1.0) * 100.0
    bars["sigma"] = by["ret"].transform(lambda s: rules.rolling_sigma(s.to_numpy()))
    bars["z"] = bars["ret"] / bars["sigma"]

    bars["dollar"] = bars["close"] * bars["volume"]
    by = bars.groupby("symbol", sort=False)
    bars["adv20"] = by["dollar"].transform(lambda s: s.rolling(20).mean().shift(1))
    avg_volume = by["volume"].transform(lambda s: s.rolling(20).mean().shift(1))
    bars["rel_volume"] = bars["volume"] / avg_volume

    for k in HORIZONS:
        bars["fwd_%d" % k] = by["close"].shift(-k) / bars["close"] - 1.0

    index = bars.loc[bars["symbol"] == benchmark, ["date", "ret"] + ["fwd_%d" % k for k in HORIZONS]]
    index = index.rename(columns={"ret": "idx_ret", **{"fwd_%d" % k: "idx_fwd_%d" % k for k in HORIZONS}})
    panel = bars[bars["symbol"] != benchmark].merge(index, on="date", how="left")
    panel["vs_index"] = (panel["ret"] - panel["idx_ret"]) * 100.0
    for k in HORIZONS:
        panel["excess_%d" % k] = panel["fwd_%d" % k] - panel["idx_fwd_%d" % k]

    panel["eligible"] = ((panel["prev_close"] >= MIN_PRICE) &
                         (panel["adv20"] >= MIN_DOLLAR_VOLUME) &
                         panel["sigma"].notna())
    return panel


# --- Applying a rule ----------------------------------------------------------

def find_alerts(panel: pd.DataFrame, variant: Variant) -> pd.DataFrame:
    fired = (panel["eligible"].to_numpy()
             & rules.market_rule_mask(panel["pct"].to_numpy(), panel["z"].to_numpy(),
                                      panel["vs_index"].to_numpy(), variant.min_drop_pct,
                                      variant.min_z, variant.min_vs_index)
             & (panel["rel_volume"].to_numpy() >= variant.min_rel_volume))
    alerts = panel[fired].sort_values(["symbol", "n"]).copy()
    alerts["tier"] = alerts["pct"].map(rules.tier_for)

    # Cooldown (PLAN.md section 6): a second alert on the very next trading day
    # only counts if the fall has reached a higher tier.
    rank = alerts["tier"].map(TIER_RANK)
    next_day = (alerts["symbol"] == alerts["symbol"].shift(1)) & (alerts["n"] - alerts["n"].shift(1) == 1)
    repeat = next_day & (rank <= rank.shift(1))
    return alerts[~repeat]


# --- Summaries ----------------------------------------------------------------

def per_day_stats(alerts: pd.DataFrame, trading_days: pd.DatetimeIndex) -> Dict[str, float]:
    counts = alerts.groupby("date").size().reindex(trading_days, fill_value=0)
    return {
        "alerts": int(counts.sum()),
        "days": len(counts),
        "mean": float(counts.mean()),
        "median": float(counts.median()),
        "p95": float(counts.quantile(0.95)),
        "max": int(counts.max()),
        "quiet_days_pct": float((counts == 0).mean() * 100),
    }


def outcome_stats(rows: pd.DataFrame) -> List[dict]:
    out = []
    for k in HORIZONS:
        raw = rows["fwd_%d" % k].dropna()
        excess = rows["excess_%d" % k].dropna()
        if raw.empty:
            out.append({"days": k, "n": 0})
            continue
        out.append({
            "days": k,
            "n": len(raw),
            "median": raw.median() * 100,
            "median_vs_index": excess.median() * 100,
            "mean_vs_index": excess.mean() * 100,
            "higher_pct": (raw > 0).mean() * 100,
            "beat_index_pct": (excess > 0).mean() * 100,
            "bad_case": raw.quantile(0.05) * 100,     # 1 in 20 did worse than this
        })
    return out


# --- Report -------------------------------------------------------------------

def _outcome_table(stats: List[dict]) -> List[str]:
    lines = ["      after   count   median   median vs   mean vs   % higher   % beat    1-in-20",
             "                               index       index     later      index    worse than"]
    for s in stats:
        if not s["n"]:
            lines.append("    %4dd       0" % s["days"])
            continue
        lines.append("    %4dd  %6d  %+6.1f%%   %+6.1f%%    %+6.1f%%    %5.0f%%   %5.0f%%   %+6.1f%%" % (
            s["days"], s["n"], s["median"], s["median_vs_index"], s["mean_vs_index"],
            s["higher_pct"], s["beat_index_pct"], s["bad_case"]))
    return lines


def _in_period(frame: pd.DataFrame, period) -> pd.DataFrame:
    return frame[(frame["date"] >= period[0]) & (frame["date"] <= period[1])]


def run(panel: pd.DataFrame) -> str:
    lines: List[str] = []
    add = lines.append
    eligible = panel[panel["eligible"]]
    first, last = panel["date"].min().date(), panel["date"].max().date()

    add("STOCKSWATCH BACKTEST  (private threshold tuning, not for publication)")
    add("=" * 78)
    add("Data: %s to %s, %d stocks, %s stock-days (%s pass the price and liquidity filters)." % (
        first, last, panel["symbol"].nunique(), format(len(panel), ","), format(len(eligible), ",")))
    add("Filters each day: previous close >= $%.0f, average >= $%.0fm traded a day, 60+ days of history."
        % (MIN_PRICE, MIN_DOLLAR_VOLUME / 1e6))
    add("")
    add("READ THIS FIRST")
    add("  * Survivorship bias: companies that later delisted or went bust are NOT in this data.")
    add("    Real outcomes after big falls were worse than shown here.")
    add("  * Alerts are judged at the day's close; 'after' is measured from that close.")
    add("  * 'vs index' subtracts the S&P 500 tracker (SPY) over the same days.")
    add("  * Past patterns do not predict future prices.")
    add("")

    for label, period in (("TUNING PERIOD 2020-2023", TUNE_PERIOD), ("TEST PERIOD 2024 onwards", TEST_PERIOD)):
        chunk = _in_period(panel, period)
        if chunk.empty:
            continue
        days = pd.DatetimeIndex(sorted(chunk["date"].unique()))
        add("#" * 78)
        add("%s   (%d trading days)" % (label, len(days)))
        add("#" * 78)
        add("")
        add("Baseline: ANY eligible stock on ANY day (what 'no signal at all' looks like)")
        lines.extend(_outcome_table(outcome_stats(chunk[chunk["eligible"]])))
        add("")
        add("How many alerts each rule would have sent")
        add("    %-46s %7s %8s %7s %6s %5s %7s" % ("rule", "total", "per day", "median", "95th%", "max", "quiet"))
        found = {}
        for variant in VARIANTS:
            alerts = find_alerts(chunk, variant)
            found[variant.name] = alerts
            s = per_day_stats(alerts, days)
            add("    %-46s %7d %8.1f %7.0f %6.0f %5d %6.0f%%" % (
                variant.name, s["alerts"], s["mean"], s["median"], s["p95"], s["max"], s["quiet_days_pct"]))
        add("    (per day = average; 95th% = a busy day; quiet = share of days with no alert)")
        add("")
        for variant in VARIANTS:
            alerts = found[variant.name]
            add("What happened after: %s" % variant.name)
            lines.extend(_outcome_table(outcome_stats(alerts)))
            add("")

        default = found[VARIANTS[0].name]
        add("Rule A broken down")
        for title, groups in (
            ("by size of fall", [(t, default[default["tier"] == t]) for t in ("Notable", "Major", "Severe")]),
            ("by how unusual", [("3-4x normal", default[default["z"] > -4]),
                                ("4-6x normal", default[(default["z"] <= -4) & (default["z"] > -6)]),
                                ("6x+ normal", default[default["z"] <= -6])]),
            ("by money traded a day", [("$20m-$100m", default[default["adv20"] < 1e8]),
                                       ("$100m-$500m", default[(default["adv20"] >= 1e8) & (default["adv20"] < 5e8)]),
                                       ("$500m+", default[default["adv20"] >= 5e8])]),
        ):
            add("  %s" % title)
            for name, rows in groups:
                s20 = outcome_stats(rows)[2]
                if not s20["n"]:
                    add("    %-14s no alerts" % name)
                    continue
                add("    %-14s %5d alerts | 20 days later: median %+5.1f%%, vs index %+5.1f%%, "
                    "%2.0f%% higher, 1-in-20 worse than %+5.1f%%" % (
                        name, len(rows), s20["median"], s20["median_vs_index"], s20["higher_pct"], s20["bad_case"]))
        touched = chunk[chunk["eligible"] & (chunk["low_pct"] <= -5.0)]
        closed = chunk[chunk["eligible"] & (chunk["pct"] <= -5.0)]
        add("")
        add("Intraday note: %s eligible stock-days touched -5%% at some point in the day; only %s"
            % (format(len(touched), ","), format(len(closed), ",")))
        add("closed that low (%.0f%%). A live scanner sees the dips that recover, so it fires more often"
            % (100.0 * len(closed) / max(len(touched), 1)))
        add("than these close-based counts.")
        add("")
    return "\n".join(lines)
