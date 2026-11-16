"""Command line entry point.

    python -m stockswatch run      download prices, then show the report
    python -m stockswatch update   download prices only
    python -m stockswatch report   show the report from prices already downloaded

    python -m stockswatch backtest-data   download whole-US-market history (once)
    python -m stockswatch backtest        replay the rules over that history
    python -m stockswatch scan            scan the whole US market right now
    python -m stockswatch publish         scan, then save everything to the database
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


def do_backtest_data() -> None:
    from . import universe
    print("Building the list of US stocks...")
    stocks = universe.build()
    print("  %d stocks in the wide universe" % len(stocks))
    print("Downloading daily prices since %s (several minutes; safe to stop and re-run)..."
          % config.BACKTEST_START)
    rows = universe.download_history()
    print("Done. %d new rows saved under %s" % (rows, config.US_BARS_DIR.relative_to(config.ROOT)))


def do_backtest() -> None:
    from . import backtest
    print("Loading price history...")
    panel = backtest.build_panel(backtest.load_us_bars())
    text = backtest.run(panel)
    config.OUT_DIR.mkdir(exist_ok=True)
    config.BACKTEST_REPORT.write_text(text, encoding="utf-8")
    print(text)
    print("Saved to %s" % config.BACKTEST_REPORT.relative_to(config.ROOT))


def do_scan() -> None:
    from . import scanner
    print("Scanning the US market...")
    print(scanner.to_text(scanner.scan()))
    print()
    print(report.DISCLAIMER)


def main() -> None:
    parser = argparse.ArgumentParser(prog="stockswatch", description="Watchlist drop report")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "update", "report", "backtest-data", "backtest", "scan", "publish"])
    command = parser.parse_args().command
    if command == "scan":
        return do_scan()
    if command == "publish":
        from . import publish
        return publish.publish()
    if command == "backtest-data":
        return do_backtest_data()
    if command == "backtest":
        return do_backtest()
    if command in ("run", "update"):
        do_update()
    if command in ("run", "report"):
        do_report()


if __name__ == "__main__":
    main()
