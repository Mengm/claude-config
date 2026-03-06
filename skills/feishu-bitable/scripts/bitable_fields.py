#!/usr/bin/env python3
"""Manage Feishu Bitable fields (columns)."""

import argparse
import json
import sys

from feishu_auth import api_get, api_post, api_put, api_delete


def list_fields(app_token: str, table_id: str) -> list:
    """List all fields in a table."""
    items = []
    page_token = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = api_get(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", params=params)
        if resp.get("code") != 0:
            print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
            sys.exit(1)
        data = resp.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return items


def create_field(app_token: str, table_id: str, name: str, field_type: int,
                 options: list | None = None,
                 property_obj: dict | None = None) -> dict:
    """Create a new field."""
    body = {"field_name": name, "type": field_type}
    if property_obj:
        body["property"] = property_obj
    elif options and field_type in (3, 4):  # single/multi select
        body["property"] = {
            "options": [{"name": opt} for opt in options]
        }
    resp = api_post(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", body=body)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("field", {})


def update_field(app_token: str, table_id: str, field_id: str,
                 name: str | None = None, field_type: int | None = None) -> dict:
    """Update a field."""
    body = {}
    if name:
        body["field_name"] = name
    if field_type is not None:
        body["type"] = field_type
    resp = api_put(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}", body=body)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("field", {})


def delete_field(app_token: str, table_id: str, field_id: str) -> dict:
    """Delete a field."""
    resp = api_delete(f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def _brief_fields(fields: list) -> list:
    """Compact field list: keep only field_id, field_name, type."""
    return [{"field_id": f.get("field_id"), "field_name": f.get("field_name"),
             "type": f.get("type")} for f in fields]


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu Bitable fields")
    parser.add_argument("--app", required=True, help="App token")
    parser.add_argument("--table", required=True, help="Table ID")
    parser.add_argument("--action", required=True, choices=["list", "create", "update", "delete"])
    parser.add_argument("--name", help="Field name")
    parser.add_argument("--type", type=int, help="Field type number")
    parser.add_argument("--field-id", help="Field ID (for update/delete)")
    parser.add_argument("--options", help="Options JSON array (for single/multi select)")
    parser.add_argument("--property", help="Property JSON object (for link/duplex fields etc.)")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output for list: only field_id/field_name/type")
    args = parser.parse_args()

    if args.action == "list":
        fields = list_fields(args.app, args.table)
        if args.brief:
            fields = _brief_fields(fields)
        print(json.dumps(fields, ensure_ascii=False, indent=2))

    elif args.action == "create":
        if not args.name or args.type is None:
            print("ERROR: --name and --type are required for create", file=sys.stderr)
            sys.exit(1)
        options = json.loads(args.options) if args.options else None
        property_obj = json.loads(args.property) if args.property else None
        result = create_field(args.app, args.table, args.name, args.type, options, property_obj)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "update":
        if not args.field_id:
            print("ERROR: --field-id is required for update", file=sys.stderr)
            sys.exit(1)
        result = update_field(args.app, args.table, args.field_id, args.name, args.type)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "delete":
        if not args.field_id:
            print("ERROR: --field-id is required for delete", file=sys.stderr)
            sys.exit(1)
        result = delete_field(args.app, args.table, args.field_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
