"""Scan the market and save the results to the database, where the web app reads them.

    python -m stockswatch publish

One run does, in order: whole-market scan, stock list, each stock's normal
behaviour, latest quotes, alerts (with news and key numbers), your watchlist
(US and UK), and the four figures for the top strip.

Still to come in Phase 1: split/halt checks against a calendar, and sending
notifications. This step only records what the scanner found.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from . import config, history, report, rules, scanner
from .db import Db
from .providers.finnhub import FinnhubProvider
from .providers.yahoo import YahooProvider

RULE_NAME = "market_drop"
MAX_ENRICH = 40                 # Finnhub's free plan allows 60 calls a minute
INDICATORS = [                  # key, label, Yahoo symbol
    ("ftse100", "FTSE 100", "^FTSE"),
    ("sp500", "S&P 500", "^GSPC"),
    ("gbpusd", "Pound/Dollar", "GBPUSD=X"),
    ("brent", "Brent Crude Oil", "BZ=F"),
]
_NAME_TAIL = re.compile(
    r"[\s,]+(class [a-z]\s+)?(common stock|common shares?|ordinary shares?|"
    r"american depositary (shares?|receipts?).*|depositary shares.*|ads|adr)\.?$", re.IGNORECASE)


def clean_name(name: str) -> str:
    """'NVIDIA Corporation Common Stock' -> 'NVIDIA Corporation'."""
    name = (name or "").strip()
    # London listings: 'SHELL PLC ORD EUR0.07' -> 'Shell plc'.
    name = re.sub(r"\s+ord\b.*$", "", name, flags=re.IGNORECASE)
    if name.isupper() and len(name) > 5:
        name = re.sub(r"\bPlc\b", "plc", name.title())
    for _ in range(3):
        shorter = _NAME_TAIL.sub("", name).strip(" ,")
        if shorter == name:
            break
        name = shorter
    return name


def short_name(name: str) -> str:
    """Headline form: 'Heartflow, Inc.' -> 'Heartflow'."""
    name = clean_name(name)
    name = re.sub(r"[\s,]+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|"
                  r"group|n\.?v|s\.?a|ag|se)\.?$", "", name, flags=re.IGNORECASE).strip(" ,")
    return name or "The company"


def biggest_fall_since(symbol: str, pct: float, before: date) -> Optional[str]:
    """A factual clause for the headline, from our own price history."""
    pattern = str(config.US_BARS_DIR / "*.parquet").replace("'", "''")
    rows = duckdb.sql(
        "SELECT date, (close / lag(close) OVER (ORDER BY date) - 1) * 100 AS pct "
        "FROM read_parquet('%s') WHERE symbol = '%s' AND date < DATE '%s' ORDER BY date"
        % (pattern, symbol.replace("'", "''"), before.isoformat())
    ).df()
    if len(rows) < 250:
        return None
    first = pd.to_datetime(rows["date"].iloc[0]).date()
    worse = rows[rows["pct"] <= pct]
    if worse.empty:
        years = (before - first).days // 365
        return "its biggest one-day fall in at least %d years" % years if years >= 2 else None
    last = pd.to_datetime(worse["date"].iloc[-1]).date()
    if (before - last).days > 365:
        return "its biggest one-day fall since %s" % last.strftime("%B %Y")
    return None


def make_headline(name: str, pct: float, clause: Optional[str]) -> str:
    text = "%s falls %.0f%%" % (short_name(name), abs(pct))
    return "%s, %s" % (text, clause) if clause else text


def session_over(bar_date: date, now: datetime) -> bool:
    local = now.astimezone(scanner.NEW_YORK)
    return local.date() > bar_date or local.time() >= time(16, 15)


# --- Steps --------------------------------------------------------------------

def _publish_instruments(db: Db) -> Dict[str, int]:
    stocks = pd.read_parquet(config.UNIVERSE_FILE)
    rows = [{"symbol": r.symbol, "market": "US", "exchange": r.exchange, "name": clean_name(r.name),
             "currency": "USD", "price_unit": "USD", "type": r.type, "is_active": True}
            for r in stocks.itertuples()]
    saved = db.upsert("instruments", rows, on_conflict="symbol,market", returning=True)
    return {r["symbol"]: r["id"] for r in saved}


def _publish_quotes(db: Db, result: scanner.ScanResult, ids: Dict[str, int], stamp: str) -> int:
    frame = result.quotes
    stats, quotes = [], []
    for symbol, row in frame.iterrows():
        if symbol not in ids:
            continue
        stats.append({"instrument_id": ids[symbol], "as_of": row["last_date"], "prev_close": row["prev_close"],
                      "sigma_60d": row["sigma"], "avg_volume_20d": row["avg_volume"],
                      "dollar_volume_20d": row["dollar_volume"], "high_52w": row["high_52w"],
                      "low_52w": row["low_52w"], "updated_at": stamp})
        quotes.append({"instrument_id": ids[symbol], "trading_date": result.bar_date, "price": row["price"],
                       "prev_close": row["prev_close"], "pct_change": row["pct"], "z_score": row["z"],
                       "rel_volume": row["rel_volume"], "dollar_volume": row["dollar_volume"],
                       "eligible": bool(row["eligible"]), "updated_at": stamp})
    db.upsert("instrument_stats", stats, on_conflict="instrument_id")
    db.upsert("quotes", quotes, on_conflict="instrument_id")
    return len(quotes)


def _rule_id(db: Db) -> int:
    found = db.select("rules", "name=eq.%s&version=eq.1&select=id" % RULE_NAME)
    if found:
        return found[0]["id"]
    return db.insert("rules", [{"name": RULE_NAME, "version": 1, "params": {
        "min_drop_pct": rules.MARKET_MIN_DROP_PCT, "min_z": rules.MARKET_MIN_Z,
        "min_vs_index": rules.MARKET_MIN_VS_INDEX, "min_rel_volume": rules.MARKET_MIN_REL_VOLUME,
        "min_price": rules.MIN_PRICE, "min_dollar_volume": rules.MIN_DOLLAR_VOLUME,
        "push_min_dollar_volume": rules.PUSH_MIN_DOLLAR_VOLUME}}])[0]["id"]


def _publish_alerts(db: Db, result: scanner.ScanResult, ids: Dict[str, int], now: datetime,
                    stamp: str) -> Dict[str, int]:
    finnhub = FinnhubProvider(os.getenv("FINNHUB_API_KEY") or "")
    day = result.bar_date
    over = session_over(day, now)
    existing = {(a["instrument_id"], a["tier"]): a for a in db.select(
        "alerts", "trading_date=eq.%s&select=id,instrument_id,tier,status,scans_seen" % day.isoformat())}
    reporting = finnhub.get_earnings_symbols(day - timedelta(days=1), day) if result.alerts else set()
    results_today = {s for s, d, hour in reporting
                     if d == day.isoformat() and hour != "amc"            # before or during today's session
                     or d == (day - timedelta(days=1)).isoformat() and hour == "amc"}   # after yesterday's close
    rule_id = _rule_id(db)
    counts = {"new": 0, "seen_again": 0}

    for number, c in enumerate(result.alerts):
        if c.symbol not in ids:
            continue
        iid = ids[c.symbol]
        figures = {"price": c.price, "pct_change": c.pct, "z_score": c.z, "rel_volume": c.rel_volume,
                   "vs_index": c.vs_index, "dollar_volume": c.dollar_volume, "push_eligible": c.push}
        old = existing.get((iid, c.tier))
        if old:
            # Seen on an earlier scan too: that is the "two scans in a row" confirmation.
            changes = dict(figures, scans_seen=old["scans_seen"] + 1)
            if old["status"] == "pending":
                changes.update(status="confirmed", confirmed_at=stamp)
            db.update("alerts", "id=eq.%d" % old["id"], changes)
            counts["seen_again"] += 1
            continue

        tags = []
        if c.price <= c.low_52w:
            tags.append("52-WEEK LOW")
        if c.gap_pct is not None and c.gap_pct <= -4.0:
            tags.append("GAP DOWN")
        if c.symbol in results_today:
            tags.append("RESULTS DAY")

        news: List[dict] = []
        if number < MAX_ENRICH:
            news = finnhub.get_news(c.symbol, day - timedelta(days=2), day + timedelta(days=1))
            facts = finnhub.get_fundamentals([c.symbol])[c.symbol]
            if facts.get("sector"):
                db.update("instruments", "id=eq.%d" % iid, {"sector": facts["sector"]})
            db.update("instrument_stats", "instrument_id=eq.%d" % iid,
                      {"market_cap": facts.get("market_cap"), "pe_ratio": facts.get("pe_ratio")})

        db.insert("alerts", [dict(
            figures, instrument_id=iid, trading_date=day, rule_id=rule_id, tier=c.tier,
            status="confirmed" if over else "pending", confirmed_at=stamp if over else None,
            triggered_at=stamp, tags=tags, news=news, data_delay="15 min",
            headline=make_headline(c.name, c.pct, biggest_fall_since(c.symbol, c.pct, day)))])
        counts["new"] += 1

    if result.sell_off:
        db.upsert("market_events", [{"market": "US", "trading_date": day, "index_pct": result.index_pct,
                                     "alert_count": len(result.alerts)}], on_conflict="market,trading_date")
    return counts


def _publish_watchlist(db: Db, result: scanner.ScanResult, ids: Dict[str, int], stamp: str) -> str:
    history.update()        # refresh the watchlist's own prices and key numbers (US and UK)
    watchlist = history.load_watchlist()
    rows = report.build_rows(watchlist, history.load_bars(), history.load_fundamentals())
    scanned = set(result.quotes.index)
    item_rows = []
    thresholds = {w.symbol: w for w in watchlist}

    for row in rows:
        if row.problem:
            continue
        uk = row.market == "UK"
        saved = db.upsert("instruments", [{
            "symbol": row.symbol, "market": row.market, "name": clean_name(row.name),
            "currency": "GBP" if uk else "USD", "price_unit": "GBX" if uk else "USD",
            "type": "Common Stock", "is_active": True}], on_conflict="symbol,market", returning=True)
        iid = saved[0]["id"]
        key_numbers = {"market_cap": row.market_cap, "pe_ratio": row.pe_ratio}
        if row.symbol in scanned:
            db.update("instrument_stats", "instrument_id=eq.%d" % iid, key_numbers)
        else:   # London shares, and any US stock outside the scanned universe: end-of-day figures
            db.upsert("instrument_stats", [dict(
                key_numbers, instrument_id=iid, as_of=row.as_of, prev_close=row.close / (1 + row.pct / 100.0),
                sigma_60d=None if row.sigma_pct is None else row.sigma_pct / 100.0,
                high_52w=row.high_52w, low_52w=row.low_52w, updated_at=stamp)], on_conflict="instrument_id")
            db.upsert("quotes", [{
                "instrument_id": iid, "trading_date": row.as_of, "price": row.close,
                "prev_close": row.close / (1 + row.pct / 100.0), "pct_change": row.pct, "z_score": row.z,
                "eligible": False, "updated_at": stamp}], on_conflict="instrument_id")
        item = thresholds[row.symbol]
        item_rows.append({"instrument_id": iid, "threshold_pct": item.threshold_pct,
                          "threshold_z": item.threshold_z, "enabled": True})

    lists = db.select("watchlists", "select=id")
    if len(lists) != 1:
        return ("watchlist prices saved; not yet linked to an account (%d accounts exist)" % len(lists))
    db.upsert("watchlist_items", [dict(r, watchlist_id=lists[0]["id"]) for r in item_rows],
              on_conflict="watchlist_id,instrument_id")
    return "%d watchlist stocks linked to your account" % len(item_rows)


def _publish_indicators(db: Db, stamp: str) -> int:
    today = date.today()
    bars = YahooProvider().get_daily_bars([s for _, _, s in INDICATORS], today - timedelta(days=12), today)
    rows = []
    for order, (key, label, symbol) in enumerate(INDICATORS):
        g = bars[bars["symbol"] == symbol].sort_values("date")
        if len(g) < 2:
            continue
        last, prev = float(g["close"].iloc[-1]), float(g["close"].iloc[-2])
        rows.append({"key": key, "label": label, "value": last, "pct_change": (last / prev - 1) * 100,
                     "as_of": g["date"].iloc[-1], "sort_order": order, "updated_at": stamp})
    db.upsert("market_indicators", rows, on_conflict="key")
    return len(rows)


# --- The whole run ------------------------------------------------------------

def publish(now: Optional[datetime] = None, say=print) -> None:
    now = now or datetime.now(scanner.NEW_YORK)
    stamp = datetime.now(timezone.utc).isoformat()
    db = Db()
    run = db.insert("scan_runs", [{"market": "US", "source": "alpaca delayed_sip"}])[0]
    try:
        say("Scanning the US market...")
        result = scanner.scan(now)
        say(scanner.to_text(result))
        say("")
        ids = _publish_instruments(db)
        say("Saved %d stocks" % len(ids))
        say("Saved %d quotes for %s" % (_publish_quotes(db, result, ids, stamp), result.bar_date))
        counts = _publish_alerts(db, result, ids, now, stamp)
        say("Alerts: %d new, %d seen again" % (counts["new"], counts["seen_again"]))
        say("Watchlist: " + _publish_watchlist(db, result, ids, stamp))
        say("Top strip: %d figures" % _publish_indicators(db, stamp))
        db.update("scan_runs", "id=eq.%d" % run["id"], {
            "status": "ok", "finished_at": datetime.now(timezone.utc).isoformat(),
            "symbols_scanned": result.scanned, "alerts_found": len(result.alerts)})
    except Exception as error:
        db.update("scan_runs", "id=eq.%d" % run["id"], {
            "status": "failed", "finished_at": datetime.now(timezone.utc).isoformat(),
            "note": str(error)[:500]})
        raise
