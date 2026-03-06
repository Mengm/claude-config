#!/usr/bin/env python3
"""Manage Feishu Bitable records."""

import argparse
import json
import sys

from feishu_auth import api_get, api_post, api_put, api_delete


def search_records(app_token: str, table_id: str, filter_obj: dict | None = None,
                   page_size: int = 20, page_token: str | None = None) -> dict:
    """Search records with optional filter."""
    body = {"automatic_fields": True}
    if filter_obj:
        body["filter"] = filter_obj
    params = {"page_size": page_size}
    if page_token:
        params["page_token"] = page_token
    resp = api_post(f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/search", body=body, params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def create_record(app_token: str, table_id: str, fields: dict) -> dict:
    """Create a single record."""
    resp = api_post(
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        body={"fields": fields},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("record", {})


def batch_create_records(app_token: str, table_id: str, records: list) -> dict:
    """Batch create records (max 500)."""
    resp = api_post(
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
        body={"records": records},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def update_record(app_token: str, table_id: str, record_id: str, fields: dict) -> dict:
    """Update a single record."""
    resp = api_put(
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        body={"fields": fields},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("record", {})


def batch_update_records(app_token: str, table_id: str, records: list) -> dict:
    """Batch update records."""
    resp = api_post(
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update",
        body={"records": records},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def delete_record(app_token: str, table_id: str, record_id: str) -> dict:
    """Delete a single record."""
    resp = api_delete(f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def batch_delete_records(app_token: str, table_id: str, record_ids: list) -> dict:
    """Batch delete records."""
    resp = api_post(
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
        body={"records": record_ids},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def _truncate(value, max_len: int = 100) -> str:
    """Truncate a field value to max_len chars for brief output."""
    s = str(value) if not isinstance(value, str) else value
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _brief_records(data: dict, select_fields: list[str] | None = None) -> dict:
    """Compact search results: keep record_id + truncated field values."""
    items = data.get("items", [])
    brief_items = []
    for item in items:
        rec = {"record_id": item.get("record_id")}
        fields = item.get("fields", {})
        if select_fields:
            rec["fields"] = {k: _truncate(fields[k]) for k in select_fields if k in fields}
        else:
            rec["fields"] = {k: _truncate(v) for k, v in fields.items()}
        brief_items.append(rec)
    out = {"total": data.get("total", len(brief_items)), "items": brief_items}
    if data.get("has_more"):
        out["has_more"] = True
        out["page_token"] = data.get("page_token")
    return out


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu Bitable records")
    parser.add_argument("--app", required=True, help="App token")
    parser.add_argument("--table", required=True, help="Table ID")
    parser.add_argument("--action", required=True,
                        choices=["search", "create", "batch_create", "update",
                                 "batch_update", "delete", "batch_delete"])
    parser.add_argument("--fields", help="Record fields JSON (for create/update)")
    parser.add_argument("--records", help="Records JSON array (for batch ops)")
    parser.add_argument("--record-id", help="Record ID (for update/delete)")
    parser.add_argument("--record-ids", help="Record IDs JSON array (for batch_delete)")
    parser.add_argument("--filter", help="Filter JSON (for search)")
    parser.add_argument("--page-size", type=int, default=20, help="Page size (default 20, max 500)")
    parser.add_argument("--page-token", help="Page token for pagination")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output: record_id + truncated fields (search only)")
    parser.add_argument("--select-fields", help="Comma-separated field names to include (search only)")
    args = parser.parse_args()

    if args.action == "search":
        filter_obj = json.loads(args.filter) if args.filter else None
        result = search_records(args.app, args.table, filter_obj,
                                args.page_size, args.page_token)
        if args.brief:
            select = [f.strip() for f in args.select_fields.split(",")] if args.select_fields else None
            result = _brief_records(result, select)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "create":
        if not args.fields:
            print("ERROR: --fields is required for create", file=sys.stderr)
            sys.exit(1)
        result = create_record(args.app, args.table, json.loads(args.fields))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "batch_create":
        if not args.records:
            print("ERROR: --records is required for batch_create", file=sys.stderr)
            sys.exit(1)
        result = batch_create_records(args.app, args.table, json.loads(args.records))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "update":
        if not args.record_id or not args.fields:
            print("ERROR: --record-id and --fields are required for update", file=sys.stderr)
            sys.exit(1)
        result = update_record(args.app, args.table, args.record_id, json.loads(args.fields))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "batch_update":
        if not args.records:
            print("ERROR: --records is required for batch_update", file=sys.stderr)
            sys.exit(1)
        result = batch_update_records(args.app, args.table, json.loads(args.records))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "delete":
        if not args.record_id:
            print("ERROR: --record-id is required for delete", file=sys.stderr)
            sys.exit(1)
        result = delete_record(args.app, args.table, args.record_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "batch_delete":
        if not args.record_ids:
            print("ERROR: --record-ids is required for batch_delete", file=sys.stderr)
            sys.exit(1)
        result = batch_delete_records(args.app, args.table, json.loads(args.record_ids))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
