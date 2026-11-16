"""The anti-nagging rules: what gets sent, what is held back, and why."""
from datetime import date, datetime, time, timezone

from stockswatch import dispatcher as d
from stockswatch import publish

PROFILE = {"timezone": "Europe/London", "daily_cap_market": 2, "daily_cap_watchlist": 10,
           "quiet_start": "22:00:00", "quiet_end": "07:00:00", "digest_mode": "both"}
AFTERNOON = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)      # 15:30 London, 10:30 New York
NIGHT = datetime(2026, 11, 16, 23, 30, tzinfo=timezone.utc)
TODAY = date(2026, 11, 16)


def alert(iid, name, pct, z, push=True, status="confirmed"):
    return {"id": 100 + iid, "status": status, "push_eligible": push, "trading_date": "2026-11-16",
            "pct_change": pct, "z_score": z, "price": 50.0, "instruments": {"id": iid, "name": name}}


def item(iid, name, pct, z, market="US", day="2026-11-16", threshold_pct=-4, threshold_z=-2.5):
    return {"threshold_pct": threshold_pct, "threshold_z": threshold_z, "enabled": True,
            "instruments": {"id": iid, "name": name, "market": market,
                            "price_unit": "GBX" if market == "UK" else "USD",
                            "quotes": {"trading_date": day, "price": 98.8, "pct_change": pct, "z_score": z}}}


def test_only_confirmed_liquid_alerts_become_messages():
    messages = d.market_messages([alert(1, "Acme", -12.0, -5.0), alert(2, "Thin", -9.0, -4.0, push=False),
                                  alert(3, "Once", -8.0, -4.0, status="pending"),
                                  alert(4, "Split", -50.0, -9.0, status="held")], None)
    assert [m.title for m in messages] == ["Acme −12.0%"]
    assert "5.0× its normal daily move" in messages[0].body


def test_market_wide_fall_is_one_message():
    event = {"id": 7, "trading_date": "2026-11-16", "index_pct": -3.4, "alert_count": 60}
    messages = d.market_messages([alert(i, "S%d" % i, -8.0, -4.0) for i in range(60)], event)
    assert len(messages) == 1 and messages[0].kind == "sell_off"


def test_daily_cap_keeps_the_most_unusual():
    messages = d.market_messages([alert(1, "A", -6.0, -3.5), alert(2, "B", -9.0, -7.0),
                                  alert(3, "C", -7.0, -5.0)], None)
    decisions = d.plan(messages, PROFILE, [], AFTERNOON)
    assert [(x.message.title[0], x.send) for x in decisions] == [("B", True), ("C", True), ("A", False)]
    assert decisions[2].reason == "daily cap reached"


def test_same_stock_is_not_sent_twice_unless_it_gets_worse():
    first = d.market_messages([alert(1, "Acme", -6.0, -4.0)], None)
    sent = [{"kind": "market", "status": "sent", "detail": "%s#%d|x" % (first[0].key, d.tier_of(first[0]))}]
    assert d.plan(d.market_messages([alert(1, "Acme", -7.5, -5.0)], None), PROFILE, sent, AFTERNOON) == []
    worse = d.plan(d.market_messages([alert(1, "Acme", -11.0, -7.0)], None), PROFILE, sent, AFTERNOON)
    assert len(worse) == 1 and worse[0].send          # crossed from Notable to Major


def test_quiet_hours_and_digest_only():
    messages = d.market_messages([alert(1, "Acme", -6.0, -4.0)], None)
    assert d.plan(messages, PROFILE, [], NIGHT)[0].reason == "quiet hours"
    digest_only = dict(PROFILE, digest_mode="digest")
    assert d.plan(messages, digest_only, [], AFTERNOON)[0].reason == "digest-only setting"
    assert d.in_quiet_hours(time(23, 0), time(22, 0), time(7, 0))
    assert not d.in_quiet_hours(time(12, 0), time(22, 0), time(7, 0))


def test_watchlist_uses_own_threshold_and_only_todays_prices():
    items = [item(1, "Nvidia", -4.5, -1.0), item(2, "Apple", -1.0, -0.4),
             item(3, "Tesla", -6.0, -3.0, day="2026-11-13"),             # Friday's price: stale
             item(4, "Old split", -50.2, -20.0)]                          # looks like a 2-for-1 split
    titles = [m.title for m in d.watchlist_messages(items, TODAY, AFTERNOON)]
    assert titles == ["Nvidia −4.5%"]


def test_uk_watchlist_waits_for_the_london_close():
    items = [item(5, "Lloyds Banking Group plc", -5.0, -3.0, market="UK")]
    assert d.watchlist_messages(items, TODAY, AFTERNOON) == []           # 15:30 London
    after = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)
    message = d.watchlist_messages(items, TODAY, after)[0]
    assert "98.8p" in message.body and "London close" in message.body


def test_stock_on_watchlist_and_market_alert_is_sent_once():
    messages = d.market_messages([alert(1, "Nvidia", -8.0, -4.0)], None) + \
        d.watchlist_messages([item(1, "Nvidia", -8.0, -4.0)], TODAY, AFTERNOON)
    decisions = d.plan(messages, PROFILE, [], AFTERNOON)
    assert len(decisions) == 1 and decisions[0].message.kind == "watchlist"
    assert decisions[0].message.alert_id == 101


def test_wording_stays_factual():
    banned = ("dip", "bargain", "opportunity", "cheap", "oversold", "buy")
    messages = d.market_messages([alert(1, "Acme", -12.0, -5.0)], None) + \
        d.watchlist_messages([item(2, "Nvidia", -4.5, -1.0)], TODAY, AFTERNOON) + \
        [d.digest_message([alert(1, "Acme", -12.0, -5.0)], TODAY)]
    for m in messages:
        assert not any(word in (m.title + " " + m.body).lower() for word in banned)


def test_split_or_big_payout_explains_a_fall():
    assert publish.explained_by("10-for-1 share split on 2024-06-10", -90.0, 120.0)
    assert publish.explained_by("dividend:0.25", -8.0, 92.0) is None       # ordinary dividend
    assert "cash payout" in publish.explained_by("dividend:10", -9.0, 91.0)
    assert publish.explained_by(None, -9.0, 91.0) is None
