"""Command line entry point.

    python -m stockswatch run      download prices, then show the report
    python -m stockswatch update   download prices only
    python -m stockswatch report   show the report from prices already downloaded
"""
from __future__ import annotations

import argparse

from . import config, history, report


def do_update() -> None:
    print("Downloading %d years of daily prices..." % config.HISTORY_YEARS)
    bars = history.update()
    print("Saved %d rows for %d symbols to %s" % (
        len(bars), bars["symbol"].nunique(), config.BARS_FILE.relative_to(config.ROOT)))
    for source, group in bars.groupby("source"):
        print("  from %-7s %s" % (source + ":", ", ".join(sorted(group["symbol"].unique()))))
    missing = [w.symbol for w in history.load_watchlist() if w.symbol not in set(bars["symbol"])]
    if missing:
        print("WARNING: no prices came back for: %s" % ", ".join(missing))


def do_report() -> None:
    bars = history.load_bars()
    rows = report.build_rows(history.load_watchlist(), bars, history.load_fundamentals())
    sources = sorted(bars["source"].unique()) if "source" in bars else ["yahoo"]
    print()
    print(report.to_text(rows))
    config.OUT_DIR.mkdir(exist_ok=True)
    config.REPORT_FILE.write_text(report.to_html(rows, sources), encoding="utf-8")
    print()
    print("Page written to %s" % config.REPORT_FILE.relative_to(config.ROOT))
    print(report.DISCLAIMER)


def main() -> None:
    parser = argparse.ArgumentParser(prog="stockswatch", description="Watchlist drop report")
    parser.add_argument("command", choices=["run", "update", "report"], nargs="?", default="run")
    command = parser.parse_args().command
    if command in ("run", "update"):
        do_update()
    if command in ("run", "report"):
        do_report()


if __name__ == "__main__":
    main()
