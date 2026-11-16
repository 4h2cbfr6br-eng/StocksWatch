"""Whole-market scanner: one pass over every US stock in the universe.

Takes a price snapshot of the market (15 minutes delayed on the free plan),
compares each stock with its own normal behaviour, and returns the ones that
pass the rules. This module only finds candidates. Checking for splits and
halts, adding news, and sending notifications are separate steps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

from . import config, rules

NEW_YORK = ZoneInfo("America/New_York")
SESSION_MINUTES = 390          # 09:30 to 16:00 New York time


@dataclass
class Candidate:
    symbol: str
    name: str
    price: float
    pct: float
    z: float
    vs_index: float
    rel_volume: float
    dollar_volume: float       # average traded per day
    tier: Optional[str]
    push: bool                 # big enough to buzz the phone
    high_52w: float
    low_52w: float


@dataclass
class ScanResult:
    bar_date: Optional[date]           # the trading day the prices belong to
    index_pct: Optional[float]
    scanned: int
    sell_off: bool
    alerts: List[Candidate] = field(default_factory=list)
    held: List[str] = field(default_factory=list)    # "SYMBOL: reason" for suppressed candidates


# --- What is "normal" for each stock ------------------------------------------

def compute_stats(before: date) -> pd.DataFrame:
    """Per stock: normal daily move, average volume and 52-week range, using
    only trading days BEFORE `before`."""
    pattern = str(config.US_BARS_DIR / "*.parquet").replace("'", "''")
    bars = duckdb.sql(
        "SELECT symbol, date, high, low, close, volume FROM read_parquet('%s') "
        "WHERE close > 0 AND date < DATE '%s' ORDER BY symbol, date" % (pattern, before.isoformat())
    ).df()
    return stats_from_bars(bars)


def stats_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for symbol, g in bars.groupby("symbol", sort=False):
        closes = g["close"].to_numpy()
        last20 = g.tail(20)
        last_year = g.tail(252)
        rows.append({
            "symbol": symbol,
            "last_date": g["date"].iloc[-1],
            "sigma": rules.robust_sigma(rules.daily_returns(closes[-(rules.SIGMA_WINDOW + 1):])),
            "dollar_volume": float((last20["close"] * last20["volume"]).mean()) if len(g) >= 20 else np.nan,
            "avg_volume": float(last20["volume"].mean()) if len(g) >= 20 else np.nan,
            "high_52w": float(last_year["high"].max()),
            "low_52w": float(last_year["low"].min()),
        })
    return pd.DataFrame(rows).set_index("symbol")


# --- Judging one snapshot of the market ---------------------------------------

def session_fraction(bar_date: date, now: datetime) -> float:
    """How much of the trading day has passed (0.05 to 1.0), for scaling volume."""
    local = now.astimezone(NEW_YORK)
    if local.date() != bar_date:
        return 1.0
    minutes = (local.hour * 60 + local.minute) - (9 * 60 + 30)
    return float(min(max(minutes / SESSION_MINUTES, 0.05), 1.0))


def evaluate(snapshots: Dict[str, dict], stats: pd.DataFrame, names: Dict[str, str],
             now: datetime, benchmark: str = config.BENCHMARK) -> ScanResult:
    """Apply the whole-market rule to one snapshot. No internet, no files."""
    table = []
    for symbol, snap in snapshots.items():
        today, prev = (snap or {}).get("dailyBar"), (snap or {}).get("prevDailyBar")
        if not today or not prev or not prev.get("c") or not today.get("c"):
            continue
        table.append((symbol, today["t"][:10], today["c"], prev["c"], today.get("v") or 0))
    frame = pd.DataFrame(table, columns=["symbol", "bar_date", "price", "prev_close", "volume"])
    if frame.empty:
        return ScanResult(None, None, 0, False)

    # Use the trading day most stocks are on; ignore stragglers that have not traded today.
    bar_day = frame["bar_date"].mode().iloc[0]
    frame = frame[frame["bar_date"] == bar_day].set_index("symbol")
    bar_date = date.fromisoformat(bar_day)
    frame["pct"] = (frame["price"] / frame["prev_close"] - 1.0) * 100.0

    index_pct = float(frame.at[benchmark, "pct"]) if benchmark in frame.index else None
    frame = frame.drop(index=benchmark, errors="ignore").join(stats, how="inner")

    fraction = session_fraction(bar_date, now)
    frame["z"] = (frame["pct"] / 100.0) / frame["sigma"]
    frame["vs_index"] = frame["pct"] - index_pct if index_pct is not None else np.nan
    frame["rel_volume"] = frame["volume"] / (frame["avg_volume"] * fraction)

    eligible = ((frame["prev_close"] >= rules.MIN_PRICE)
                & (frame["dollar_volume"] >= rules.MIN_DOLLAR_VOLUME)
                & frame["sigma"].notna())
    falls_far_enough = (frame["pct"] <= rules.MARKET_MIN_DROP_PCT) & eligible
    passes = (eligible
              & rules.market_rule_mask(frame["pct"].to_numpy(), frame["z"].to_numpy(),
                                       frame["vs_index"].to_numpy())
              & (frame["rel_volume"] >= rules.MARKET_MIN_REL_VOLUME))

    result = ScanResult(bar_date, index_pct, int(eligible.sum()), False)
    for symbol, row in frame[falls_far_enough].iterrows():
        reason = rules.evaluate_market(row["pct"], row["z"], row["vs_index"]).held
        if reason:
            result.held.append("%s (%.1f%%): %s" % (symbol, row["pct"], reason))
    for symbol, row in frame[passes].sort_values("z").iterrows():
        result.alerts.append(Candidate(
            symbol=symbol, name=names.get(symbol, symbol), price=float(row["price"]),
            pct=float(row["pct"]), z=float(row["z"]), vs_index=float(row["vs_index"]),
            rel_volume=float(row["rel_volume"]), dollar_volume=float(row["dollar_volume"]),
            tier=rules.tier_for(row["pct"]),
            push=bool(row["dollar_volume"] >= rules.PUSH_MIN_DOLLAR_VOLUME),
            high_52w=float(row["high_52w"]), low_52w=float(row["low_52w"])))

    result.sell_off = ((index_pct is not None and index_pct <= rules.SELL_OFF_INDEX_PCT)
                       or len(result.alerts) > rules.SELL_OFF_ALERT_COUNT)
    return result


# --- The live scan (talks to Alpaca) ------------------------------------------

def scan(now: Optional[datetime] = None) -> ScanResult:
    from . import universe
    now = now or datetime.now(NEW_YORK)
    stocks = pd.read_parquet(config.UNIVERSE_FILE)
    names = dict(zip(stocks["symbol"], stocks["name"]))
    snapshots = universe._alpaca().get_snapshots(stocks["symbol"].tolist() + [config.BENCHMARK])

    days = [s["dailyBar"]["t"][:10] for s in snapshots.values() if s and s.get("dailyBar")]
    bar_date = date.fromisoformat(max(set(days), key=days.count))
    return evaluate(snapshots, compute_stats(before=bar_date), names, now)


def to_text(result: ScanResult) -> str:
    if result.bar_date is None:
        return "No prices came back."
    lines = ["Whole-market scan for %s (prices 15 minutes delayed)" % result.bar_date.strftime("%a %d %b %Y"),
             "%d stocks checked. S&P 500 tracker: %s" % (
                 result.scanned, "-" if result.index_pct is None else "%+.2f%%" % result.index_pct)]
    if result.sell_off:
        lines.append("SELL-OFF MODE: market-wide fall. One summary alert would be sent instead of %d."
                     % len(result.alerts))
    for title, wanted in (("WOULD PUSH TO PHONE", True), ("FRONT PAGE ONLY", False)):
        group = [c for c in result.alerts if c.push == wanted]
        lines.append("")
        lines.append("%s (%d)" % (title, len(group)))
        for c in group:
            lines.append("  %-6s %-34s $%-8.2f %+6.1f%%  %4.1fx normal  %+5.1fpt vs index  vol %4.1fx  %s" % (
                c.symbol, c.name[:34], c.price, c.pct, abs(c.z), c.vs_index, c.rel_volume, c.tier or ""))
    if result.held:
        lines.append("")
        lines.append("HELD FOR CHECKING (%d)" % len(result.held))
        lines.extend("  " + h for h in result.held)
    return "\n".join(lines)
