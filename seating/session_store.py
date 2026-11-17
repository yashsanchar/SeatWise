"""Where a visitor's loaded data is remembered between clicks.

Vercel runs every request on a fresh copy of the app, so a Python variable cannot remember anything. This file
gives the app two ways to remember:

  * RedisStore  - a small free online store (Upstash Redis, added through Vercel's Storage tab). Used when its two
                  settings (URL and token) are present as environment variables.
  * no store    - when the settings are missing (your laptop) the app keeps everything in plain memory, as before.

The store talks to Upstash over its plain web (REST) address, so no extra Python package is needed.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from typing import Dict, Optional

SESSION_TTL_SECONDS = 24 * 60 * 60          # a visitor's data is forgotten after one day of not using the app
MAX_VALUE_BYTES = 900_000                    # Upstash's free plan accepts about 1 MB per request
KEY_PREFIX = "seatwise:session:"


class StoreError(Exception):
    """The online store could not be reached or refused the request."""


def new_session_id() -> str:
    return secrets.token_urlsafe(24)         # random, impossible to guess


def valid_session_id(value: Optional[str]) -> bool:
    return bool(value) and 20 <= len(value) <= 64 and all(c.isalnum() or c in "-_" for c in value)


class RedisStore:
    """Tiny Upstash Redis client: GET and SET with an expiry."""

    def __init__(self, url: str, token: str, timeout: float = 5.0) -> None:
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout

    def _command(self, *parts: object) -> object:
        req = urllib.request.Request(
            self.url, data=json.dumps([str(p) for p in parts]).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            raise StoreError(f"could not reach the online store ({exc})") from exc
        if isinstance(body, dict) and body.get("error"):
            raise StoreError(f"the online store said: {body['error']}")
        return body.get("result") if isinstance(body, dict) else None

    def get(self, session_id: str) -> Optional[str]:
        result = self._command("GET", KEY_PREFIX + session_id)
        return result if isinstance(result, str) else None

    def put(self, session_id: str, value: str) -> None:
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            raise StoreError("the loaded data is too big for the free online store")
        self._command("SET", KEY_PREFIX + session_id, value, "EX", SESSION_TTL_SECONDS)


def store_from_environment(env: Optional[Dict[str, str]] = None) -> Optional[RedisStore]:
    """Build the store from environment variables, or None (plain memory) when they are not set.
    Vercel's Upstash integration names them <PREFIX>KV_REST_API_URL / <PREFIX>KV_REST_API_TOKEN, where the prefix
    can be empty (older projects) or something like STORAGE_ (what Vercel adds by default today). The plain
    UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN pair is understood too. The "read only" token is never used."""
    env = os.environ if env is None else env
    pairs = [("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"), ("KV_REST_API_URL", "KV_REST_API_TOKEN")]
    for name in sorted(env):                                     # any prefix: STORAGE_KV_REST_API_URL, MYDB_KV_REST_API_URL ...
        if name.endswith("_KV_REST_API_URL"):
            pairs.append((name, name[: -len("URL")] + "TOKEN"))
    for url_name, token_name in pairs:
        url, token = env.get(url_name, "").strip(), env.get(token_name, "").strip()
        if url and token:
            return RedisStore(url, token)
    return None
