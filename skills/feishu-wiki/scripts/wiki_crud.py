#!/usr/bin/env python3
"""Manage Feishu Wiki / Knowledge Base (Wiki V2 API)."""

import argparse
import json
import os
import sys

from feishu_auth import api_get, api_patch, api_post

FEISHU_DOMAIN = os.getenv("FEISHU_DOMAIN", "feishu.cn")


def list_spaces(page_size: int = 20, page_token: str | None = None) -> dict:
    """List all accessible wiki spaces."""
    params = {"page_size": page_size}
    if page_token:
        params["page_token"] = page_token
    resp = api_get("/wiki/v2/spaces", params=params, as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def get_space(space_id: str) -> dict:
    """Get wiki space details."""
    resp = api_get(f"/wiki/v2/spaces/{space_id}", as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def list_nodes(space_id: str, parent_node_token: str | None = None,
               page_size: int = 50, page_token: str | None = None) -> dict:
    """List child nodes in a wiki space. Use space_id='my_library' for personal docs."""
    params = {"page_size": page_size}
    if parent_node_token:
        params["parent_node_token"] = parent_node_token
    if page_token:
        params["page_token"] = page_token
    resp = api_get(f"/wiki/v2/spaces/{space_id}/nodes", params=params, as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def get_node(token: str, obj_type: str | None = None) -> dict:
    """Get wiki node info by token."""
    params = {"token": token}
    if obj_type:
        params["obj_type"] = obj_type
    resp = api_get("/wiki/v2/spaces/get_node", params=params, as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def create_space(name: str, description: str = "") -> dict:
    """Create a new wiki space (requires user_access_token)."""
    body = {"name": name}
    if description:
        body["description"] = description
    resp = api_post("/wiki/v2/spaces", body=body, as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def create_node(space_id: str, title: str, obj_type: str = "docx",
                parent_node_token: str | None = None) -> dict:
    """Create a new wiki node (page).

    Tries tenant token first; falls back to user token on permission error.
    """
    body = {
        "obj_type": obj_type,
        "node_type": "origin",
        "title": title,
    }
    if parent_node_token:
        body["parent_node_token"] = parent_node_token
    resp = api_post(f"/wiki/v2/spaces/{space_id}/nodes", body=body)
    if resp.get("code") not in (0, 131006, 131001):
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    # Fallback to user token on permission errors
    if resp.get("code") in (131006, 131001):
        print(f"Tenant token denied (code={resp.get('code')}), retrying with user token...", file=sys.stderr)
        resp = api_post(f"/wiki/v2/spaces/{space_id}/nodes", body=body, as_user=True)
        if resp.get("code") != 0:
            print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
            sys.exit(1)
    data = resp.get("data", {})
    node = data.get("node", {})
    node_token = node.get("node_token", "")
    obj_token = node.get("obj_token", "")
    if node_token:
        node["url"] = f"https://{FEISHU_DOMAIN}/wiki/{node_token}"
    # Auto-grant tenant_editable so bot can write content via tenant token
    if obj_token:
        grant_resp = api_patch(
            f"/drive/v1/permissions/{obj_token}/public",
            body={"link_share_entity": "tenant_editable"},
            params={"type": "docx"},
            as_user=True,
        )
        if grant_resp.get("code") == 0:
            print("Auto-granted tenant_editable on wiki doc for bot write access", file=sys.stderr)
        else:
            print(f"Warning: failed to grant tenant_editable | code={grant_resp.get('code')}, msg={grant_resp.get('msg', '')[:80]}", file=sys.stderr)
    return data


def move_node(space_id: str, node_token: str,
              target_parent_token: str | None = None,
              target_space_id: str | None = None) -> dict:
    """Move a wiki node to a new parent within the same or different space."""
    body: dict = {}
    if target_parent_token:
        body["target_parent_token"] = target_parent_token
    if target_space_id:
        body["target_space_id"] = target_space_id
    resp = api_post(f"/wiki/v2/spaces/{space_id}/nodes/{node_token}/move",
                    body=body, as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def move_to_wiki(space_id: str, obj_token: str, obj_type: str = "docx",
                 parent_node_token: str | None = None) -> dict:
    """Move an existing document into a wiki space (requires user_access_token)."""
    body = {"obj_type": obj_type, "obj_token": obj_token}
    if parent_node_token:
        body["parent_node_token"] = parent_node_token
    resp = api_post(f"/wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki",
                    body=body, as_user=True)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def _brief_spaces(data: dict) -> dict:
    """Compact list-spaces: keep only space_id and name."""
    items = data.get("items", [])
    brief = [{"space_id": s.get("space_id"), "name": s.get("name")} for s in items]
    out = {"items": brief}
    if data.get("has_more"):
        out["has_more"] = True
        out["page_token"] = data.get("page_token")
    return out


def _brief_nodes(data: dict) -> dict:
    """Compact list-nodes: keep only node_token, title, obj_type, url."""
    items = data.get("items", [])
    brief = [{"node_token": n.get("node_token"), "title": n.get("title"),
              "obj_type": n.get("obj_type"),
              "url": f"https://{FEISHU_DOMAIN}/wiki/{n.get('node_token', '')}"}
             for n in items]
    out = {"items": brief}
    if data.get("has_more"):
        out["has_more"] = True
        out["page_token"] = data.get("page_token")
    return out


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu Wiki / Knowledge Base")
    parser.add_argument("--action", required=True,
                        choices=["list-spaces", "get-space", "list-nodes",
                                 "get-node", "create-node", "create-space",
                                 "move-to-wiki", "move-node"])
    parser.add_argument("--space-id", help="Wiki space ID (use 'my_library' for personal docs)")
    parser.add_argument("--parent-node-token", help="Parent node token")
    parser.add_argument("--target-parent-token", help="Target parent node token for move-node")
    parser.add_argument("--target-space-id", help="Target space ID for move-node (cross-space)")
    parser.add_argument("--token", help="Node token or doc token")
    parser.add_argument("--obj-type", help="Doc type: doc/docx/sheet/mindnote/bitable")
    parser.add_argument("--title", help="Node title or space name for create")
    parser.add_argument("--description", help="Space description for create-space")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--page-token", help="Pagination token")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output for list-spaces/list-nodes/get-space")
    args = parser.parse_args()

    if args.action == "list-spaces":
        result = list_spaces(args.page_size, args.page_token)
        if args.brief:
            result = _brief_spaces(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "get-space":
        if not args.space_id:
            print("ERROR: --space-id is required", file=sys.stderr)
            sys.exit(1)
        result = get_space(args.space_id)
        if args.brief:
            space = result.get("space", result)
            result = {"space_id": space.get("space_id"), "name": space.get("name"),
                       "description": space.get("description", "")}
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "list-nodes":
        if not args.space_id:
            print("ERROR: --space-id is required", file=sys.stderr)
            sys.exit(1)
        result = list_nodes(args.space_id, args.parent_node_token,
                            args.page_size, args.page_token)
        if args.brief:
            result = _brief_nodes(result)
        else:
            for item in result.get("items", []):
                nt = item.get("node_token", "")
                if nt and "url" not in item:
                    item["url"] = f"https://{FEISHU_DOMAIN}/wiki/{nt}"
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "get-node":
        if not args.token:
            print("ERROR: --token is required", file=sys.stderr)
            sys.exit(1)
        result = get_node(args.token, args.obj_type)
        node = result.get("node", {})
        nt = node.get("node_token", "")
        if nt and "url" not in node:
            node["url"] = f"https://{FEISHU_DOMAIN}/wiki/{nt}"
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "create-node":
        if not args.space_id or not args.title:
            print("ERROR: --space-id and --title are required", file=sys.stderr)
            sys.exit(1)
        result = create_node(args.space_id, args.title,
                             args.obj_type or "docx", args.parent_node_token)
        # URL is already injected by create_node()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "create-space":
        if not args.title:
            print("ERROR: --title is required (space name)", file=sys.stderr)
            sys.exit(1)
        result = create_space(args.title, args.description or "")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "move-to-wiki":
        if not args.space_id or not args.token:
            print("ERROR: --space-id and --token (obj_token) are required", file=sys.stderr)
            sys.exit(1)
        result = move_to_wiki(args.space_id, args.token,
                              args.obj_type or "docx", args.parent_node_token)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "move-node":
        if not args.space_id or not args.token:
            print("ERROR: --space-id and --token (node_token) are required", file=sys.stderr)
            sys.exit(1)
        result = move_node(args.space_id, args.token,
                           args.target_parent_token, args.target_space_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
