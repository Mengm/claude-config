#!/usr/bin/env python3
"""Scan large CI/build logs and print high-signal failure snippets."""

from __future__ import annotations

import argparse
import mmap
import os
import re
import sys
from pathlib import Path


DEFAULT_PATTERNS = [
    b"FAILURE:",
    b"FAILED",
    b"BUILD FAILED",
    b"Build failed",
    b"Build Failed",
    b"CommandInvokationFailure",
    b"Execution failed",
    b"Exception",
    b"Traceback",
    b"ERROR",
    b"Error",
    b"error",
    b"exit code",
    b"script returned exit code",
    b"fatal error",
    b"CMake Error",
    b"clang:",
    b"xcodebuild",
    b"MSB",
]

SENSITIVE_LINE = re.compile(
    r"(TOKEN|TICKET|COOKIE|PASSWORD|SECRET|KEY|AUTH|CREDENTIAL|JENKINS_SERVER_COOKIE|P4_TICKET)",
    re.IGNORECASE,
)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def redact(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if SENSITIVE_LINE.search(line):
            out.append("[redacted sensitive line]")
        else:
            out.append(line)
    return "\n".join(out)


def find_positions(mm: mmap.mmap, pattern: bytes, max_first: int, max_last: int):
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


def read_snippet(path: Path, pos: int, context: int, size: int) -> str:
    start = max(0, pos - context)
    end = min(size, pos + context)
    with path.open("rb") as fh:
        fh.seek(start)
        return redact(decode(fh.read(end - start)))


def heading(text: str) -> None:
    print()
    print("=" * 100)
    print(text)
    print("=" * 100)


def main() -> int:
    configure_stdout()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--pattern", action="append", default=[], help="Extra search pattern")
    parser.add_argument("--context", type=int, default=3000, help="Bytes around each hit")
    parser.add_argument("--snippets", type=int, default=8, help="Maximum snippets to print")
    parser.add_argument("--tail-mb", type=int, default=64, help="Tail size used for heuristic summary")
    args = parser.parse_args()

    path = args.log
    if not path.is_file():
        print(f"Log not found: {path}", file=sys.stderr)
        return 2

    patterns = DEFAULT_PATTERNS + [p.encode("utf-8", errors="replace") for p in args.pattern]
    size = os.path.getsize(path)
    print(f"Log: {path}")
    print(f"Size: {size:,} bytes")

    hits: dict[bytes, tuple[int, list[int], list[int]]] = {}
    with path.open("rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        for pattern in patterns:
            result = find_positions(mm, pattern, 3, 5)
            if result[0]:
                hits[pattern] = result
        mm.close()

    heading("Pattern Summary")
    for pattern, (count, first, last) in hits.items():
        print(f"{pattern.decode('utf-8', errors='replace')}: count={count}, first={first}, last={last}")

    priority = [
        b"FAILURE:",
        b"CommandInvokationFailure",
        b"Execution failed",
        b"BUILD FAILED",
        b"Build failed",
        b"Build Failed",
        b"FAILED",
        b"fatal error",
        b"CMake Error",
        b"clang:",
        b"Traceback",
        b"ERROR",
        b"Exception",
    ]
    selected: list[int] = []
    for pattern in priority:
        if pattern not in hits:
            continue
        for pos in reversed(hits[pattern][2]):
            if all(abs(pos - existing) > args.context for existing in selected):
                selected.append(pos)
            if len(selected) >= args.snippets:
                break
        if len(selected) >= args.snippets:
            break

    heading("High Signal Snippets")
    for pos in selected:
        heading(f"offset {pos}")
        print(read_snippet(path, pos, args.context, size))

    tail_size = min(size, args.tail_mb * 1024 * 1024)
    with path.open("rb") as fh:
        fh.seek(size - tail_size)
        tail = fh.read(tail_size)

    heading("Heuristic Summary")
    if b"namespace not specified" in tail and b"generateDebugBuildConfig" in tail:
        print("Likely root cause: Android Gradle module lacks android.namespace or manifest package.")
    elif b"CommandInvokationFailure" in tail and b"Gradle" in tail:
        print("Likely root cause: Gradle failed during Unity Android post-processing.")
    elif b"CMake Error" in tail:
        print("Likely root cause: CMake configure/generate failed.")
    elif b"clang:" in tail or b"fatal error:" in tail:
        print("Likely root cause: native compile/link step failed; inspect compiler snippet above.")
    elif b"script returned exit code" in tail or b"exit code" in tail:
        print("Final symptom: script exited non-zero; inspect earlier high-signal snippets for root cause.")
    else:
        print("No specific heuristic matched. Inspect high-signal snippets and add --pattern as needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
