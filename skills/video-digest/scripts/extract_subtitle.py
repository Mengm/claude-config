#!/usr/bin/env python3
"""
Extract clean text from SRT/VTT subtitle files.

Outputs:
  <name>_transcript.txt  — clean concatenated text
  <name>_timed.jsonl     — {"start": 0.0, "end": 2.5, "text": "..."} per line

Usage:
  python extract_subtitle.py <input.srt|vtt> [--output-dir <dir>]
"""

import re
import sys
import json
from pathlib import Path


def parse_srt_time(ts: str) -> float:
    """Convert SRT timestamp '00:01:23,456' to seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def parse_vtt_time(ts: str) -> float:
    """Convert VTT timestamp '00:01:23.456' to seconds."""
    return parse_srt_time(ts.replace(".", ",", ts.count(".") - 1) if ts.count(".") > 1 else ts)


def extract_srt(content: str):
    """Parse SRT content into timed entries."""
    # Split on blank lines to get blocks
    blocks = re.split(r"\n\s*\n", content.strip())
    entries = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # Find the timestamp line
        ts_line = None
        text_start = 0
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line = line
                text_start = i + 1
                break

        if not ts_line:
            continue

        # Parse timestamps
        parts = ts_line.split("-->")
        if len(parts) != 2:
            continue

        start = parse_srt_time(parts[0].strip())
        end = parse_srt_time(parts[1].strip().split()[0])  # Remove position info

        # Extract text (remaining lines after timestamp)
        text_lines = lines[text_start:]
        text = " ".join(line.strip() for line in text_lines if line.strip())

        # Remove HTML tags (some SRT files have <i>, <b>, etc.)
        text = re.sub(r"<[^>]+>", "", text)

        if text:
            entries.append({"start": round(start, 2), "end": round(end, 2), "text": text})

    return entries


def extract_vtt(content: str):
    """Parse VTT content into timed entries."""
    # Remove VTT header
    content = re.sub(r"^WEBVTT.*?\n\n", "", content, flags=re.DOTALL)
    # Remove style blocks
    content = re.sub(r"STYLE\n.*?\n\n", "", content, flags=re.DOTALL)
    # Remove NOTE blocks
    content = re.sub(r"NOTE\n.*?\n\n", "", content, flags=re.DOTALL)
    # Treat as SRT from here
    return extract_srt(content)


def deduplicate_entries(entries):
    """Remove duplicate/overlapping text from auto-generated subtitles.

    YouTube auto-generated subtitles often have overlapping entries where
    each new entry repeats part of the previous one. This deduplicates
    by only keeping the new text from each entry.
    """
    if not entries:
        return entries

    result = [entries[0]]
    prev_text = entries[0]["text"]

    for entry in entries[1:]:
        text = entry["text"]

        # Check if this entry's text starts with part of the previous
        # (common in auto-generated subtitles)
        if prev_text and text.startswith(prev_text[:len(prev_text) // 2]):
            # Only keep the new part
            new_part = text[len(prev_text):].strip()
            if new_part:
                result.append({**entry, "text": new_part})
        else:
            result.append(entry)

        prev_text = text

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_subtitle.py <input.srt|vtt> [--output-dir <dir>]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    # Parse output dir
    output_dir = input_path.parent
    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            output_dir = Path(sys.argv[idx + 1])
            output_dir.mkdir(parents=True, exist_ok=True)

    # Read and detect format
    content = input_path.read_text(encoding="utf-8", errors="replace")
    stem = input_path.stem

    if input_path.suffix.lower() == ".vtt" or content.strip().startswith("WEBVTT"):
        entries = extract_vtt(content)
    else:
        entries = extract_srt(content)

    if not entries:
        print("Error: no subtitle entries found")
        sys.exit(1)

    # Deduplicate overlapping entries
    entries = deduplicate_entries(entries)

    # Write timed JSONL
    timed_path = output_dir / f"{stem}_timed.jsonl"
    with open(timed_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Write clean transcript
    transcript_path = output_dir / f"{stem}_transcript.txt"
    full_text = " ".join(e["text"] for e in entries)
    # Clean up multiple spaces
    full_text = re.sub(r"\s+", " ", full_text).strip()
    transcript_path.write_text(full_text, encoding="utf-8")

    # Stats
    duration = entries[-1]["end"] if entries else 0
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)

    print(f"Extracted {len(entries)} entries, duration {hours}h{minutes:02d}m")
    print(f"Transcript: {transcript_path} ({transcript_path.stat().st_size:,} bytes)")
    print(f"Timed data: {timed_path} ({timed_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
