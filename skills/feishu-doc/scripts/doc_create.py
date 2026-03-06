#!/usr/bin/env python3
"""Create a new Feishu document with graceful fallback.

Priority: Wiki → Drive folder → bare create (no location).
Each step catches errors and falls through to the next.
"""

import argparse
import json
import os
import sys

from feishu_auth import api_patch, api_post
from doc_share import grant_owner


FEISHU_DOMAIN = os.getenv("FEISHU_DOMAIN", "feishu.cn")


def _try_wiki(title: str, space_id: str,
              parent_node_token: str | None = None) -> dict | None:
    """Try creating a document as a Wiki node. Returns None on failure.

    Tries tenant token first; falls back to user token on permission error.
    """
    body = {
        "obj_type": "docx",
        "node_type": "origin",
        "title": title,
    }
    if parent_node_token:
        body["parent_node_token"] = parent_node_token
    try:
        resp = api_post(f"/wiki/v2/spaces/{space_id}/nodes", body=body)
    except Exception as e:
        print(f"ERROR: wiki create failed (network) | error={e}", file=sys.stderr)
        return None
    if resp.get("code") in (131006, 131001):
        print(f"Tenant token denied (code={resp.get('code')}), retrying with user token...", file=sys.stderr)
        try:
            resp = api_post(f"/wiki/v2/spaces/{space_id}/nodes", body=body, as_user=True)
        except Exception as e:
            print(f"ERROR: wiki create failed (user token) | error={e}", file=sys.stderr)
            return None
    if resp.get("code") != 0:
        print(f"ERROR: wiki create failed | code={resp.get('code')}, msg={resp.get('msg')}", file=sys.stderr)
        return None
    node = resp.get("data", {}).get("node", {})
    obj_token = node.get("obj_token", "")
    # Auto-grant tenant_editable so bot can write content via tenant token
    # Uses tenant token (drive:drive scope unavailable for user token)
    if obj_token:
        api_patch(
            f"/drive/v1/permissions/{obj_token}/public",
            body={"link_share_entity": "tenant_editable"},
            params={"type": "docx"},
        )
    return {
        "document_id": obj_token,
        "node_token": node.get("node_token", ""),
        "title": node.get("title", title),
        "url": f"https://{FEISHU_DOMAIN}/wiki/{node.get('node_token', '')}",
        "space_id": space_id,
        "location": "wiki",
    }


def _try_folder(title: str, folder_token: str) -> dict | None:
    """Try creating a document in a Drive folder. Returns None on failure."""
    try:
        resp = api_post("/docx/v1/documents", body={"title": title, "folder_token": folder_token})
    except Exception as e:
        print(f"ERROR: folder create failed (network) | error={e}", file=sys.stderr)
        return None
    if resp.get("code") != 0:
        print(f"ERROR: folder create failed | code={resp.get('code')}, msg={resp.get('msg')}", file=sys.stderr)
        return None
    doc = resp.get("data", {}).get("document", {})
    document_id = doc.get("document_id", "")
    return {
        "document_id": document_id,
        "title": doc.get("title", title),
        "url": f"https://{FEISHU_DOMAIN}/docx/{document_id}",
        "location": "folder",
    }


def _bare_create(title: str) -> dict:
    """Create a document with no location (always succeeds or hard-fails)."""
    resp = api_post("/docx/v1/documents", body={"title": title})
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    doc = resp.get("data", {}).get("document", {})
    document_id = doc.get("document_id", "")
    return {
        "document_id": document_id,
        "title": doc.get("title", title),
        "url": f"https://{FEISHU_DOMAIN}/docx/{document_id}",
        "location": "bare",
    }


def create_document(title: str, folder_token: str | None = None,
                    wiki_space: str | None = None,
                    parent_node: str | None = None) -> dict:
    """Create a document with fallback: Wiki → folder → bare.

    --folder forces Drive folder mode (skips Wiki).
    """
    # If --folder is explicitly given, go straight to folder (no Wiki)
    if folder_token:
        result = _try_folder(title, folder_token)
        if result:
            return result
        return _bare_create(title)

    # Step 1: try Wiki
    space = wiki_space or os.getenv("FEISHU_WIKI_SPACE", "")
    if space:
        result = _try_wiki(title, space, parent_node)
        if result:
            return result
        print("Falling back to Drive folder...", file=sys.stderr)

    # Step 2: try folder
    folder = os.getenv("FEISHU_DOC_FOLDER", "")
    if folder:
        result = _try_folder(title, folder)
        if result:
            return result
        print("Falling back to bare create...", file=sys.stderr)

    # Step 3: bare create
    return _bare_create(title)


def main():
    parser = argparse.ArgumentParser(description="Create a new Feishu document")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--folder", default=None, help="Folder token (forces Drive folder mode)")
    parser.add_argument("--wiki-space", default=None, help="Wiki space ID (overrides FEISHU_WIKI_SPACE)")
    parser.add_argument("--parent-node", default=None, help="Parent node token in Wiki")
    args = parser.parse_args()

    result = create_document(args.title, args.folder, args.wiki_space, args.parent_node)

    # Auto-grant current user as owner (uses TASKPOOL_USER_ID)
    doc_id = result.get("document_id", "")
    if doc_id:
        grant_result = grant_owner(doc_id)
        result["granted_to"] = grant_result.get("member", {}).get("member_id", "")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
