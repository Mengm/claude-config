#!/usr/bin/env python3
"""Manage Feishu Drive folders (create, list, move files)."""

import argparse
import json
import sys

from feishu_auth import api_get, api_post


def create_folder(name: str, parent_token: str = "") -> dict:
    """Create a folder. parent_token='' means root folder."""
    body = {"name": name, "folder_token": parent_token}
    resp = api_post("/drive/v1/files/create_folder", body=body, as_user=False)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def list_folder(folder_token: str | None = None, page_size: int = 100,
                page_token: str | None = None, order_by: str = "EditedTime",
                direction: str = "DESC") -> dict:
    """List files/docs in a folder."""
    params = {
        "page_size": page_size,
        "order_by": order_by,
        "direction": direction,
    }
    if folder_token:
        params["folder_token"] = folder_token
    if page_token:
        params["page_token"] = page_token
    resp = api_get("/drive/v1/files", params=params, as_user=False)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def move_file(file_token: str, target_folder: str, file_type: str = "docx") -> dict:
    """Move a file/doc into a folder."""
    body = {"type": file_type, "folder_token": target_folder}
    resp = api_post(f"/drive/v1/files/{file_token}/move", body=body, as_user=False)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def _brief_files(data: dict) -> dict:
    """Compact list output: keep only name, token, type."""
    files = data.get("files", [])
    brief = [{"name": f.get("name"), "token": f.get("token"), "type": f.get("type")} for f in files]
    out = {"files": brief}
    if data.get("has_more"):
        out["has_more"] = True
        out["next_page_token"] = data.get("next_page_token")
    return out


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu Drive folders")
    parser.add_argument("--action", required=True,
                        choices=["create", "list", "move"])
    parser.add_argument("--name", help="Folder name (for create)")
    parser.add_argument("--parent", default="", help="Parent folder token (for create, empty=root)")
    parser.add_argument("--folder-token", help="Folder token to list")
    parser.add_argument("--file-token", help="File token to move")
    parser.add_argument("--target-folder", help="Target folder token (for move)")
    parser.add_argument("--file-type", default="docx",
                        help="File type for move: file/docx/bitable/sheet (default: docx)")
    parser.add_argument("--order-by", default="EditedTime",
                        help="Sort by: EditedTime or CreatedTime")
    parser.add_argument("--direction", default="DESC", help="ASC or DESC")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--page-token", help="Pagination token")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output for list: only name/token/type")
    args = parser.parse_args()

    if args.action == "create":
        if not args.name:
            print("ERROR: --name is required for create", file=sys.stderr)
            sys.exit(1)
        result = create_folder(args.name, args.parent)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "list":
        result = list_folder(args.folder_token, args.page_size, args.page_token,
                             args.order_by, args.direction)
        if args.brief:
            result = _brief_files(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "move":
        if not args.file_token or not args.target_folder:
            print("ERROR: --file-token and --target-folder are required for move",
                  file=sys.stderr)
            sys.exit(1)
        result = move_file(args.file_token, args.target_folder, args.file_type)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
