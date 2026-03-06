#!/usr/bin/env python3
"""Send email via Resend API."""

import argparse
import json
import os

import resend
from dotenv import load_dotenv

ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env"))
load_dotenv(ENV_PATH)

resend.api_key = os.getenv("RESEND_API_KEY", "")
DEFAULT_FROM = os.getenv("RESEND_FROM", "DutyAI <onboarding@resend.dev>")


def send_email(to, subject, body=None, html=None, attachments=None,
               cc=None, bcc=None, reply_to=None, from_addr=None):
    if isinstance(to, str):
        to = [to]

    params = {
        "from": from_addr or DEFAULT_FROM,
        "to": to,
        "subject": subject,
    }

    if html:
        params["html"] = html
    elif body:
        params["text"] = body
    else:
        params["text"] = ""

    if cc:
        params["cc"] = [cc] if isinstance(cc, str) else cc
    if bcc:
        params["bcc"] = [bcc] if isinstance(bcc, str) else bcc
    if reply_to:
        params["reply_to"] = reply_to

    if attachments:
        att_list = []
        for path in attachments:
            with open(path, "rb") as f:
                att_list.append({
                    "content": list(f.read()),
                    "filename": os.path.basename(path),
                })
        params["attachments"] = att_list

    return resend.Emails.send(params)


def main():
    parser = argparse.ArgumentParser(description="Send email via Resend")
    parser.add_argument("--to", required=True, nargs="+", help="Recipient(s)")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", help="Plain text body")
    parser.add_argument("--html", help="HTML body")
    parser.add_argument("--attachments", nargs="+", help="File paths")
    parser.add_argument("--cc", nargs="+")
    parser.add_argument("--bcc", nargs="+")
    parser.add_argument("--reply-to")
    parser.add_argument("--from", dest="from_addr")
    args = parser.parse_args()

    result = send_email(
        to=args.to,
        subject=args.subject,
        body=args.body,
        html=args.html,
        attachments=args.attachments,
        cc=args.cc,
        bcc=args.bcc,
        reply_to=args.reply_to,
        from_addr=args.from_addr,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
