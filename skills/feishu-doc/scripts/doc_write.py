#!/usr/bin/env python3
"""Append or replace content blocks in a Feishu document.

Accepts two input formats via stdin:

1. JSON array (default):
  [{"type": "heading2", "text": "Title"}, {"type": "text", "text": "body"}]

2. Markdown (--markdown flag):
  ## Title
  body text
  - bullet a
  - bullet b

Use --replace to clear all existing content before writing.
"""

import argparse
import json
import os
import re
import sys
import time

import requests

from feishu_auth import api_delete, api_get, api_patch, api_post, get_token

BLOCK_TYPES = {
    "text": 2,
    "heading1": 3,
    "heading2": 4,
    "heading3": 5,
    "heading4": 6,
    "heading5": 7,
    "heading6": 8,
    "heading7": 9,
    "heading8": 10,
    "heading9": 11,
    "bullet": 12,
    "ordered": 13,
    "code": 14,
    "todo": 17,
    "divider": 22,
    "image": 27,
    "table": 31,
    "table_cell": 32,
    "quote_container": 34,
}

BASE = "https://open.feishu.cn/open-apis"

LANG_MAP = {
    "python": 14, "go": 8, "java": 11, "javascript": 12, "typescript": 27,
    "bash": 3, "shell": 22, "sql": 23, "json": 13, "yaml": 31,
    "markdown": 37, "rust": 20, "c": 4, "cpp": 5, "csharp": 6,
    "html": 9, "css": 7, "plaintext": 1,
}

MAX_BLOCKS_PER_REQUEST = 50

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')
_BULLET_RE = re.compile(r'^[-*]\s+(.+)$')
_ORDERED_RE = re.compile(r'^\d+[.)]\s+(.+)$')
_CODE_FENCE_RE = re.compile(r'^```(\w*)$')
_DIVIDER_RE = re.compile(r'^(-{3,}|\*{3,})$')
_IMAGE_RE = re.compile(r'^!\[.*?\]\((.+?)\)$')


def parse_markdown(text: str) -> list[dict]:
    """Convert markdown text to block spec list."""
    blocks: list[dict] = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Empty line — skip
        if not stripped:
            i += 1
            continue

        # Divider: --- or ***
        if _DIVIDER_RE.match(stripped):
            blocks.append({"type": "divider"})
            i += 1
            continue

        # Heading: # to ######
        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            blocks.append({"type": f"heading{level}", "text": m.group(2)})
            i += 1
            continue

        # Code fence: ```lang
        m = _CODE_FENCE_RE.match(stripped)
        if m:
            lang = m.group(1) or None
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            spec = {"type": "code", "text": '\n'.join(code_lines)}
            if lang:
                spec["lang"] = lang
            blocks.append(spec)
            continue

        # Image: ![alt](path)
        m = _IMAGE_RE.match(stripped)
        if m:
            blocks.append({"type": "image", "path": m.group(1)})
            i += 1
            continue

        # Bullet list: - item or * item (collect consecutive)
        m = _BULLET_RE.match(stripped)
        if m:
            items = []
            while i < len(lines) and _BULLET_RE.match(lines[i].strip()):
                items.append(_BULLET_RE.match(lines[i].strip()).group(1))
                i += 1
            blocks.append({"type": "bullet", "texts": items})
            continue

        # Ordered list: 1. item (collect consecutive)
        m = _ORDERED_RE.match(stripped)
        if m:
            items = []
            while i < len(lines) and _ORDERED_RE.match(lines[i].strip()):
                items.append(_ORDERED_RE.match(lines[i].strip()).group(1))
                i += 1
            blocks.append({"type": "ordered", "texts": items})
            continue

        # Regular paragraph
        blocks.append({"type": "text", "text": stripped})
        i += 1

    return blocks


def upload_image(file_path: str, block_id: str) -> str | None:
    """Upload a local image to Feishu Drive and return file_token.

    Args:
        file_path: Local path to the image file.
        block_id: The image block ID (from Step 1) to use as parent_node.
    """
    if not os.path.isfile(file_path):
        print(f"Warning: image file not found | path={file_path}", file=sys.stderr)
        return None
    token = get_token()
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{BASE}/drive/v1/medias/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_name": file_name,
                "parent_type": "docx_image",
                "parent_node": block_id,
                "size": str(file_size),
            },
            files={"file": (file_name, f, "image/png")},
            timeout=60,
        )
    data = resp.json()
    if data.get("code") != 0:
        print(f"Warning: image upload failed | path={file_path}, code={data.get('code')}, msg={data.get('msg', '')[:80]}", file=sys.stderr)
        return None
    ft = data.get("data", {}).get("file_token")
    print(f"Uploaded image | path={file_path} -> file_token={ft}", file=sys.stderr)
    return ft


def insert_image(document_id: str, file_path: str) -> bool:
    """Insert an image into a document using the official 3-step flow.

    Step 1: Create empty image block → get block_id
    Step 2: Upload image with parent_node=block_id → get file_token
    Step 3: PATCH replace_image to bind file_token + dimensions to block

    Returns True on success, False on failure.
    """
    # Read image dimensions for Step 3
    width, height = 0, 0
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.width, img.height
    except Exception:
        pass

    # Step 1: Create empty image block
    resp = api_post(
        f"/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        body={"children": [{"block_type": 27, "image": {}}]},
    )
    if resp.get("code") != 0:
        print(f"Warning: create image block failed | code={resp.get('code')}, msg={resp.get('msg')}", file=sys.stderr)
        return False
    children = resp.get("data", {}).get("children", [])
    if not children:
        print("Warning: no block_id returned from image block creation", file=sys.stderr)
        return False
    block_id = children[0].get("block_id")

    # Step 2: Upload image with parent_node=block_id
    file_token = upload_image(file_path, block_id)
    if not file_token:
        return False

    # Step 3: PATCH replace_image to bind the uploaded image with dimensions
    replace_body = {"token": file_token}
    if width and height:
        replace_body["width"] = width
        replace_body["height"] = height
    resp = api_patch(
        f"/docx/v1/documents/{document_id}/blocks/{block_id}",
        body={"replace_image": replace_body},
    )
    if resp.get("code") != 0:
        print(f"Warning: replace_image failed | code={resp.get('code')}, msg={resp.get('msg')}", file=sys.stderr)
        return False
    print(f"Image inserted | path={file_path}, block_id={block_id}, file_token={file_token}", file=sys.stderr)
    return True


def make_text_element(text: str) -> dict:
    return {"text_run": {"content": text}}


def make_block(block_type: int, texts: list[str], lang: str | None = None) -> dict:
    block = {"block_type": block_type}
    if block_type == 22:
        block["divider"] = {}
    elif block_type == 14:
        block["code"] = {
            "elements": [make_text_element(t) for t in texts],
            "language": LANG_MAP.get(lang or "plaintext", 1),
        }
    elif 3 <= block_type <= 11:
        block[f"heading{block_type - 2}"] = {
            "elements": [make_text_element(t) for t in texts],
        }
    elif block_type == 12:
        block["bullet"] = {"elements": [make_text_element(t) for t in texts]}
    elif block_type == 13:
        block["ordered"] = {"elements": [make_text_element(t) for t in texts]}
    else:
        block["text"] = {"elements": [make_text_element(t) for t in texts]}
    return block


def make_block_from_elements(
    block_type: int,
    elements: list[dict],
    lang: str | None = None,
    done: bool = False,
) -> dict:
    """Build a Feishu block dict from pre-formatted text_run elements."""
    block: dict = {"block_type": block_type}
    if block_type == 22:
        block["divider"] = {}
    elif block_type == 14:
        block["code"] = {
            "elements": elements,
            "language": LANG_MAP.get(lang or "plaintext", 1),
        }
    elif 3 <= block_type <= 11:
        block[f"heading{block_type - 2}"] = {"elements": elements}
    elif block_type == 12:
        block["bullet"] = {"elements": elements}
    elif block_type == 13:
        block["ordered"] = {"elements": elements}
    elif block_type == 17:
        block["todo"] = {"elements": elements, "style": {"done": done}}
    else:
        block["text"] = {"elements": elements}
    return block


def insert_table(document_id: str, spec: dict) -> bool:
    """Insert a GFM table as a Feishu table block (multi-step API).

    Steps:
    1. Create table shell with row_size/column_size → get cell block_ids
    2. Fill each cell with text block containing styled elements
    """
    header = spec.get("header", [])
    rows = spec.get("rows", [])
    n_cols = spec.get("n_cols", len(header))
    n_rows = spec.get("n_rows", len(rows) + 1)

    if n_cols == 0:
        return False

    # Step 1: Create table shell
    table_block = {
        "block_type": 31,
        "table": {
            "property": {
                "row_size": n_rows,
                "column_size": n_cols,
                "column_width": [200] * n_cols,
            },
        },
    }
    resp = api_post(
        f"/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        body={"children": [table_block]},
    )
    if resp.get("code") != 0:
        print(
            f"Warning: create table failed | code={resp.get('code')}, msg={resp.get('msg')}",
            file=sys.stderr,
        )
        return False

    children = resp.get("data", {}).get("children", [])
    if not children:
        print("Warning: no table block returned", file=sys.stderr)
        return False

    table_block_id = children[0].get("block_id")

    # Step 2: Get cell block IDs
    resp = api_get(
        f"/docx/v1/documents/{document_id}/blocks/{table_block_id}"
    )
    if resp.get("code") != 0:
        print(
            f"Warning: get table block failed | code={resp.get('code')}",
            file=sys.stderr,
        )
        return False

    cell_ids = resp.get("data", {}).get("block", {}).get("children", [])
    if len(cell_ids) < n_rows * n_cols:
        print(
            f"Warning: expected {n_rows * n_cols} cells, got {len(cell_ids)}",
            file=sys.stderr,
        )

    # Step 3: Fill cells — header row with bold
    all_rows = [header] + rows
    cells_filled = 0
    for row_idx, row_cells in enumerate(all_rows):
        for col_idx, cell_elements in enumerate(row_cells):
            cell_index = row_idx * n_cols + col_idx
            if cell_index >= len(cell_ids):
                break
            cell_id = cell_ids[cell_index]

            # For header row, force bold on all elements
            if row_idx == 0:
                for elem in cell_elements:
                    tr = elem.get("text_run")
                    if tr:
                        style = tr.setdefault("text_element_style", {})
                        style["bold"] = True

            text_block = {
                "block_type": 2,
                "text": {"elements": cell_elements or [make_text_element("")]},
            }
            resp = api_post(
                f"/docx/v1/documents/{document_id}/blocks/{cell_id}/children",
                body={"children": [text_block]},
            )
            if resp.get("code") != 0:
                print(
                    f"Warning: fill cell [{row_idx},{col_idx}] failed | code={resp.get('code')}",
                    file=sys.stderr,
                )
            else:
                cells_filled += 1
            time.sleep(0.1)

    print(
        f"Table inserted | {n_rows}x{n_cols}, cells_filled={cells_filled}",
        file=sys.stderr,
    )
    return True


def insert_blockquote(document_id: str, spec: dict) -> bool:
    """Insert a blockquote as a Feishu quote_container block.

    Steps:
    1. Create quote_container → get block_id
    2. Add child blocks inside the container
    """
    children_specs = spec.get("children", [])
    if not children_specs:
        return False

    # Step 1: Create quote_container
    resp = api_post(
        f"/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        body={"children": [{"block_type": 34, "quote_container": {}}]},
    )
    if resp.get("code") != 0:
        print(
            f"Warning: create quote_container failed | code={resp.get('code')}, msg={resp.get('msg')}",
            file=sys.stderr,
        )
        return False

    children = resp.get("data", {}).get("children", [])
    if not children:
        return False
    quote_block_id = children[0].get("block_id")

    # Step 2: Add child blocks inside the quote_container
    child_blocks = []
    for child_spec in children_specs:
        type_name = child_spec.get("type", "text")
        if type_name == "divider":
            child_blocks.append(make_block(22, []))
        elif "elements" in child_spec:
            bt = BLOCK_TYPES.get(type_name, 2)
            child_blocks.append(
                make_block_from_elements(bt, child_spec["elements"])
            )
        elif type_name == "code":
            child_blocks.append(
                make_block(14, [child_spec.get("text", "")], lang=child_spec.get("lang"))
            )
        else:
            child_blocks.append(make_block(2, [child_spec.get("text", "")]))

    if child_blocks:
        resp = api_post(
            f"/docx/v1/documents/{document_id}/blocks/{quote_block_id}/children",
            body={"children": child_blocks},
        )
        if resp.get("code") != 0:
            print(
                f"Warning: fill quote_container failed | code={resp.get('code')}",
                file=sys.stderr,
            )
            return False

    print(
        f"Blockquote inserted | children={len(child_blocks)}",
        file=sys.stderr,
    )
    return True


def clear_document(document_id: str) -> int:
    """Delete all child blocks from the document root. Returns count deleted."""
    resp = api_get(f"/docx/v1/documents/{document_id}/blocks/{document_id}")
    if resp.get("code") != 0:
        print(f"ERROR: read doc failed | code={resp.get('code')}, msg={resp.get('msg')}", file=sys.stderr)
        sys.exit(1)
    children = resp.get("data", {}).get("block", {}).get("children", [])
    count = len(children)
    if count == 0:
        return 0
    resp = api_delete(
        f"/docx/v1/documents/{document_id}/blocks/{document_id}/children/batch_delete",
        body={"start_index": 0, "end_index": count},
    )
    if resp.get("code") != 0:
        print(f"ERROR: clear doc failed | code={resp.get('code')}, msg={resp.get('msg')}", file=sys.stderr)
        sys.exit(1)
    return count


def append_blocks(document_id: str, blocks: list[dict]) -> dict:
    resp = api_post(
        f"/docx/v1/documents/{document_id}/blocks/{document_id}/children",
        body={"children": blocks},
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def append_blocks_chunked(document_id: str, blocks: list[dict]) -> dict:
    total = 0
    for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
        chunk = blocks[i:i + MAX_BLOCKS_PER_REQUEST]
        result = append_blocks(document_id, chunk)
        total += len(result.get("children", []))
        if i + MAX_BLOCKS_PER_REQUEST < len(blocks):
            time.sleep(0.35)
    return {"ok": True, "blocks_created": total}


def main():
    parser = argparse.ArgumentParser(description="Append or replace content blocks in a Feishu document (JSON or markdown from stdin)")
    parser.add_argument("--id", required=True, help="Document ID")
    parser.add_argument("--replace", action="store_true", help="Clear all existing content before writing")
    parser.add_argument("--markdown", action="store_true", help="Parse stdin as markdown instead of JSON")
    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"ok": True, "blocks_created": 0}))
        return

    if args.markdown:
        try:
            from gfm_to_feishu import convert_markdown
        except ImportError:
            print("Warning: gfm_to_feishu not available, using legacy parser", file=sys.stderr)
            spec_list = parse_markdown(raw)
        else:
            try:
                spec_list = convert_markdown(raw)
            except Exception as e:
                print(f"Warning: GFM parser failed, falling back to legacy | {e}", file=sys.stderr)
                spec_list = parse_markdown(raw)
    else:
        try:
            spec_list = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON on stdin: {e}", file=sys.stderr)
            sys.exit(1)

    if not spec_list:
        print(json.dumps({"ok": True, "blocks_created": 0}))
        return

    deleted = 0
    if args.replace:
        deleted = clear_document(args.id)

    # Process specs in order, flushing text blocks before each image/container
    # so they appear at the correct position in the document.
    total = 0
    images_ok = 0
    containers_ok = 0
    pending_blocks = []

    def flush_pending():
        nonlocal total, pending_blocks
        if pending_blocks:
            result = append_blocks_chunked(args.id, pending_blocks)
            total += result.get("blocks_created", 0)
            pending_blocks = []
            time.sleep(0.35)

    for spec in spec_list:
        # Container blocks (table, blockquote) — need multi-step API
        if spec.get("_container"):
            flush_pending()
            container_type = spec["_container"]
            if container_type == "table":
                if insert_table(args.id, spec):
                    containers_ok += 1
            elif container_type == "quote":
                if insert_blockquote(args.id, spec):
                    containers_ok += 1
            time.sleep(0.35)
            continue

        type_name = spec.get("type", "text")

        if type_name == "image":
            flush_pending()
            path = spec.get("path", "")
            if path and insert_image(args.id, path):
                images_ok += 1
            time.sleep(0.35)
        elif "elements" in spec:
            # New GFM format: pre-formatted text_run elements
            block_type = BLOCK_TYPES.get(type_name, 2)
            if type_name == "todo":
                pending_blocks.append(
                    make_block_from_elements(
                        17, spec["elements"], done=spec.get("done", False)
                    )
                )
            elif type_name == "code":
                pending_blocks.append(
                    make_block_from_elements(
                        14, spec["elements"], lang=spec.get("lang")
                    )
                )
            elif type_name == "divider":
                pending_blocks.append(make_block(22, []))
            else:
                pending_blocks.append(
                    make_block_from_elements(block_type, spec["elements"])
                )
        else:
            # Legacy JSON format: plain text strings
            block_type = BLOCK_TYPES.get(type_name)
            if block_type is None:
                print(f"Warning: unknown block type, treating as text | type={type_name}", file=sys.stderr)
                block_type = 2

            if type_name == "divider":
                pending_blocks.append(make_block(22, []))
            elif type_name in ("bullet", "ordered"):
                for t in spec.get("texts", []):
                    pending_blocks.append(make_block(block_type, [t]))
            elif type_name == "code":
                pending_blocks.append(make_block(14, [spec.get("text", "")], lang=spec.get("lang")))
            else:
                pending_blocks.append(make_block(block_type, [spec.get("text", "")]))

    flush_pending()

    print(json.dumps({
        "ok": True,
        "blocks_created": total,
        "images_inserted": images_ok,
        "containers_inserted": containers_ok,
        "blocks_deleted": deleted,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
