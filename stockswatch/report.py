"""Turn stored prices into today's watchlist report (terminal table + HTML page)."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

from . import config, rules
from .history import WatchItem

DISCLAIMER = (
    "Information only. Not investment advice or a personal recommendation. "
    "StocksWatch is not authorised or regulated by the Financial Conduct Authority. "
    "Prices may be delayed or wrong. The value of investments can fall as well as "
    "rise and you may get back less than you invest."
)


@dataclass
class Row:
    symbol: str
    name: str
    market: str
    as_of: Optional[date] = None
    close: Optional[float] = None
    pct: Optional[float] = None
    z: Optional[float] = None
    sigma_pct: Optional[float] = None       # normal daily move, in %
    index_pct: Optional[float] = None
    vs_index: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    currency: Optional[str] = None
    verdict: Optional[rules.Verdict] = None
    problem: Optional[str] = None


def build_rows(watchlist: List[WatchItem], bars: pd.DataFrame,
               fundamentals: Dict[str, dict]) -> List[Row]:
    by_symbol = {s: g.dropna(subset=["close"]).reset_index(drop=True) for s, g in bars.groupby("symbol")}
    rows = []
    for item in watchlist:
        facts = fundamentals.get(item.symbol, {})
        row = Row(symbol=item.symbol, name=facts.get("name") or item.symbol, market=item.market,
                  market_cap=facts.get("market_cap"), pe_ratio=facts.get("pe_ratio"),
                  currency=facts.get("currency"))
        g = by_symbol.get(item.symbol)
        if g is None or len(g) < 2:
            row.problem = "no price data"
            rows.append(row)
            continue

        closes = g["close"].tolist()
        row.as_of = g["date"].iloc[-1]
        row.close = closes[-1]
        row.pct = rules.pct_change(closes[-1], closes[-2])

        # "Normal" is measured only on days BEFORE the one being judged.
        sigma = rules.robust_sigma(rules.daily_returns(closes[:-1]))
        if sigma is not None:
            row.sigma_pct = sigma * 100
            row.z = rules.z_score(row.pct, sigma)

        last_year = g.tail(252)
        row.high_52w = float(last_year["high"].max())
        row.low_52w = float(last_year["low"].min())

        index = by_symbol.get(config.INDEX_FOR_MARKET[item.market])
        if index is not None:
            same_day = index.index[index["date"] == row.as_of]
            pos = int(same_day[0]) if len(same_day) else 0
            if pos >= 1:
                row.index_pct = rules.pct_change(index["close"].iloc[pos], index["close"].iloc[pos - 1])
                row.vs_index = row.pct - row.index_pct

        row.verdict = rules.evaluate_watchlist(row.pct, row.z, item.threshold_pct, item.threshold_z)
        rows.append(row)

    # Breaches first, then biggest fall first.
    rows.sort(key=lambda r: (not (r.verdict and r.verdict.alert), r.pct if r.pct is not None else 0))
    return rows


# --- Formatting --------------------------------------------------------------

def _price(row: Row, value: Optional[float]) -> str:
    if value is None:
        return "-"
    if row.currency == "GBp" or (row.currency is None and row.market == "UK"):
        return "%.1fp" % value
    sign = {"USD": "$", "GBP": "£", "EUR": "€"}.get(row.currency or "USD", "")
    return "%s%.2f" % (sign, value)


def _cap(row: Row) -> str:
    if not row.market_cap:
        return "-"
    sign = "£" if row.market == "UK" else "$"
    value = row.market_cap
    if value >= 1e12:
        return "%s%.2ftn" % (sign, value / 1e12)
    if value >= 1e9:
        return "%s%.1fbn" % (sign, value / 1e9)
    return "%s%.0fm" % (sign, value / 1e6)


def _signed(value: Optional[float], suffix: str = "%") -> str:
    return "-" if value is None else "%+.2f%s" % (value, suffix)


def _status(row: Row) -> str:
    if row.problem:
        return row.problem.upper()
    if row.verdict.held:
        return "CHECK DATA"
    if row.verdict.alert:
        return ("BREACH (%s)" % row.verdict.tier) if row.verdict.tier else "BREACH"
    return ""


def to_text(rows: List[Row]) -> str:
    header = "%-8s %-11s %10s %8s %8s %8s %9s %-22s %9s %6s  %s" % (
        "Symbol", "As of", "Close", "Change", "x normal", "Normal", "vs index",
        "52-week range", "Mkt cap", "P/E", "Status")
    lines = [header, "-" * len(header)]
    for r in rows:
        if r.problem:
            lines.append("%-8s %s" % (r.symbol, _status(r)))
            continue
        lines.append("%-8s %-11s %10s %8s %8s %8s %9s %-22s %9s %6s  %s" % (
            r.symbol, r.as_of, _price(r, r.close), _signed(r.pct),
            "-" if r.z is None else "%.1fx" % abs(r.z),
            "-" if r.sigma_pct is None else "%.1f%%" % r.sigma_pct,
            _signed(r.vs_index, "pt"),
            "%s - %s" % (_price(r, r.low_52w), _price(r, r.high_52w)),
            _cap(r), "-" if not r.pe_ratio else "%.0f" % r.pe_ratio, _status(r)))
    return "\n".join(lines)


SOURCE_LABELS = {
    "alpaca": "Alpaca (US, all exchanges)",
    "yahoo": "Yahoo Finance (unofficial)",
}


def to_html(rows: List[Row], sources: Optional[List[str]] = None) -> str:
    e = html.escape
    source_text = "; ".join(SOURCE_LABELS.get(s, s) for s in (sources or ["yahoo"]))
    breaches = [r for r in rows if r.verdict and r.verdict.alert]
    body = []
    for r in rows:
        if r.problem:
            body.append("<tr><td><b>%s</b></td><td colspan=9>%s</td></tr>" % (e(r.symbol), e(r.problem)))
            continue
        cls = "breach" if r.verdict.alert else ("held" if r.verdict.held else "")
        note = "; ".join(r.verdict.reasons) or r.verdict.held or ""
        tag = ""
        if r.verdict.alert:
            tag = '<span class="tag">%s</span>' % e(r.verdict.tier or "Threshold")
        elif r.verdict.held:
            tag = '<span class="tag grey">Check data</span>'
        body.append(
            '<tr class="%s"><td><b>%s</b><br><small>%s</small></td><td>%s<br><small>%s</small></td>'
            '<td class="%s">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
            '<td>%s <small>%s</small></td></tr>' % (
                cls, e(r.symbol), e(r.name), _price(r, r.close), r.as_of,
                "down" if r.pct < 0 else "up", _signed(r.pct),
                "-" if r.z is None else "%.1f&times;" % abs(r.z),
                "-" if r.sigma_pct is None else "%.1f%%" % r.sigma_pct,
                _signed(r.vs_index, " pts"),
                "%s &ndash; %s" % (_price(r, r.low_52w), _price(r, r.high_52w)),
                _cap(r), "-" if not r.pe_ratio else "%.0f" % r.pe_ratio, tag, e(note)))

    if breaches:
        top = breaches[0]
        headline = "%s falls %.1f%%" % (e(top.name), abs(top.pct))
        standfirst = "%d of %d watchlist stocks passed a threshold at the latest close." % (
            len(breaches), len(rows))
    else:
        headline = "No watchlist thresholds passed"
        standfirst = "None of your %d watchlist stocks fell past its threshold at the latest close." % len(rows)

    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StocksWatch</title>
<style>
  body {{ background:#F8ECDF; color:#1E1A17; font-family:-apple-system, Helvetica, Arial, sans-serif;
         margin:0; padding:0 16px 40px; }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  .mast {{ font-family:Georgia, 'Times New Roman', serif; font-size:40px; font-weight:700;
          text-align:center; padding:22px 0 14px; border-bottom:1px solid rgba(30,26,23,.2); }}
  .label {{ color:#8A1C3C; font-weight:600; margin-top:24px; }}
  h1 {{ font-family:Georgia, 'Times New Roman', serif; font-weight:500; font-size:38px; margin:6px 0 8px; }}
  .standfirst {{ color:#6B625B; font-size:17px; margin:0 0 22px; }}
  .scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums; }}
  th {{ text-align:left; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:#6B625B;
       border-top:1px solid rgba(30,26,23,.2); border-bottom:1px solid rgba(30,26,23,.2); padding:8px 10px 8px 0; }}
  td {{ padding:10px 10px 10px 0; border-bottom:1px dotted rgba(30,26,23,.35); vertical-align:top; white-space:nowrap; }}
  td:last-child {{ white-space:normal; }}
  small {{ color:#6B625B; }}
  .down {{ color:#B3261E; font-weight:600; }} .up {{ color:#17693F; font-weight:600; }}
  tr.breach td:first-child {{ box-shadow:inset 3px 0 0 #8A1C3C; padding-left:10px; }}
  .tag {{ display:inline-block; font-size:11px; letter-spacing:.06em; text-transform:uppercase;
         background:#1E1A17; color:#F8ECDF; padding:2px 6px; margin-right:6px; }}
  .tag.grey {{ background:#6B625B; }}
  footer {{ color:#6B625B; font-size:12px; margin-top:28px; line-height:1.5; }}
</style></head><body><div class="wrap">
<div class="mast">StocksWatch</div>
<div class="label">Your watchlist</div>
<h1>{headline}</h1>
<p class="standfirst">{standfirst}</p>
<div class="scroll"><table>
<tr><th>Stock</th><th>Close</th><th>Change</th><th>&times; normal move</th><th>Normal daily move</th>
<th>vs index</th><th>52-week range</th><th>Market cap</th><th>P/E</th><th>Status</th></tr>
{body}
</table></div>
<footer>End-of-day prices, personal use only. Sources: {sources}. Page built {built}.<br>{disclaimer}</footer>
</div></body></html>
""".format(sources=e(source_text), headline=headline, standfirst=e(standfirst), body="\n".join(body),
           built=datetime.now().strftime("%d %b %Y %H:%M"), disclaimer=e(DISCLAIMER))
