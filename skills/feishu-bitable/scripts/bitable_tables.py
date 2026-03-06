#!/usr/bin/env python3
"""Manage Feishu Bitable tables."""

import argparse
import json
import sys

from feishu_auth import api_get, api_post, api_delete


def create_app(name: str, folder_token: str | None = None) -> dict:
    """Create a new bitable app."""
    body = {"name": name}
    if folder_token:
        body["folder_token"] = folder_token
    resp = api_post("/bitable/v1/apps", body=body)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("app", {})


def list_tables(app_token: str) -> list:
    """List all tables in a bitable app."""
    items = []
    page_token = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = api_get(f"/bitable/v1/apps/{app_token}/tables", params=params)
        if resp.get("code") != 0:
            print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
            sys.exit(1)
        data = resp.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return items


def create_table(app_token: str, name: str, fields: list | None = None) -> dict:
    """Create a new table."""
    table_def = {"name": name}
    if fields:
        table_def["fields"] = fields
    body = {"table": table_def}
    resp = api_post(f"/bitable/v1/apps/{app_token}/tables", body=body)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def delete_table(app_token: str, table_id: str) -> dict:
    """Delete a table."""
    resp = api_delete(f"/bitable/v1/apps/{app_token}/tables/{table_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu Bitable tables")
    parser.add_argument("--app", help="App token (not needed for create-app)")
    parser.add_argument("--action", required=True, choices=["create-app", "list", "create", "delete"])
    parser.add_argument("--name", help="Table name (for create)")
    parser.add_argument("--fields", help="Fields JSON array (for create)")
    parser.add_argument("--table", help="Table ID (for delete)")
    parser.add_argument("--folder", help="Folder token (for create-app)")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output for list: only table_id/name")
    args = parser.parse_args()

    if args.action == "create-app":
        if not args.name:
            print("ERROR: --name is required for create-app", file=sys.stderr)
            sys.exit(1)
        result = create_app(args.name, args.folder)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "list":
        if not args.app:
            print("ERROR: --app is required for list", file=sys.stderr)
            sys.exit(1)
        tables = list_tables(args.app)
        if args.brief:
            tables = [{"table_id": t.get("table_id"), "name": t.get("name")} for t in tables]
        print(json.dumps(tables, ensure_ascii=False, indent=2))

    elif args.action == "create":
        if not args.name:
            print("ERROR: --name is required for create", file=sys.stderr)
            sys.exit(1)
        fields = json.loads(args.fields) if args.fields else None
        result = create_table(args.app, args.name, fields)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "delete":
        if not args.table:
            print("ERROR: --table is required for delete", file=sys.stderr)
            sys.exit(1)
        result = delete_table(args.app, args.table)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
