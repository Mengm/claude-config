#!/usr/bin/env python3
"""Shared Feishu auth helper — tenant_access_token and user_access_token.

Token strategy (all skill scripts share this module via symlinks):
- Default (as_user=False): tenant_access_token. Covers calendar, task,
  bitable, doc, meeting, approval, mail.
- as_user=True: user_access_token. Required for wiki (user has wiki:wiki
  scope) and user-identity operations (create wiki space, move docs).
- No automatic fallback. Callers choose explicitly.
"""

import os
import sqlite3
import time

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env"))
load_dotenv(ENV_PATH)

def _resolve_app_credentials() -> tuple[str, str]:
    """Resolve app_id/app_secret, preferring TASKPOOL_APP_ID + FEISHU_APPS."""
    import json
    target_app_id = os.environ.get("TASKPOOL_APP_ID", "")
    apps_json = os.environ.get("FEISHU_APPS", "")
    if target_app_id and apps_json:
        try:
            for app in json.loads(apps_json):
                if app["app_id"] == target_app_id:
                    return app["app_id"], app["app_secret"]
        except (json.JSONDecodeError, KeyError):
            pass
    return os.getenv("FEISHU_APP_ID", ""), os.getenv("FEISHU_APP_SECRET", "")

APP_ID, APP_SECRET = _resolve_app_credentials()

BASE = "https://open.feishu.cn/open-apis"

_token_cache = {"token": "", "expires_at": 0}
_user_token_cache = {"token": "", "expires_at": 0}

_DB_PATH = os.environ.get("DUTYAI_DB_PATH", os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "tasks.db")))


def get_token() -> str:
    """Get a cached or fresh tenant_access_token."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to get token: {data}")
    token = data["tenant_access_token"]
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + data.get("expire", 7200)
    return token


def get_user_token() -> str:
    """Get a user_access_token from the main app's SQLite store.

    The main service (feishu_oauth.py) handles refresh automatically.
    This function only reads the stored token.
    """
    now = time.time()
    if _user_token_cache["token"] and _user_token_cache["expires_at"] > now + 60:
        return _user_token_cache["token"]

    conn = sqlite3.connect(_DB_PATH)
    try:
        row = conn.execute(
            "SELECT user_access_token, token_expires_at FROM oauth_tokens WHERE app_id = ?",
            (APP_ID,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("No user_access_token. Run: uv run python feishu_oauth.py authorize")
    token, expires_at = row
    if time.time() > expires_at:
        raise RuntimeError("user_access_token expired. Check main service logs.")

    _user_token_cache["token"] = token
    _user_token_cache["expires_at"] = expires_at
    return token


def headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}


def user_headers() -> dict:
    """Headers using user_access_token (for APIs that require user identity)."""
    return {"Authorization": f"Bearer {get_user_token()}", "Content-Type": "application/json"}


def _request(method: str, path: str, *, body: dict | None = None,
             params: dict | None = None, as_user: bool = False) -> dict:
    """Send a Feishu API request. See module docstring for token strategy."""
    url = f"{BASE}{path}"
    h = user_headers() if as_user else headers()

    kwargs: dict = {"headers": h, "timeout": 30}
    if method in ("GET", "DELETE"):
        if params:
            kwargs["params"] = params
        if method == "DELETE" and body is not None:
            kwargs["json"] = body
    else:
        kwargs["json"] = body or {}
        if params:
            kwargs["params"] = params

    resp = requests.request(method, url, **kwargs)
    try:
        return resp.json()
    except Exception:
        return {"code": resp.status_code, "msg": resp.text[:200]}


def api_get(path: str, params: dict | None = None, as_user: bool = False) -> dict:
    return _request("GET", path, params=params, as_user=as_user)


def api_post(path: str, body: dict | None = None, params: dict | None = None, as_user: bool = False) -> dict:
    return _request("POST", path, body=body, params=params, as_user=as_user)


def api_put(path: str, body: dict | None = None, params: dict | None = None, as_user: bool = False) -> dict:
    return _request("PUT", path, body=body, params=params, as_user=as_user)


def api_patch(path: str, body: dict | None = None, params: dict | None = None, as_user: bool = False) -> dict:
    return _request("PATCH", path, body=body, params=params, as_user=as_user)


def api_delete(path: str, body: dict | None = None, as_user: bool = False) -> dict:
    return _request("DELETE", path, body=body, as_user=as_user)
