#!/usr/bin/env python3
"""Manage Feishu document/bitable sharing permissions."""

import argparse
import json
import os
import sys

from feishu_auth import api_patch, api_post

LINK_SHARE_TYPES = {
    "anyone_read": "anyone_readable",
    "anyone_edit": "anyone_editable",
    "tenant_read": "tenant_readable",
    "tenant_edit": "tenant_editable",
    "off": "closed",
}

# Feishu drive type mapping
DOC_TYPES = {
    "docx": "docx",
    "bitable": "bitable",
    "sheet": "sheet",
    "file": "file",
    "wiki": "wiki",
}


def set_link_share(token: str, share_type: str, doc_type: str = "docx") -> dict:
    """Set document link sharing permissions via Drive API.

    Permission layers (from private to public):
    - off:          Only collaborators (default after creation)
    - tenant_read:  Anyone in the organization with link can read
    - tenant_edit:  Anyone in the organization with link can edit
    - anyone_read:  Anyone on the internet with link can read
    - anyone_edit:  Anyone on the internet with link can edit
    """
    perm_type = LINK_SHARE_TYPES.get(share_type)
    if not perm_type:
        print(f"ERROR: unknown share type '{share_type}'. Options: {list(LINK_SHARE_TYPES.keys())}", file=sys.stderr)
        sys.exit(1)

    need_external = share_type.startswith("anyone_")
    body = {"link_share_entity": perm_type}
    if need_external:
        body["external_access"] = True

    resp = api_patch(
        f"/drive/v1/permissions/{token}/public",
        body=body,
        params={"type": doc_type},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def add_collaborator(token: str, open_id: str, perm: str = "full_access",
                     doc_type: str = "docx") -> dict:
    """Add a user as collaborator to a document/bitable.

    perm options: view, edit, full_access
    """
    resp = api_post(
        f"/drive/v1/permissions/{token}/members",
        body={
            "member_type": "openid",
            "member_id": open_id,
            "perm": perm,
        },
        params={"type": doc_type, "need_notification": "false"},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def grant_owner(token: str, doc_type: str = "docx") -> dict:
    """Grant full_access to the current user (from TASKPOOL_USER_ID env)."""
    open_id = os.environ.get("TASKPOOL_USER_ID", "")
    if not open_id:
        print("Warning: TASKPOOL_USER_ID not set, skipping grant_owner | env=TASKPOOL_USER_ID", file=sys.stderr)
        return {}
    return add_collaborator(token, open_id, "full_access", doc_type)


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu document sharing")
    parser.add_argument("--id", required=True, help="Document/Bitable token")
    all_types = list(LINK_SHARE_TYPES.keys()) + ["owner"]
    parser.add_argument("--type", required=True,
                        choices=all_types,
                        help="Share permission type ('owner' = grant current user full_access)")
    parser.add_argument("--doc-type", default="docx",
                        choices=list(DOC_TYPES.keys()),
                        help="Document type (default: docx)")
    args = parser.parse_args()

    if args.type == "owner":
        result = grant_owner(args.id, args.doc_type)
    else:
        result = set_link_share(args.id, args.type, args.doc_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
