#!/usr/bin/env python3
"""Scan large Unity BuildPlayer.log files for packaging failure causes."""

from __future__ import annotations

import argparse
import mmap
import os
import re
import sys
from pathlib import Path


DEFAULT_PATTERNS = [
    b"FAILURE:",
    b"CommandInvokationFailure",
    b"Build failed",
    b"Build Failed",
    b"BUILD FAILED",
    b"Execution failed",
    b"Gradle build failed",
    b"Exception",
    b"ERROR",
    b"Error",
    b"error",
    b"apk miss",
    b"StackOverflowError",
    b"namespace",
    b"AndroidManifest.xml",
]

SENSITIVE_LINE = re.compile(
    r"(TOKEN|TICKET|COOKIE|PASSWORD|SECRET|KEY|AUTH|CREDENTIAL)",
    re.IGNORECASE,
)


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def redact(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if SENSITIVE_LINE.search(line):
            lines.append("[redacted sensitive environment line]")
        else:
            lines.append(line)
    return "\n".join(lines)


def find_positions(mm: mmap.mmap, pattern: bytes, max_first: int = 3, max_last: int = 5):
    first: list[int] = []
    last: list[int] = []
    count = 0
    start = 0
    while True:
        pos = mm.find(pattern, start)
        if pos < 0:
            break
        count += 1
        if len(first) < max_first:
            first.append(pos)
        last.append(pos)
        if len(last) > max_last:
            last.pop(0)
        start = pos + len(pattern)
    return count, first, last


def snippet(path: Path, pos: int, context: int, size: int) -> str:
    start = max(0, pos - context)
    end = min(size, pos + context)
    with path.open("rb") as fh:
        fh.seek(start)
        data = fh.read(end - start)
    return redact(decode(data))


def print_section(title: str):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Path to BuildPlayer.log")
    parser.add_argument("--context", type=int, default=3500, help="Bytes around each hit")
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Extra byte/string pattern to search; can be repeated",
    )
    parser.add_argument(
        "--snippets",
        type=int,
        default=8,
        help="Maximum snippets to print from high-signal hit positions",
    )
    args = parser.parse_args()

    path = args.log
    if not path.is_file():
        print(f"Log file not found: {path}", file=sys.stderr)
        return 2

    patterns = DEFAULT_PATTERNS + [p.encode("utf-8", errors="replace") for p in args.pattern]
    size = os.path.getsize(path)
    print(f"Log: {path}")
    print(f"Size: {size:,} bytes")

    all_hits: dict[bytes, tuple[int, list[int], list[int]]] = {}
    with path.open("rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        for pattern in patterns:
            count, first, last = find_positions(mm, pattern)
            if count:
                all_hits[pattern] = (count, first, last)
        mm.close()

    print_section("Pattern Summary")
    for pattern, (count, first, last) in all_hits.items():
        label = pattern.decode("utf-8", errors="replace")
        print(f"{label}: count={count}, first={first}, last={last}")

    priority = [
        b"FAILURE:",
        b"CommandInvokationFailure",
        b"Gradle build failed",
        b"Execution failed",
        b"BUILD FAILED",
        b"Build failed",
        b"Build Failed",
        b"apk miss",
        b"ERROR",
        b"Exception",
    ]
    selected: list[int] = []
    for pattern in priority:
        hit = all_hits.get(pattern)
        if not hit:
            continue
        for pos in reversed(hit[2]):
            if all(abs(pos - existing) > args.context for existing in selected):
                selected.append(pos)
            if len(selected) >= args.snippets:
                break
        if len(selected) >= args.snippets:
            break

    print_section("High Signal Snippets")
    for pos in selected:
        print_section(f"offset {pos}")
        print(snippet(path, pos, args.context, size))

    print_section("Heuristic Diagnosis")
    with path.open("rb") as fh:
        tail_size = min(size, 20 * 1024 * 1024)
        fh.seek(size - tail_size)
        tail = fh.read(tail_size)

    if b"namespace not specified" in tail and b"generateDebugBuildConfig" in tail:
        print(
            "Likely root cause: Android Gradle launcher module lacks android.namespace "
            "and its AndroidManifest.xml does not provide a package name. Check generated "
            "launcher/build.gradle or Gradle templates and add the expected namespace."
        )
    elif b"CommandInvokationFailure" in tail and b"Gradle build failed" in tail:
        print("Likely root cause: Gradle failed during Android player post-processing.")
    elif b"apk miss" in tail:
        print("Final symptom: APK is missing. Search earlier snippets for the Unity/Gradle root cause.")
    else:
        print("No specific heuristic matched. Use the high-signal snippets above.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
