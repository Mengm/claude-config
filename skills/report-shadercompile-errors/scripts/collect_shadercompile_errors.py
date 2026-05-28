#!/usr/bin/env python3
"""Collect Unity shader compiler errors into a Chinese Markdown report."""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


PATTERNS = [
    (
        "texture",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in (?P<shader>.+?) on "
            r"(?P<api>\w+): texture count is (?P<tex>\d+), exceed "
            r"(?P<limit>\d+) in subshader (?P<subshader>\d+), pass : "
            r"(?P<pass_name>.+?) for keywords : (?P<keywords>.*)$"
        ),
    ),
    (
        "quoted_on",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in '(?P<shader>[^']+)' "
            r"on (?P<api>\w+)\s*:\s*(?P<msg>.*)$"
        ),
    ),
    (
        "quoted_kernel",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in '(?P<shader>[^']+)': "
            r"(?P<msg>.*?) at kernel (?P<kernel>.+?) at "
            r"(?P<file>.+?)\((?P<fileline>\d+)\) \(on (?P<api>\w+)\)$"
        ),
    ),
    (
        "quoted_file",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in '(?P<shader>[^']+)': "
            r"(?P<msg>.*?) at "
            r"(?P<file>(?:[A-Za-z]:|/|Assets/|PackageRepo/|Library/|"
            r"[\w./-]+\.(?:hlsl|compute|shader|cginc)).*?)"
            r"\((?P<fileline>\d+)\) \(on (?P<api>\w+)\)$"
        ),
    ),
    (
        "quoted_line",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in '(?P<shader>[^']+)': "
            r"(?P<msg>.*?) at line (?P<fileline>\d+) \(on (?P<api>\w+)\)$"
        ),
    ),
    (
        "quoted_api_paren",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in '(?P<shader>[^']+)': "
            r"(?P<msg>.*) \(on (?P<api>\w+)\)$"
        ),
    ),
    (
        "quoted_noapi",
        re.compile(
            r"^\[(?P<ts>[^\]]+)\] Shader error in '(?P<shader>[^']+)': "
            r"(?P<msg>.*)$"
        ),
    ),
]

CATEGORY_ZH = {
    "texture count > 32": "纹理数量超过 32",
    "total blob size > 50 MB": "Shader blob 总大小超过 50 MB",
    "ray tracing preprocess-only unsupported": "RayTracing 不支持 preprocess-only",
    "maximum cbuffer exceeded": "cbuffer 数量超过上限",
    "sampler register index exceeded": "sampler 寄存器编号超过上限",
    "unknown parameter type": "未知参数类型",
    "syntax error": "语法错误",
    "undeclared identifier": "未声明标识符",
    "GeneralTransform/ctx compile error": "GeneralTransform/ctx 编译错误",
    "UAV register binding conflict": "UAV 寄存器绑定冲突",
    "type conversion error": "类型转换错误",
    "unclassified": "未分类",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Unity Shader error lines into a Chinese Markdown report."
    )
    parser.add_argument("log", type=Path, help="Unity shadercompile/BuildPlayer log path")
    parser.add_argument("--out", type=Path, help="Output Markdown path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "ShaderReport",
        help="Output directory when --out is omitted",
    )
    parser.add_argument(
        "--title",
        default="Shader 编译错误报告",
        help="Report title",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Parse and print counts without writing Markdown",
    )
    return parser.parse_args()


def parse_line(line_no: int, line: str) -> dict[str, str | int]:
    rec: dict[str, str | int] = {
        "line": line_no,
        "raw": line.rstrip("\n"),
        "kind": "unparsed",
    }
    raw = str(rec["raw"])
    for kind, rx in PATTERNS:
        match = rx.match(raw)
        if match:
            rec.update(match.groupdict())
            rec["kind"] = kind
            break
    for key in (
        "shader",
        "api",
        "msg",
        "file",
        "fileline",
        "kernel",
        "pass_name",
        "keywords",
        "subshader",
        "tex",
        "limit",
    ):
        rec.setdefault(key, "")
    if not rec["shader"]:
        rec["shader"] = "?"
    return rec


def read_records(log_path: Path) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            if "Shader error" in line:
                records.append(parse_line(line_no, line))
    return records


def category(rec: dict[str, str | int]) -> str:
    if rec["kind"] == "texture":
        return "texture count > 32"
    msg = str(rec.get("msg", ""))
    if "total blob size exceed" in msg:
        return "total blob size > 50 MB"
    if "Preprocess only is not supported" in msg:
        return "ray tracing preprocess-only unsupported"
    if "maximum cbuffer exceeded" in msg:
        return "maximum cbuffer exceeded"
    if "sampler register index" in msg:
        return "sampler register index exceeded"
    if "Unknown parameter type" in msg:
        return "unknown parameter type"
    if "syntax error" in msg:
        return "syntax error"
    if "undeclared identifier" in msg:
        return "undeclared identifier"
    if "GeneralTransform" in msg or "ctx" in msg:
        return "GeneralTransform/ctx compile error"
    if "UAV registers live" in msg:
        return "UAV register binding conflict"
    if "cannot implicitly convert" in msg:
        return "type conversion error"
    return msg or "unclassified"


def category_zh(cat_or_rec: str | dict[str, str | int]) -> str:
    cat = cat_or_rec if isinstance(cat_or_rec, str) else category(cat_or_rec)
    return CATEGORY_ZH.get(cat, cat)


def detail_key(rec: dict[str, str | int]) -> tuple[str, ...]:
    if rec["kind"] == "texture":
        return (
            str(rec["shader"]),
            str(rec["api"]),
            str(rec["subshader"]),
            str(rec["pass_name"]),
            str(rec["tex"]),
            str(rec["limit"]),
            str(rec["keywords"]),
        )
    return (
        str(rec["shader"]),
        str(rec.get("api", "")),
        category(rec),
        str(rec.get("msg", "")),
        str(rec.get("kernel", "")),
        str(rec.get("file", "")),
        str(rec.get("fileline", "")),
    )


def aggregate(records: list[dict[str, str | int]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, ...], dict[str, object]] = {}
    for rec in records:
        key = detail_key(rec)
        if key not in grouped:
            item: dict[str, object] = dict(rec)
            item["count"] = 0
            item["lines"] = []
            item["category"] = category(rec)
            grouped[key] = item
        grouped[key]["count"] = int(grouped[key]["count"]) + 1
        grouped[key]["lines"].append(rec["line"])  # type: ignore[index]
    return list(grouped.values())


def compact_lines(lines: object) -> str:
    values = sorted(int(v) for v in lines)  # type: ignore[union-attr]
    if not values:
        return ""
    if len(values) == 1:
        return str(values[0])
    if len(values) == 2:
        return f"{values[0]}, {values[1]}"
    return f"{values[0]}-{values[-1]}"


def md_escape(text: object) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def code(text: object) -> str:
    value = str(text or "")
    if not value:
        return ""
    return "`" + value.replace("`", "\\`") + "`"


def platform_set(recs: list[dict[str, str | int]]) -> str:
    vals = sorted({str(r.get("api") or "unknown") for r in recs})
    return ", ".join(vals)


def category_summary(recs: list[dict[str, str | int]]) -> str:
    counts = Counter(category(r) for r in recs)
    return "<br>".join(
        f"{md_escape(category_zh(k))}: {v}" for k, v in counts.most_common()
    )


def variant_availability(recs: list[dict[str, str | int]]) -> str:
    tex = [r for r in recs if r["kind"] == "texture"]
    kernels = [r for r in recs if r.get("kernel")]
    no_keywords = len(recs) - len(tex)
    parts: list[str] = []
    if tex:
        parts.append(f"keyword 组合: {len({str(r.get('keywords', '')) for r in tex})}")
        parts.append(
            "平台变体记录: "
            f"{len({(str(r.get('api', '')), str(r.get('keywords', ''))) for r in tex})}"
        )
    if kernels:
        parts.append(f"kernel: {len({str(r.get('kernel', '')) for r in kernels})}")
    if no_keywords:
        parts.append("log 未打印 keywords")
    return "<br>".join(parts)


def output_path(args: argparse.Namespace) -> Path:
    if args.out:
        return args.out
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return args.output_dir / f"shadercompile_errors_{stamp}.md"


def build_markdown(
    args: argparse.Namespace,
    records: list[dict[str, str | int]],
    unique: list[dict[str, object]],
) -> str:
    texture_records = sorted(
        [r for r in unique if r["kind"] == "texture"],
        key=lambda r: (
            str(r["shader"]),
            str(r["api"]),
            int(str(r.get("tex") or 0)),
            str(r["keywords"]),
        ),
    )
    other_records = sorted(
        [r for r in unique if r["kind"] != "texture"],
        key=lambda r: (
            str(r["shader"]),
            str(r.get("api", "")),
            category_zh(str(r["category"])),
            str(r.get("kernel", "")),
            str(r.get("file", "")),
            int(str(r.get("fileline") or 0)),
            str(r.get("msg", "")),
        ),
    )
    unique_keyword_sets = len({str(r.get("keywords", "")) for r in texture_records})

    by_shader: dict[str, list[dict[str, str | int]]] = defaultdict(list)
    for rec in records:
        by_shader[str(rec["shader"])].append(rec)
    unique_by_shader = Counter(str(rec["shader"]) for rec in unique)

    lines: list[str] = [
        f"# {args.title}",
        "",
        f"- 源 log: `{args.log}`",
        f"- 生成时间: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- 匹配到的 `Shader error` 行数: **{len(records)}**",
        f"- 去重后的错误记录数: **{len(unique)}**",
        f"- 带完整 keywords 的平台变体记录数: **{len(texture_records)}**",
        f"- 这些记录里的唯一 keyword 组合数: **{unique_keyword_sets}**",
        "",
        "## 说明",
        "",
        "- 只有纹理数量超限类错误在 log 里打印了完整 Unity keywords，完整列表见 `完整 Keyword 变体明细`。",
        "- 这里区分 `keyword 组合` 和 `平台变体记录`：同一组 keywords 可能在 `d3d11` 和 `d3d12` 各报一次。",
        "- Compute shader 错误用 shader + platform + kernel + 文件行号表示，因为这类 log 没有 Unity keyword 列表。",
        "- 其它 shader 错误用 shader + platform + 编译器消息 + 源文件/Program 表示；log 本身没有打印它们的 keyword 组合。",
        "- 完全相同的非 keyword 错误会合并，`出现次数` 和 `log 行号` 会标出重复范围。",
        "",
        "## 关键结论",
        "",
    ]

    top_shader, top_recs = ("", [])
    if by_shader:
        top_shader, top_recs = max(by_shader.items(), key=lambda item: len(item[1]))
    if top_shader:
        lines.append(
            f"- `{top_shader}` 的错误最多，共 {len(top_recs)} 行；"
            f"主要类型：{category_summary(top_recs)}。"
        )
    if texture_records:
        lines.append(
            "- 纹理数量超限类错误是唯一带完整 keywords 的错误；"
            f"共 {unique_keyword_sets} 组 keyword 组合、{len(texture_records)} 条平台变体记录。"
        )
    lines.extend(
        [
            "- 没有打印 keywords 的错误不要反推具体 keyword 组合；报告只保留 log 能证明的 kernel、program、文件行号或 shader 级信息。",
            "",
            "## 按 Shader 汇总",
            "",
            "| Shader | 错误行数 | 去重记录数 | 平台 | 错误类型 | 可用的变体信息 |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for shader, recs in sorted(by_shader.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(
            f"| {code(shader)} | {len(recs)} | {unique_by_shader[shader]} | "
            f"{md_escape(platform_set(recs))} | {category_summary(recs)} | "
            f"{variant_availability(recs)} |"
        )

    lines.extend(
        [
            "",
            "## 完整 Keyword 变体明细",
            "",
            "这些行是 log 明确打印完整 keyword 组合的变体。`d3d11` 和 `d3d12` 保留为不同平台记录。",
            "",
            "| # | 出现次数 | Log 行号 | Shader | 平台 | SubShader | Pass | 纹理数量 | Keywords |",
            "|---:|---:|---|---|---|---:|---|---:|---|",
        ]
    )
    for idx, rec in enumerate(texture_records, 1):
        lines.append(
            f"| {idx} | {rec['count']} | {compact_lines(rec['lines'])} | "
            f"{code(rec['shader'])} | {code(rec['api'])} | {rec.get('subshader', '')} | "
            f"{code(rec.get('pass_name', ''))} | {rec.get('tex', '')} | "
            f"{code(rec.get('keywords', ''))} |"
        )

    lines.extend(
        [
            "",
            "## 其它 Shader 错误记录",
            "",
            "这些错误在 log 里没有完整 keyword 组合。这里列出 log 能提供的最具体身份：kernel、program、文件行号或 shader 级记录。",
            "",
            "| # | 出现次数 | Log 行号 | Shader | 平台 | 错误类型 | Kernel / Program / Pass 线索 | 源位置 | 原始消息 |",
            "|---:|---:|---|---|---|---|---|---|---|",
        ]
    )
    for idx, rec in enumerate(other_records, 1):
        msg = str(rec.get("msg", ""))
        program = ""
        program_match = re.search(r"Program '([^']+)'", msg)
        if program_match:
            program = program_match.group(1)
        hint = str(rec.get("kernel") or program)
        file_value = str(rec.get("file", ""))
        if not hint and "RayTracingPass.hlsl" in file_value:
            hint = "RayTracingPass"
        if not hint and "VGRasterShadingPass.hlsl" in file_value:
            hint = "VGRasterShadingPass"
        if not hint and "VGTransformUtility.hlsl" in file_value:
            hint = "VirtualGeometry/VGTransformUtility"
        if not hint and "Preprocess only is not supported for ray tracing shaders" in msg:
            hint = "RayTracing / preprocess-only"
        if not hint and "total blob size exceed" in msg:
            hint = "shader blob size"
        location = ""
        if file_value:
            location = f"{file_value}:{rec.get('fileline', '')}"
        elif rec.get("fileline"):
            location = f"line {rec.get('fileline')}"
        lines.append(
            f"| {idx} | {rec['count']} | {compact_lines(rec['lines'])} | "
            f"{code(rec['shader'])} | {code(rec.get('api') or 'unknown')} | "
            f"{md_escape(category_zh(str(rec['category'])))} | {code(hint)} | "
            f"{code(location)} | {code(msg)} |"
        )

    keyword_counts = Counter()
    texture_counts = Counter()
    platform_texture_counts = Counter()
    for rec in records:
        if rec["kind"] == "texture":
            texture_counts[str(rec.get("tex", ""))] += 1
            platform_texture_counts[str(rec.get("api", ""))] += 1
            for keyword in str(rec.get("keywords", "")).split():
                keyword_counts[keyword] += 1

    lines.extend(
        [
            "",
            "## 纹理超限变体的 Keyword 统计",
            "",
            "### 平台分布",
            "",
            "| 平台 | 错误行数 |",
            "|---|---:|",
        ]
    )
    for platform, count in sorted(platform_texture_counts.items()):
        lines.append(f"| {code(platform)} | {count} |")

    lines.extend(["", "### 纹理数量分布", "", "| 纹理数量 | 错误行数 |", "|---:|---:|"])
    for tex, count in sorted(texture_counts.items(), key=lambda kv: int(kv[0])):
        lines.append(f"| {tex} | {count} |")

    lines.extend(
        [
            "",
            "### 纹理超限错误中的 Keyword 出现频次",
            "",
            "| Keyword | 错误行数 |",
            "|---|---:|",
        ]
    )
    for keyword, count in keyword_counts.most_common():
        lines.append(f"| {code(keyword)} | {count} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    if not args.log.exists():
        raise SystemExit(f"Log not found: {args.log}")

    records = read_records(args.log)
    unique = aggregate(records)
    texture_records = [r for r in unique if r["kind"] == "texture"]
    unique_keyword_sets = len({str(r.get("keywords", "")) for r in texture_records})

    print(f"matched_shader_error_lines={len(records)}")
    print(f"unique_records={len(unique)}")
    print(f"keyword_platform_records={len(texture_records)}")
    print(f"unique_keyword_sets={unique_keyword_sets}")

    if args.summary_only:
        return 0

    out = output_path(args)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_markdown(args, records, unique), encoding="utf-8")
    print(f"output={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
