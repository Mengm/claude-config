#!/usr/bin/env python3
"""Delete a Feishu document or file from Drive."""

import argparse
import json
import sys

import requests
from feishu_auth import get_token, headers


def delete_file(file_token: str, file_type: str = "docx") -> dict:
    """Delete a file from Feishu Drive.

    Args:
        file_token: Document/file token (document_id for docx).
        file_type: file/docx/bitable/sheet/mindnote/slides
    """
    url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}"
    resp = requests.delete(url, headers=headers(), params={"type": file_type}, timeout=30)
    try:
        data = resp.json()
    except Exception:
        data = {"code": resp.status_code, "msg": resp.text[:200]}
    if data.get("code") != 0:
        print(f"ERROR: {data.get('msg', 'unknown error')} (code={data.get('code')})", file=sys.stderr)
        sys.exit(1)
    return data


def main():
    parser = argparse.ArgumentParser(description="Delete a Feishu document/file")
    parser.add_argument("--id", required=True, help="File token (document_id for docx)")
    parser.add_argument("--type", default="docx",
                        choices=["file", "docx", "bitable", "sheet", "mindnote", "slides"],
                        help="File type (default: docx)")
    args = parser.parse_args()

    result = delete_file(args.id, args.type)
    print(json.dumps({"status": "deleted", "file_token": args.id, "type": args.type}))


if __name__ == "__main__":
    main()
