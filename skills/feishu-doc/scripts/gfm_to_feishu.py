"""Convert GFM markdown to Feishu document block specifications.

Uses mistune v3 to parse markdown into an AST, then walks the AST
to produce Feishu-compatible block specs.

Output types:
- Flat blocks: {"type": "text"|"heading2"|..., "elements": [...]}
- Container specs: {"_container": "table"|"quote", ...}
- Image specs: {"type": "image", "path": "..."}
"""

import re
import sys

import mistune

_SAFE_URL_SCHEMES = ("http://", "https://", "mailto:", "#", "/")

# Feishu code block language IDs
LANG_MAP = {
    "python": 14, "go": 8, "java": 11, "javascript": 12, "typescript": 27,
    "bash": 3, "shell": 22, "sql": 23, "json": 13, "yaml": 31,
    "markdown": 37, "rust": 20, "c": 4, "cpp": 5, "csharp": 6,
    "html": 9, "css": 7, "plaintext": 1, "ruby": 19, "php": 17,
    "swift": 25, "kotlin": 15, "scala": 21, "r": 18, "lua": 16,
    "perl": 28, "xml": 30, "toml": 29, "dockerfile": 33, "makefile": 34,
    "protobuf": 35, "thrift": 36,
}

MAX_TABLE_ROWS = 20
MAX_TABLE_COLS = 10


# ---------------------------------------------------------------------------
# Inline formatting engine
# ---------------------------------------------------------------------------

def parse_inline(children: list[dict], styles: dict | None = None) -> list[dict]:
    """Recursively convert mistune inline AST nodes to Feishu text_run elements.

    Args:
        children: List of mistune inline AST nodes.
        styles: Accumulated text_element_style dict from parent nodes.

    Returns:
        List of Feishu text_run element dicts.
    """
    styles = styles or {}
    elements: list[dict] = []

    for node in children:
        t = node.get("type", "")

        if t == "text":
            raw = node.get("raw", "")
            if not raw:
                continue
            elem: dict = {"text_run": {"content": raw}}
            if styles:
                elem["text_run"]["text_element_style"] = dict(styles)
            elements.append(elem)

        elif t == "strong":
            elements.extend(
                parse_inline(node.get("children", []), {**styles, "bold": True})
            )

        elif t == "emphasis":
            elements.extend(
                parse_inline(node.get("children", []), {**styles, "italic": True})
            )

        elif t == "strikethrough":
            elements.extend(
                parse_inline(
                    node.get("children", []), {**styles, "strikethrough": True}
                )
            )

        elif t == "codespan":
            raw = node.get("raw", "")
            elem = {
                "text_run": {
                    "content": raw,
                    "text_element_style": {**styles, "inline_code": True},
                }
            }
            elements.append(elem)

        elif t == "link":
            url = node.get("attrs", {}).get("url", "")
            # Block dangerous protocols (javascript:, data:, vbscript:, etc.)
            if url and not url.startswith(_SAFE_URL_SCHEMES):
                url = ""
            link_style = {**styles, "link": {"url": url}}
            child_elements = parse_inline(node.get("children", []), link_style)
            if child_elements:
                elements.extend(child_elements)
            else:
                elements.append(
                    {"text_run": {"content": url, "text_element_style": link_style}}
                )

        elif t == "image":
            # Images are block-level in Feishu. Return a marker so the
            # caller can split the paragraph.
            url = node.get("attrs", {}).get("url", "")
            elements.append({"_image": url})

        elif t in ("softbreak", "linebreak"):
            elem = {"text_run": {"content": "\n"}}
            if styles:
                elem["text_run"]["text_element_style"] = dict(styles)
            elements.append(elem)

        elif t == "inline_html":
            raw = re.sub(r"<[^>]+>", "", node.get("raw", ""))
            if raw:
                elem = {"text_run": {"content": raw}}
                if styles:
                    elem["text_run"]["text_element_style"] = dict(styles)
                elements.append(elem)

        else:
            # Unknown inline node — try to extract raw text
            raw = node.get("raw", "")
            if raw:
                elem = {"text_run": {"content": raw}}
                if styles:
                    elem["text_run"]["text_element_style"] = dict(styles)
                elements.append(elem)

    return elements


def _split_images(elements: list[dict]) -> list[dict]:
    """Split a list of elements containing _image markers into separate specs.

    If a paragraph contains only an image, return an image spec.
    If it contains text + images, split into text block + image block(s).
    """
    has_images = any("_image" in e for e in elements)
    if not has_images:
        return [{"type": "text", "elements": elements}]

    results: list[dict] = []
    text_buf: list[dict] = []

    for elem in elements:
        if "_image" in elem:
            if text_buf:
                # Strip trailing whitespace-only text_runs
                while text_buf and text_buf[-1].get("text_run", {}).get("content", "").strip() == "":
                    text_buf.pop()
                if text_buf:
                    results.append({"type": "text", "elements": list(text_buf)})
                text_buf.clear()
            results.append({"type": "image", "path": elem["_image"]})
        else:
            text_buf.append(elem)

    if text_buf:
        while text_buf and text_buf[-1].get("text_run", {}).get("content", "").strip() == "":
            text_buf.pop()
        if text_buf:
            results.append({"type": "text", "elements": list(text_buf)})

    return results


# ---------------------------------------------------------------------------
# Block-level handlers
# ---------------------------------------------------------------------------

def _get_inline_children(node: dict) -> list[dict]:
    """Get inline elements from a node, handling both paragraph and block_text."""
    children = node.get("children", [])
    if not children:
        return []
    # For list items, the content is wrapped in block_text
    if len(children) == 1 and children[0].get("type") == "block_text":
        return children[0].get("children", [])
    return children


def _process_heading(node: dict) -> list[dict]:
    level = node.get("attrs", {}).get("level", 1)
    level = min(level, 9)  # Feishu supports heading1-9
    elements = parse_inline(node.get("children", []))
    return [{"type": f"heading{level}", "elements": elements}]


def _process_paragraph(node: dict) -> list[dict]:
    elements = parse_inline(node.get("children", []))
    if not elements:
        return []
    return _split_images(elements)


def _process_code_block(node: dict) -> list[dict]:
    raw = node.get("raw", "")
    # Strip trailing newline added by mistune
    if raw.endswith("\n"):
        raw = raw[:-1]
    lang = node.get("attrs", {}).get("info", "") or None
    return [{"type": "code", "text": raw, "lang": lang}]


def _process_list(node: dict) -> list[dict]:
    ordered = node.get("attrs", {}).get("ordered", False)
    results: list[dict] = []

    for item in node.get("children", []):
        item_type = item.get("type", "")

        if item_type == "task_list_item":
            checked = item.get("attrs", {}).get("checked", False)
            inline_children = _get_inline_children(item)
            elements = parse_inline(inline_children)
            if elements:
                results.append({"type": "todo", "elements": elements, "done": checked})

        elif item_type == "list_item":
            inline_children = _get_inline_children(item)
            # Check if list_item contains a nested list
            sub_lists = [
                c for c in item.get("children", []) if c.get("type") == "list"
            ]
            elements = parse_inline(inline_children)
            if elements:
                block_type = "ordered" if ordered else "bullet"
                results.append({"type": block_type, "elements": elements})
            # Flatten nested lists (Feishu API doesn't support list nesting well)
            for sub_list in sub_lists:
                results.extend(_process_list(sub_list))

    return results


def _process_blockquote(node: dict) -> list[dict]:
    """Convert blockquote to a quote_container spec."""
    children_specs: list[dict] = []
    for child in node.get("children", []):
        children_specs.extend(_dispatch(child))

    if not children_specs:
        return []

    return [{"_container": "quote", "children": children_specs}]


def _process_table(node: dict) -> list[dict]:
    """Convert GFM table to a table container spec."""
    header_cells: list[list[dict]] = []
    body_rows: list[list[list[dict]]] = []

    for child in node.get("children", []):
        if child.get("type") == "table_head":
            for cell in child.get("children", []):
                header_cells.append(parse_inline(cell.get("children", [])))

        elif child.get("type") == "table_body":
            for row in child.get("children", []):
                row_cells: list[list[dict]] = []
                for cell in row.get("children", []):
                    row_cells.append(parse_inline(cell.get("children", [])))
                body_rows.append(row_cells)

    if not header_cells:
        return []

    # Enforce size limits
    n_cols = min(len(header_cells), MAX_TABLE_COLS)
    n_rows = min(len(body_rows), MAX_TABLE_ROWS)

    if len(body_rows) > MAX_TABLE_ROWS:
        print(
            f"Warning: table truncated from {len(body_rows)} to {MAX_TABLE_ROWS} rows",
            file=sys.stderr,
        )

    header_cells = header_cells[:n_cols]
    body_rows = [row[:n_cols] for row in body_rows[:n_rows]]

    return [
        {
            "_container": "table",
            "header": header_cells,
            "rows": body_rows,
            "n_cols": n_cols,
            "n_rows": n_rows + 1,  # +1 for header row
        }
    ]


def _process_thematic_break(_node: dict) -> list[dict]:
    return [{"type": "divider"}]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_HANDLERS = {
    "heading": _process_heading,
    "paragraph": _process_paragraph,
    "block_code": _process_code_block,
    "list": _process_list,
    "block_quote": _process_blockquote,
    "table": _process_table,
    "thematic_break": _process_thematic_break,
    "blank_line": lambda _: [],
}


def _dispatch(node: dict) -> list[dict]:
    handler = _HANDLERS.get(node.get("type", ""))
    if handler:
        return handler(node)
    # Unknown block — try to extract text
    raw = node.get("raw", "")
    if raw:
        return [{"type": "text", "elements": [{"text_run": {"content": raw}}]}]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_markdown(text: str) -> list[dict]:
    """Parse GFM markdown and return a list of Feishu block specs.

    Returns a mixed list where each item is either:
    - A flat block spec: {"type": ..., "elements": [...]}
    - A container spec: {"_container": "table"|"quote", ...}
    - An image spec: {"type": "image", "path": "..."}
    - A code spec: {"type": "code", "text": "...", "lang": "..."}
    - A divider spec: {"type": "divider"}
    """
    md = mistune.create_markdown(
        renderer="ast",
        plugins=["strikethrough", "table", "task_lists"],
    )
    tokens = md(text)

    result: list[dict] = []
    for token in tokens:
        result.extend(_dispatch(token))
    return result
