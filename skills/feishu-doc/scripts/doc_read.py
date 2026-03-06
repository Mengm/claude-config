#!/usr/bin/env python3
"""Read Feishu document content."""

import argparse
import json
import sys

from feishu_auth import api_get


def get_raw_content(document_id: str) -> str:
    """Get plain text content of a document."""
    resp = api_get(f"/docx/v1/documents/{document_id}/raw_content")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("content", "")


def get_blocks(document_id: str) -> list:
    """Get all blocks of a document."""
    items = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        resp = api_get(f"/docx/v1/documents/{document_id}/blocks", params=params)
        if resp.get("code") != 0:
            print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
            sys.exit(1)
        data = resp.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return items


def get_document_meta(document_id: str) -> dict:
    """Get document metadata."""
    resp = api_get(f"/docx/v1/documents/{document_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("document", {})


def main():
    parser = argparse.ArgumentParser(description="Read Feishu document content")
    parser.add_argument("--id", required=True, help="Document ID")
    parser.add_argument("--blocks", action="store_true", help="Get structured block data (JSON)")
    parser.add_argument("--meta", action="store_true", help="Get document metadata")
    parser.add_argument("--brief", action="store_true",
                        help="Compact block output: only block_id/block_type/parent_id")
    parser.add_argument("--max-chars", type=int, default=0,
                        help="Truncate output to N chars (0 = no limit, applies to text and blocks)")
    parser.add_argument("--offset", type=int, default=0,
                        help="Start reading from this char offset (for paging large docs, text mode only)")
    args = parser.parse_args()

    if args.meta:
        meta = get_document_meta(args.id)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    elif args.blocks:
        blocks = get_blocks(args.id)
        block_count = len(blocks)
        if args.brief:
            blocks = [{"block_id": b.get("block_id"), "block_type": b.get("block_type"),
                        "parent_id": b.get("parent_id")} for b in blocks]
        output = json.dumps(blocks, ensure_ascii=False, indent=2)
        if args.max_chars and len(output) > args.max_chars:
            full_len = len(output)
            output = output[:args.max_chars] + "\n... (truncated)"
            print(f"HINT: blocks output truncated at {args.max_chars} of {full_len} chars ({block_count} blocks) — use --brief or increase --max-chars", file=sys.stderr)
        print(output)
    else:
        content = get_raw_content(args.id)
        total = len(content)
        chunk = content[args.offset:]
        if args.max_chars and len(chunk) > args.max_chars:
            end = args.offset + args.max_chars
            print(chunk[:args.max_chars])
            print(f"\n... (truncated, {total} chars total)")
            print(f"HINT: showing chars {args.offset}-{end} of {total} — rerun with --offset {end} to continue", file=sys.stderr)
        else:
            print(chunk)
            if args.offset > 0:
                print(f"HINT: showing chars {args.offset}-{total} of {total} (end of document)", file=sys.stderr)


if __name__ == "__main__":
    main()
