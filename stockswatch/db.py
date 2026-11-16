"""A very small client for the Supabase database (its automatic REST API).

Uses the SECRET key, so it is only ever used by the Python jobs on a trusted
machine, never by the web app.
"""
from __future__ import annotations

import math
import os
from typing import Iterable, List, Optional

import requests

from . import providers  # noqa: F401  (importing this loads the .env file)


def _clean(value):
    """JSON has no NaN or numpy types: turn them into plain Python values."""
    if value is None:
        return None
    if hasattr(value, "item"):          # numpy number or bool
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "isoformat"):     # dates and times
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


class Db:
    def __init__(self) -> None:
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set in .env")
        self._base = url.rstrip("/") + "/rest/v1/"
        self._headers = {"apikey": key, "Authorization": "Bearer " + key}

    def _send(self, method: str, path: str, prefer: str = "", **kwargs) -> requests.Response:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        response = requests.request(method, self._base + path, headers=headers, timeout=60, **kwargs)
        if not response.ok:
            raise RuntimeError("Database %s %s failed (%d): %s" % (
                method, path.split("?")[0], response.status_code, response.text[:300]))
        return response

    def select(self, table: str, query: str = "select=*") -> List[dict]:
        return self._send("GET", "%s?%s" % (table, query)).json()

    def insert(self, table: str, rows: Iterable[dict]) -> List[dict]:
        rows = [_clean(r) for r in rows]
        if not rows:
            return []
        return self._send("POST", table, prefer="return=representation", json=rows).json()

    def upsert(self, table: str, rows: Iterable[dict], on_conflict: str,
               returning: bool = False, batch: int = 500) -> List[dict]:
        """Insert rows, or update them if a row with the same key already exists."""
        rows = [_clean(r) for r in rows]
        out: List[dict] = []
        prefer = "resolution=merge-duplicates,return=" + ("representation" if returning else "minimal")
        for i in range(0, len(rows), batch):
            response = self._send("POST", "%s?on_conflict=%s" % (table, on_conflict),
                                  prefer=prefer, json=rows[i:i + batch])
            if returning:
                out.extend(response.json())
        return out

    def update(self, table: str, match: str, values: dict) -> None:
        self._send("PATCH", "%s?%s" % (table, match), json=_clean(values))

    def delete(self, table: str, match: str) -> None:
        self._send("DELETE", "%s?%s" % (table, match))
