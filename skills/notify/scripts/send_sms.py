#!/usr/bin/env python3
"""Send SMS via UniSMS API."""

import argparse
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env"))
load_dotenv(ENV_PATH)

ACCESS_KEY_ID = os.getenv("UNISMS_ACCESS_KEY_ID", "")
ACCESS_KEY_SECRET = os.getenv("UNISMS_ACCESS_KEY_SECRET", "")
DEFAULT_SIGNATURE = os.getenv("UNISMS_SIGNATURE", "")
DEFAULT_TEMPLATE_ID = os.getenv("UNISMS_TEMPLATE_ID", "")

API_BASE = "https://uni.apistd.com"


def _build_signed_url(action):
    query = {
        "action": action,
        "accessKeyId": ACCESS_KEY_ID,
        "algorithm": "hmac-sha256",
        "timestamp": str(int(time.time() * 1000)),
        "nonce": os.urandom(8).hex(),
    }
    str_to_sign = urlencode(sorted(query.items()))
    sig = hmac.new(
        ACCESS_KEY_SECRET.encode(),
        str_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    query["signature"] = sig
    return f"{API_BASE}/?{urlencode(query)}"


def send_sms(to, template_data=None, template_id=None, signature=None, content=None):
    url = _build_signed_url("sms.message.send")

    body = {
        "to": to,
        "signature": signature or DEFAULT_SIGNATURE,
    }

    if content:
        body["content"] = content
    else:
        body["templateId"] = template_id or DEFAULT_TEMPLATE_ID
        if template_data:
            body["templateData"] = template_data

    resp = requests.post(url, json=body, headers={"Accept": "application/json"}, timeout=10)
    data = resp.json()

    if data.get("code") != "0":
        raise RuntimeError(f"UniSMS error {data.get('code')}: {data.get('message')}")

    return data.get("data", {})


def main():
    parser = argparse.ArgumentParser(description="Send SMS via UniSMS")
    parser.add_argument("--to", required=True, nargs="+", help="Phone number(s)")
    parser.add_argument("--content", help="Raw text content")
    parser.add_argument("--template-id", help="Template ID")
    parser.add_argument("--template-data", help="Template variables as JSON string")
    parser.add_argument("--signature", help="SMS signature")
    args = parser.parse_args()

    to = args.to[0] if len(args.to) == 1 else args.to
    tpl_data = json.loads(args.template_data) if args.template_data else None

    result = send_sms(
        to=to,
        content=args.content,
        template_id=args.template_id,
        template_data=tpl_data,
        signature=args.signature,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
