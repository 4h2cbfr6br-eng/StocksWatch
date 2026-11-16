"""Decide who gets told about what, then send it.

    python -m stockswatch notify        (also runs at the end of "publish")

An ALERT is a fact about a stock, saved once by the publish step.
A NOTIFICATION is one delivery to one person. This file turns the first into
the second, and is where the anti-nagging rules live:

  * only today's prices are pushed (re-running on old data never buzzes a phone)
  * one push per stock, per day, per tier (a second push only if it gets worse)
  * a daily cap, biggest moves first; the rest stay on the front page
  * quiet hours, and a "digest only" setting
  * on a market-wide fall, one push instead of dozens

The deciding part (`plan`) is pure: no internet, no database, so it is tested.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests

from . import rules, scanner
from .db import Db

LONDON = ZoneInfo("Europe/London")
UK_CHECK_TIME = time(16, 45)        # London prices are only trusted after the close
TIER_RANK = {None: 0, "Notable": 1, "Major": 2, "Severe": 3}


@dataclass
class Message:
    kind: str                  # market | watchlist | sell_off | digest
    key: str                   # identifies this event, so it is never sent twice
    title: str
    body: str
    url: str = "/"
    weight: float = 0.0        # bigger = more unusual; decides who wins under the cap
    alert_id: Optional[int] = None
    market_event_id: Optional[int] = None


@dataclass
class Decision:
    message: Message
    send: bool
    reason: str = ""           # why it was not sent


# --- Wording (facts only: see PLAN.md section 10) -------------------------------

def _money(price_unit: str, value: Optional[float]) -> str:
    if value is None:
        return ""
    return "%sp" % ("%.1f" % value).rstrip("0").rstrip(".") if price_unit == "GBX" else "$%.2f" % value


def _pct(value: float) -> str:
    return "%s%.1f%%" % ("−" if value < 0 else "+", abs(value))


def _stock_body(z: Optional[float], price: str, note: str) -> str:
    parts = []
    if z is not None:
        parts.append("%.1f× its normal daily move" % abs(z))
    if price:
        parts.append(price)
    parts.append(note)
    return " · ".join(parts)


# --- What happened today --------------------------------------------------------

def market_messages(alerts: Iterable[dict], event: Optional[dict]) -> List[Message]:
    """Whole-market alerts. On a market-wide fall: one message, not many."""
    if event:
        return [Message(
            kind="sell_off", key="selloff:%s" % event["trading_date"], market_event_id=event["id"],
            title="Market-wide fall: S&P 500 %s" % _pct(float(event["index_pct"] or 0)),
            body="%d stocks passed the alert rule today. Single-stock alerts are paused."
                 % (event.get("alert_count") or 0), weight=99.0)]
    out = []
    for a in alerts:
        if a["status"] != "confirmed" or not a.get("push_eligible"):
            continue
        stock = a["instruments"]
        out.append(Message(
            kind="market", key="stock:%d:%s" % (stock["id"], a["trading_date"]), alert_id=a["id"],
            title="%s %s" % (stock["name"], _pct(float(a["pct_change"]))),
            body=_stock_body(a.get("z_score"), _money("USD", a.get("price")), "15 min delayed"),
            url="/#/stock/%d" % stock["id"], weight=abs(float(a.get("z_score") or 0))))
    return out


def watchlist_messages(items: Iterable[dict], us_date: Optional[date], now: datetime) -> List[Message]:
    """Stocks on one person's watchlist that passed that person's own threshold."""
    london = now.astimezone(LONDON)
    out = []
    for item in items:
        stock = item["instruments"]
        quote = stock.get("quotes")
        if not item.get("enabled", True) or not quote or quote.get("pct_change") is None:
            continue
        pct = float(quote["pct_change"])
        z = None if quote.get("z_score") is None else float(quote["z_score"])
        day = date.fromisoformat(quote["trading_date"])
        if stock["market"] == "UK":
            if day != london.date() or london.time() < UK_CHECK_TIME:
                continue
            note = "London close"
        else:
            if day != us_date:
                continue
            note = "15 min delayed"
        breached = pct <= float(item["threshold_pct"]) or (z is not None and z <= float(item["threshold_z"]))
        if not breached or pct >= 0:
            continue
        # A fall this size is far more often a split or a bad price than real news.
        if pct <= rules.SUSPECT_DROP_PCT or rules.looks_like_split(pct):
            continue
        out.append(Message(
            kind="watchlist", key="stock:%d:%s" % (stock["id"], day.isoformat()),
            title="%s %s" % (stock["name"], _pct(pct)),
            body=_stock_body(z, _money(stock.get("price_unit") or "USD", quote.get("price")),
                             "watchlist · " + note),
            url="/#/stock/%d" % stock["id"], weight=abs(z) if z is not None else abs(pct)))
    return out


def digest_message(alerts: List[dict], trading_date: date) -> Optional[Message]:
    confirmed = [a for a in alerts if a["status"] == "confirmed"]
    if not confirmed:
        return None
    worst = min(confirmed, key=lambda a: float(a["pct_change"]))
    count = len(confirmed)
    return Message(
        kind="digest", key="digest:%s" % trading_date.isoformat(),
        title="Today's US edition: %d large fall%s" % (count, "" if count == 1 else "s"),
        body="Biggest: %s %s." % (worst["instruments"]["name"], _pct(float(worst["pct_change"]))))


# --- The anti-nagging rules ------------------------------------------------------

def in_quiet_hours(local: time, start: time, end: time) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= local < end
    return local >= start or local < end          # e.g. 22:00 to 07:00, across midnight


def tier_of(message: Message) -> int:
    """Read the size band back out of a title like 'Nvidia −15.2%'."""
    try:
        pct = -float(message.title.rsplit("−", 1)[1].rstrip("%"))
    except (IndexError, ValueError):
        return 0
    return TIER_RANK[rules.tier_for(pct)]


def plan(messages: List[Message], profile: dict, already: List[dict], now: datetime) -> List[Decision]:
    """Apply dedupe, digest-only, quiet hours and the daily caps for ONE person.

    `already` is that person's notification rows from today: dicts with
    "kind", "status" and "detail" (which starts with "key#tier|").
    """
    local = now.astimezone(ZoneInfo(profile.get("timezone") or "Europe/London"))
    quiet = in_quiet_hours(local.time(), _time(profile.get("quiet_start"), time(22, 0)),
                           _time(profile.get("quiet_end"), time(7, 0)))
    best_tier: Dict[str, int] = {}
    sent = {"market": 0, "watchlist": 0}
    for row in already:
        key, _, tier = (row.get("detail") or "").split("|", 1)[0].partition("#")
        if row.get("status") in ("sent", "skipped"):
            best_tier[key] = max(best_tier.get(key, -1), int(tier or 0))
        if row.get("status") == "sent" and row.get("kind") in sent and row.get("today", True):
            sent[row["kind"]] += 1
    caps = {"market": int(profile.get("daily_cap_market") or 5),
            "watchlist": int(profile.get("daily_cap_watchlist") or 10)}

    # A watchlist stock that is also a market alert is sent once, as the watchlist one.
    by_key: Dict[str, Message] = {}
    for m in sorted(messages, key=lambda m: m.kind != "watchlist"):
        if m.key in by_key:
            if by_key[m.key].alert_id is None:
                by_key[m.key].alert_id = m.alert_id
            continue
        by_key[m.key] = m

    decisions = []
    for m in sorted(by_key.values(), key=lambda m: -m.weight):
        if m.key in best_tier and tier_of(m) <= best_tier[m.key]:
            continue                                   # already handled today, and no worse since
        mode = profile.get("digest_mode") or "both"
        if m.kind == "digest" and mode == "live":
            continue
        if m.kind != "digest" and mode == "digest":
            decisions.append(Decision(m, False, "digest-only setting"))
        elif quiet:
            decisions.append(Decision(m, False, "quiet hours"))
        elif m.kind in caps and sent[m.kind] >= caps[m.kind]:
            decisions.append(Decision(m, False, "daily cap reached"))
        else:
            decisions.append(Decision(m, True))
            if m.kind in sent:
                sent[m.kind] += 1
    return decisions


def _time(text, default: time) -> time:
    try:
        return time.fromisoformat(str(text)[:8])
    except (TypeError, ValueError):
        return default


# --- Sending ---------------------------------------------------------------------

class WebPush:
    """Sends to phones and browsers that switched notifications on."""

    def __init__(self):
        self.private_key = os.getenv("VAPID_PRIVATE_KEY") or ""
        self.contact = os.getenv("VAPID_CONTACT") or "mailto:push@example.com"

    @property
    def ready(self) -> bool:
        return bool(self.private_key)

    def send(self, subscription: dict, message: Message) -> str:
        """Returns "ok", "gone" (device unsubscribed) or an error description."""
        from pywebpush import WebPushException, webpush
        payload = json.dumps({"title": message.title, "body": message.body, "url": message.url})
        try:
            webpush(subscription_info={"endpoint": subscription["endpoint"], "keys": subscription["keys"]},
                    data=payload, vapid_private_key=self.private_key,
                    vapid_claims={"sub": self.contact}, ttl=3600, timeout=20)
            return "ok"
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            return "gone" if status in (404, 410) else "error %s" % (status or str(error)[:80])
        except requests.RequestException as error:
            return "error %s" % type(error).__name__


class Telegram:
    """Backup channel: the same alert as a Telegram message (optional)."""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN") or ""
        self.chat = os.getenv("TELEGRAM_CHAT_ID") or ""

    @property
    def ready(self) -> bool:
        return bool(self.token and self.chat)

    def send(self, message: Message) -> str:
        try:
            response = requests.post("https://api.telegram.org/bot%s/sendMessage" % self.token, timeout=20,
                                     json={"chat_id": self.chat, "text": "%s\n%s" % (message.title, message.body)})
            return "ok" if response.status_code == 200 else "error %d" % response.status_code
        except requests.RequestException as error:
            return "error %s" % type(error).__name__


def ping_heartbeat(ok: bool = True) -> None:
    """Tell an outside monitor that a scan ran, so silence gets noticed (optional)."""
    url = os.getenv("HEARTBEAT_URL")
    if not url:
        return
    try:
        requests.get(url if ok else url.rstrip("/") + "/fail", timeout=10)
    except requests.RequestException:
        pass


# --- The whole run ----------------------------------------------------------------

def dispatch(db: Optional[Db] = None, now: Optional[datetime] = None, say: Callable = print,
             push: Optional[WebPush] = None, telegram: Optional[Telegram] = None) -> Dict[str, int]:
    db = db or Db()
    now = now or datetime.now(timezone.utc)
    push, telegram = push or WebPush(), telegram or Telegram()
    counts = {"sent": 0, "held_back": 0, "failed": 0}

    # Only a US trading day that is still "today" in New York can be pushed.
    new_york = now.astimezone(scanner.NEW_YORK)
    us_date = new_york.date()
    alerts = db.select("alerts", "trading_date=eq.%s&select=*,instruments(id,symbol,name)" % us_date.isoformat())
    events = db.select("market_events", "market=eq.US&trading_date=eq.%s" % us_date.isoformat())
    market = market_messages(alerts, events[0] if events else None)
    if new_york.time() >= time(16, 15):
        digest = digest_message(alerts, us_date)
        if digest:
            market.append(digest)

    profiles = db.select("profiles", "select=*")
    devices = db.select("push_subscriptions", "select=id,user_id,endpoint,keys")
    items = db.select(
        "watchlist_items",
        "select=threshold_pct,threshold_z,enabled,watchlists!inner(user_id),"
        "instruments!inner(id,symbol,name,market,price_unit,quotes(trading_date,price,pct_change,z_score))")
    since = (now - timedelta(hours=36)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    history = db.select("notifications", "sent_at=gte.%s&select=user_id,kind,status,detail,sent_at" % since)

    if not push.ready and not telegram.ready:
        say("Notifications: no sending keys are set, so nothing can be sent")
        return counts

    for profile in profiles:
        user = profile["user_id"]
        zone = ZoneInfo(profile.get("timezone") or "Europe/London")
        today = now.astimezone(zone).date()
        already = [dict(h, today=datetime.fromisoformat(h["sent_at"].replace("Z", "+00:00"))
                        .astimezone(zone).date() == today)
                   for h in history if h["user_id"] == user]
        own_items = [i for i in items if i["watchlists"]["user_id"] == user]
        messages = market + watchlist_messages(own_items, us_date, now)
        own_devices = [d for d in devices if d["user_id"] == user]

        for decision in plan(messages, profile, already, now):
            m = decision.message
            detail = "%s#%d|%s — %s" % (m.key, tier_of(m), m.title, m.body)
            base = {"user_id": user, "alert_id": m.alert_id, "market_event_id": m.market_event_id,
                    "kind": m.kind}
            if not decision.send:
                db.insert("notifications", [dict(base, channel="web_push", status="skipped",
                                                 detail=detail + " [%s]" % decision.reason)])
                counts["held_back"] += 1
                continue
            if not own_devices and not telegram.ready:
                say("Notifications: %s is ready to send, but no phone or browser has notifications on"
                    % m.title)
                continue

            delivered = False
            if push.ready and own_devices:
                results = []
                for device in own_devices:
                    outcome = push.send(device, m)
                    results.append(outcome)
                    if outcome == "ok":
                        db.update("push_subscriptions", "id=eq.%d" % device["id"],
                                  {"last_ok_at": now.astimezone(timezone.utc).isoformat()})
                    elif outcome == "gone":
                        db.delete("push_subscriptions", "id=eq.%d" % device["id"])
                ok = "ok" in results
                delivered = delivered or ok
                db.insert("notifications", [dict(base, channel="web_push", status="sent" if ok else "failed",
                                                 detail=detail if ok else detail + " [%s]" % ", ".join(results))])
            if telegram.ready:
                outcome = telegram.send(m)
                delivered = delivered or outcome == "ok"
                db.insert("notifications", [dict(base, channel="telegram",
                                                 status="sent" if outcome == "ok" else "failed",
                                                 detail=detail if outcome == "ok" else detail + " [%s]" % outcome)])
            counts["sent" if delivered else "failed"] += 1
            say("Notifications: %s %s" % ("sent" if delivered else "FAILED to send", m.title))

    say("Notifications: %(sent)d sent, %(held_back)d held back, %(failed)d failed" % counts)
    return counts


def send_test(db: Optional[Db] = None, say: Callable = print) -> None:
    """One test push to every registered device, to prove the pipe works."""
    db = db or Db()
    push = WebPush()
    devices = db.select("push_subscriptions", "select=id,user_id,endpoint,keys")
    if not push.ready:
        return say("No VAPID key is set in .env, so nothing can be sent.")
    if not devices:
        return say("No phone or browser has switched notifications on yet.")
    message = Message(kind="test", key="test", title="StocksWatch test",
                      body="Notifications are working on this device.")
    for device in devices:
        outcome = push.send(device, message)
        if outcome == "gone":
            db.delete("push_subscriptions", "id=eq.%d" % device["id"])
        db.insert("notifications", [{"user_id": device["user_id"], "kind": "test", "channel": "web_push",
                                     "status": "sent" if outcome == "ok" else "failed",
                                     "detail": "test [%s]" % outcome}])
        say("Test push: %s" % outcome)
