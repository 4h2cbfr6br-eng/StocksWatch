"""Throwaway server for the Phase 0 push test.

It serves one page, remembers the phone's push subscription, and sends a test
notification on request. Phase 1 replaces this with the real dispatcher.

    .venv/bin/python push_test/server.py
"""
from __future__ import annotations

import base64
import json
import os
import struct
import sys
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
KEY_FILE = DATA / "vapid_private.pem"          # the server's signing key (never leaves the Mac)
SUBS_FILE = DATA / "push_subscriptions.json"   # where each device said "send pushes here"
PORT = int(os.getenv("PORT", "8787"))
# Push services want a contact address in case a sender misbehaves.
CONTACT = os.getenv("VAPID_CONTACT", "mailto:push-test@example.com")

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
}


def load_vapid() -> Vapid:
    DATA.mkdir(exist_ok=True)
    if KEY_FILE.exists():
        return Vapid.from_file(str(KEY_FILE))
    vapid = Vapid()
    vapid.generate_keys()
    vapid.save_key(str(KEY_FILE))
    return vapid


def public_key_text(vapid: Vapid) -> str:
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def load_subs() -> list:
    return json.loads(SUBS_FILE.read_text()) if SUBS_FILE.exists() else []


def save_subs(subs: list) -> None:
    SUBS_FILE.write_text(json.dumps(subs, indent=2))


def solid_png(size: int, rgb: tuple) -> bytes:
    """A plain coloured square, used as the Home Screen icon."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    row = b"\x00" + bytes(rgb) * size
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * size, 9))
            + chunk(b"IEND", b""))


def send_to_all(title: str, body: str) -> list:
    results, keep = [], []
    for sub in load_subs():
        host = sub["endpoint"].split("/")[2]
        try:
            response = webpush(subscription_info=sub,
                               data=json.dumps({"title": title, "body": body}),
                               vapid_private_key=str(KEY_FILE),
                               vapid_claims={"sub": CONTACT})
            results.append({"service": host, "ok": True, "status": response.status_code})
            keep.append(sub)
        except WebPushException as error:
            status = error.response.status_code if error.response is not None else None
            detail = error.response.text[:200] if error.response is not None else str(error)[:200]
            results.append({"service": host, "ok": False, "status": status, "detail": detail})
            if status not in (404, 410):   # 404/410 mean the device unsubscribed: forget it
                keep.append(sub)
    save_subs(keep)
    return results


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in STATIC:
            name, content_type = STATIC[path]
            self._send(200, (HERE / name).read_bytes(), content_type)
        elif path == "/vapid-public-key":
            self._json({"key": PUBLIC_KEY})
        elif path in ("/icon-180.png", "/icon-512.png"):
            self._send(200, solid_png(int(path[6:9]), (0x8A, 0x1C, 0x3C)), "image/png")
        elif path == "/status":
            self._json({"devices": len(load_subs())})
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10_000:
            return self._json({"error": "too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad request"}, 400)

        if self.path == "/subscribe":
            if not str(body.get("endpoint", "")).startswith("https://") or "keys" not in body:
                return self._json({"error": "not a push subscription"}, 400)
            subs = [s for s in load_subs() if s["endpoint"] != body["endpoint"]]
            subs.append({"endpoint": body["endpoint"], "keys": body["keys"]})
            save_subs(subs[-5:])   # a test only ever needs a handful of devices
            self._json({"ok": True})
        elif self.path == "/send":
            results = send_to_all("StocksWatch test",
                                  "Test alert: NVDA -2.0%, 0.8x its normal daily move.")
            self._json({"results": results})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


VAPID = load_vapid()
PUBLIC_KEY = public_key_text(VAPID)

if __name__ == "__main__":
    print("Push test server on http://localhost:%d" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
