"""Proves the database keeps each user's data private.

Creates two throwaway accounts (A and B), tries every way A might read or
change B's data, then deletes both accounts. Run it after any change to the
database rules:

    .venv/bin/python scripts/check_security.py
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
URL = ENV["SUPABASE_URL"].rstrip("/")
SECRET = {"apikey": ENV["SUPABASE_SECRET_KEY"], "Authorization": "Bearer " + ENV["SUPABASE_SECRET_KEY"]}
PUBLIC_KEY = ENV["SUPABASE_PUBLISHABLE_KEY"]
REST = URL + "/rest/v1/"
RETURN = {"Prefer": "return=representation"}

results = []


def check(description: str, passed: bool, detail: str = "") -> None:
    results.append(passed)
    print("  %s  %s%s" % ("PASS" if passed else "FAIL", description, "" if passed else "   <-- " + detail))


def make_user(tag: str) -> dict:
    email = "rls-test-%s-%s@example.com" % (tag, secrets.token_hex(4))
    password = secrets.token_urlsafe(24)
    created = requests.post(URL + "/auth/v1/admin/users", headers=SECRET, timeout=30,
                            json={"email": email, "password": password, "email_confirm": True})
    created.raise_for_status()
    signed_in = requests.post(URL + "/auth/v1/token?grant_type=password", headers={"apikey": PUBLIC_KEY},
                              json={"email": email, "password": password}, timeout=30)
    signed_in.raise_for_status()
    return {"id": created.json()["id"],
            "headers": {"apikey": PUBLIC_KEY, "Authorization": "Bearer " + signed_in.json()["access_token"]}}


def rows(user: dict, path: str) -> list:
    reply = requests.get(REST + path, headers=user["headers"], timeout=30)
    return reply.json() if reply.ok else []


def main() -> int:
    users, instrument_id = [], None
    try:
        a, b = make_user("a"), make_user("b")
        users = [a, b]
        made = requests.post(REST + "instruments", headers={**SECRET, **RETURN}, timeout=30,
                             json={"symbol": "ZZTEST", "market": "US", "name": "Security test"})
        made.raise_for_status()
        instrument_id = made.json()[0]["id"]

        a_lists, b_lists = rows(a, "watchlists?select=*"), rows(b, "watchlists?select=*")
        print("New accounts")
        check("each new user automatically gets one watchlist", len(a_lists) == 1 and len(b_lists) == 1,
              "A has %d, B has %d" % (len(a_lists), len(b_lists)))
        check("each new user automatically gets a profile",
              len(rows(a, "profiles?select=*")) == 1 and len(rows(b, "profiles?select=*")) == 1)
        if not a_lists or not b_lists:
            return 1
        a_list, b_list = a_lists[0]["id"], b_lists[0]["id"]

        print("Reading")
        check("A sees only A's watchlist", [w["user_id"] for w in a_lists] == [a["id"]])
        check("A cannot fetch B's watchlist by its id", rows(a, "watchlists?id=eq.%d" % b_list) == [])
        check("A sees only A's profile", [p["user_id"] for p in rows(a, "profiles?select=*")] == [a["id"]])

        # Give B some private rows using the jobs' key, then see whether A can find them.
        requests.post(REST + "watchlist_items", headers=SECRET, timeout=30,
                      json={"watchlist_id": b_list, "instrument_id": instrument_id}).raise_for_status()
        requests.post(REST + "push_subscriptions", headers=SECRET, timeout=30,
                      json={"user_id": b["id"], "endpoint": "https://example.com/" + secrets.token_hex(6),
                            "keys": {}}).raise_for_status()
        requests.post(REST + "notifications", headers=SECRET, timeout=30,
                      json={"user_id": b["id"], "kind": "test", "channel": "web_push",
                            "status": "sent"}).raise_for_status()
        check("B can see B's own watchlist item", len(rows(b, "watchlist_items?select=*")) == 1)
        check("A cannot see B's watchlist items", rows(a, "watchlist_items?select=*") == [])
        check("A cannot see B's push subscription", rows(a, "push_subscriptions?select=*") == [])
        check("A cannot see B's notifications", rows(a, "notifications?select=*") == [])
        check("B can see B's own notification", len(rows(b, "notifications?select=*")) == 1)

        print("Changing")
        hdr = {**a["headers"], **RETURN}
        r = requests.post(REST + "watchlists", headers=hdr, json={"user_id": b["id"], "name": "planted"}, timeout=30)
        check("A cannot create a watchlist owned by B", not r.ok, "status %d" % r.status_code)
        r = requests.patch(REST + "watchlists?id=eq.%d" % b_list, headers=hdr, json={"name": "hacked"}, timeout=30)
        check("A cannot rename B's watchlist", r.ok and r.json() == [] or not r.ok, r.text[:80])
        r = requests.delete(REST + "watchlists?id=eq.%d" % b_list, headers=hdr, timeout=30)
        check("A cannot delete B's watchlist", (r.ok and r.json() == []) or not r.ok, r.text[:80])
        check("B's watchlist is untouched", [w["name"] for w in rows(b, "watchlists?select=*")] == ["My watchlist"])
        r = requests.post(REST + "watchlist_items", headers=hdr, timeout=30,
                          json={"watchlist_id": b_list, "instrument_id": instrument_id, "threshold_pct": -1})
        check("A cannot add a stock to B's watchlist", not r.ok, "status %d" % r.status_code)
        r = requests.patch(REST + "profiles?user_id=eq.%s" % a["id"], headers=hdr, json={"user_id": b["id"]}, timeout=30)
        check("A cannot turn A's profile into B's", not r.ok, "status %d" % r.status_code)
        r = requests.post(REST + "notifications", headers=hdr, timeout=30,
                          json={"user_id": a["id"], "kind": "test", "channel": "web_push", "status": "sent"})
        check("A cannot forge a notification record", not r.ok, "status %d" % r.status_code)

        print("A's own data and market data")
        r = requests.post(REST + "watchlist_items", headers=hdr, timeout=30,
                          json={"watchlist_id": a_list, "instrument_id": instrument_id})
        check("A can add a stock to A's own watchlist", r.status_code == 201, r.text[:80])
        r = requests.patch(REST + "profiles?user_id=eq.%s" % a["id"], headers=hdr, json={"daily_cap_market": 3}, timeout=30)
        check("A can change A's own settings", r.ok and len(r.json()) == 1, r.text[:80])
        check("A can read the stock list", len(rows(a, "instruments?symbol=eq.ZZTEST")) == 1)
        r = requests.post(REST + "instruments", headers=hdr, json={"symbol": "ZZFAKE", "market": "US"}, timeout=30)
        check("A cannot add to the stock list", not r.ok, "status %d" % r.status_code)
        r = requests.post(REST + "alerts", headers=hdr, timeout=30,
                          json={"instrument_id": instrument_id, "trading_date": "2026-01-01"})
        check("A cannot create a fake alert", not r.ok, "status %d" % r.status_code)
        r = requests.delete(REST + "instruments?symbol=eq.ZZTEST", headers=hdr, timeout=30)
        check("A cannot delete from the stock list", not r.ok or r.json() == [], r.text[:80])
    finally:
        print("Cleaning up")
        for user in users:
            gone = requests.delete(URL + "/auth/v1/admin/users/" + user["id"], headers=SECRET, timeout=30)
            print("  test account deleted" if gone.ok else "  COULD NOT DELETE test account %s" % user["id"])
        if instrument_id:
            requests.delete(REST + "instruments?id=eq.%d" % instrument_id, headers=SECRET, timeout=30)
        left = [requests.get(REST + t + "?select=*", headers=SECRET, timeout=30).json()
                for t in ("watchlists", "profiles", "watchlist_items", "push_subscriptions", "notifications")]
        test_stock = requests.get(REST + "instruments?symbol=like.ZZ*", headers=SECRET, timeout=30).json()
        print("  rows left behind: %d" % (sum(len(x) for x in left) + len(test_stock)))

    print()
    print("%d of %d checks passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
