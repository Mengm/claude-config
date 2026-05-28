#!/usr/bin/env python3
"""
unity_artifact.py — Unity asset 引用 / Library artifact 查询（不需打开 Editor）

底层 LMDB 读取仍由 bin/unity_lmdb_dump.exe 完成（LMDB 私有 page 格式必须用
Unity 自带的 mdb.c，纯 Python 逆向不现实）。本脚本接管 dump 之上的全部解析：
guid nibble-swap、CurrentRevisions / ArtifactMetaInfo blob 解析、contentHash
定位、guid 索引、binary2text 调用、引用提取。

子命令:
  index    <proj>                       构建/刷新 guid->asset 索引
  resolve  <proj> <guid|asset>          guid -> 磁盘 artifact 文件
  inspect  <proj> <guid|asset> [--bin2text P]   asset -> binary2text 文本
  refs     <proj> <guid|asset> [--bin2text P]   查引用（文本 grep 或 binary2text）

链路（对 Unity 2022.3 源码逐字节验证）:
  .meta guid --nibble-swap--> LMDB guid
    --CurrentRevisions--> artifactID
    --ArtifactIDToArtifactMetaInfo--> producedFiles[].contentHash
    --> Library/Artifacts/<ch[:2]>/<contentHash>
磁盘文件名 = contentHash（不是 artifactID 也不是 guid）。
"""
from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DUMP_EXE = HERE / "bin" / "unity_lmdb_dump.exe"

GUID_RE = re.compile(r'^[0-9a-fA-F]{32}$')
YAML_GUID_RE = re.compile(rb'guid: ([0-9a-f]{32})')
# binary2text External References 用大写 "GUID: <hex>"，也兼容小写 "guid:"
B2T_GUID_RE = re.compile(r'guid:?\s+([0-9a-f]{32})', re.IGNORECASE)

TEXTURE_EXTS = {'.tga', '.png', '.tif', '.tiff', '.psd', '.exr', '.jpg', '.jpeg', '.bmp', '.gif'}
CACHE_TTL = 24 * 3600  # guid index / lmdb dump cache lifetime


# ---------------------------------------------------------------- helpers

def cache_dir(proj: Path) -> Path:
    d = proj / "Temp" / "unity-artifact-skill"
    d.mkdir(parents=True, exist_ok=True)
    return d


def swap_nibbles(hexstr: str) -> str:
    """.meta guid hex <-> LMDB 内存字节：每个 byte 的两个 nibble 交换。"""
    return ''.join(hexstr[i + 1] + hexstr[i] for i in range(0, len(hexstr), 2))


def fresh(path: Path, ttl: int = CACHE_TTL) -> bool:
    return path.is_file() and (time.time() - path.stat().st_mtime) < ttl


def err(msg: str):
    print(msg, file=sys.stderr)


def require_dump():
    if not DUMP_EXE.is_file():
        err(f"ERROR: {DUMP_EXE} 不存在。先编译: bin/build-mdb_dump.bat")
        sys.exit(1)


def lmdb_dump(env_file: Path, subdb: str, out: Path):
    """调用 unity_lmdb_dump.exe，把某个 sub-DB dump 成 'K <hex>\\nV <hex>' 文本。"""
    require_dump()
    with open(out, "w") as fh:
        r = subprocess.run([str(DUMP_EXE), str(env_file), subdb],
                           stdout=fh, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        err(f"ERROR: dump {subdb} 失败")
        sys.exit(1)


def iter_kv(dumpfile: Path):
    """遍历 dump 文件，yield (key_hex, value_hex)。"""
    k = None
    with open(dumpfile, "r") as fh:
        for line in fh:
            if line.startswith("K "):
                k = line[2:].strip()
            elif line.startswith("V ") and k is not None:
                yield k, line[2:].strip()
                k = None


# ---------------------------------------------------------------- guid <-> asset index

def build_index(proj: Path) -> Path:
    """扫 Assets+Packages+PackageCache 的 .meta，建 guid->relpath 索引。"""
    cache = cache_dir(proj) / "guid-index.tsv"
    dirs = [d for d in ("Assets", "Packages", "Library/PackageCache") if (proj / d).is_dir()]
    err(f"Building guid index from: {dirs}")
    start = time.time()
    n = 0
    with open(cache, "w", encoding="utf-8") as out:
        for d in dirs:
            for meta in (proj / d).rglob("*.meta"):
                try:
                    with open(meta, "rb") as fh:
                        for line in fh:
                            m = YAML_GUID_RE.match(line.strip())
                            if m:
                                rel = str(meta.with_suffix("")).replace("\\", "/")
                                rel = rel[len(str(proj).replace("\\", "/")) + 1:] \
                                    if rel.startswith(str(proj).replace("\\", "/")) else rel
                                out.write(f"{m.group(1).decode()}\t{rel}\n")
                                n += 1
                                break
                except OSError:
                    continue
    err(f"Done: {n} entries in {time.time()-start:.0f}s -> {cache}")
    return cache


def load_index(proj: Path) -> dict[str, str]:
    cache = cache_dir(proj) / "guid-index.tsv"
    if not fresh(cache):
        build_index(proj)
    idx = {}
    with open(cache, "r", encoding="utf-8") as fh:
        for line in fh:
            g, _, path = line.rstrip("\n").partition("\t")
            if g and g not in idx:
                idx[g] = path
    return idx


def lookup_guid(g: str, idx: dict[str, str]) -> str:
    if g.startswith("0000000"):
        return "<builtin>"
    return idx.get(g, "<not found>")


# ---------------------------------------------------------------- guid -> on-disk artifact

def meta_guid_from_input(proj: Path, inp: str) -> tuple[str, str | None]:
    """返回 (meta_guid_lower, abs_asset_path|None)。"""
    if GUID_RE.match(inp):
        return inp.lower(), None
    abspath = inp if (os.path.isabs(inp) or re.match(r'^[A-Za-z]:', inp)) else str(proj / inp)
    if abspath.endswith(".meta"):
        abspath = abspath[:-5]
    meta = abspath + ".meta"
    if not os.path.isfile(meta):
        err(f"ERROR: 无 .meta: {abspath}")
        sys.exit(1)
    with open(meta, "rb") as fh:
        for line in fh:
            m = YAML_GUID_RE.match(line.strip())
            if m:
                return m.group(1).decode(), abspath
    err(f"ERROR: .meta 内无 guid: {meta}")
    sys.exit(1)


def ensure_artifact_dumps(proj: Path) -> tuple[Path, Path]:
    adb = proj / "Library" / "ArtifactDB"
    if not adb.is_file():
        err(f"ERROR: {adb} 不存在（工程从未 import?）")
        sys.exit(1)
    cr = cache_dir(proj) / "CurrentRevisions.hexdump"
    mi = cache_dir(proj) / "ArtifactMetaInfo.hexdump"
    if not fresh(cr):
        err("Dumping CurrentRevisions...")
        lmdb_dump(adb, "CurrentRevisions", cr)
    if not fresh(mi):
        err("Dumping ArtifactIDToArtifactMetaInfo (~30s)...")
        lmdb_dump(adb, "ArtifactIDToArtifactMetaInfo", mi)
    return cr, mi


def current_artifact_id(cr_dump: Path, lmdb_guid: str) -> str | None:
    """CurrentRevisions: value[0:16]==guid 时，artifactID = value 末 16 字节。"""
    for _, v in iter_kv(cr_dump):
        if v[:32] == lmdb_guid:
            return v[-32:]
    return None


def metainfo_value(mi_dump: Path, artifact_id: str) -> str | None:
    for k, v in iter_kv(mi_dump):
        if k == artifact_id:
            return v
    return None


def content_hashes_on_disk(proj: Path, value_hex: str) -> list[tuple[str, Path, int]]:
    """扫 value 的 16-byte 窗口，凡能映射到磁盘存在的 artifact 文件即 contentHash。
    （避开脆弱的 blob offset 手算；producedFiles[].contentHash 必在其中。）"""
    found, seen = [], set()
    nbytes = len(value_hex) // 2
    art = proj / "Library" / "Artifacts"
    for b in range(0, nbytes - 16 + 1):
        win = value_hex[b * 2: b * 2 + 32]
        if win in seen:
            continue
        seen.add(win)
        p = art / win[:2] / win
        if p.is_file():
            found.append((win, p, p.stat().st_size))
    return found


def resolve(proj: Path, inp: str) -> list[tuple[str, Path, int]]:
    meta_guid, _ = meta_guid_from_input(proj, inp)
    lmdb_guid = swap_nibbles(meta_guid)
    cr, mi = ensure_artifact_dumps(proj)
    aid = current_artifact_id(cr, lmdb_guid)
    if not aid:
        err(f"NOT FOUND: guid {meta_guid} 无 current revision（未 import 或 Library stale）")
        return []
    val = metainfo_value(mi, aid)
    if not val:
        err(f"NOT FOUND: artifactID {aid} 无 ArtifactMetaInfo")
        return []
    hits = content_hashes_on_disk(proj, val)
    if not hits:
        err(f"NOT FOUND: artifactID {aid} 的 produced file 磁盘不存在（已 GC?）")
    return hits


# ---------------------------------------------------------------- binary2text

def find_bin2text(proj: Path, override: str | None) -> str | None:
    if override:
        return override
    if os.environ.get("UNITY_BINARY2TEXT"):
        return os.environ["UNITY_BINARY2TEXT"]
    import glob
    drive = str(proj)[:2]
    pats = [
        r"C:/Program Files/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe",
        r"D:/Program Files/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe",
        f"{drive}/Unity/Hub/Editor/*/Editor/Data/Tools/binary2text.exe",
    ]
    for pat in pats:
        for hit in glob.glob(pat):
            return hit
    fb = "F:/jnunity-2022-310/artifacts/Binary2Text/release_Win64_VS2019/binary2text.exe"
    return fb if os.path.isfile(fb) else None


def inspect(proj: Path, inp: str, bin2text: str | None) -> list[Path]:
    b2t = find_bin2text(proj, bin2text)
    if not b2t or not os.path.isfile(b2t):
        err("ERROR: binary2text.exe 找不到。传 --bin2text <path> 或设 UNITY_BINARY2TEXT")
        sys.exit(1)
    base = (Path(inp).stem if ("/" in inp or "\\" in inp) else inp).replace(".meta", "")
    out_dir = cache_dir(proj)
    outs = []
    for ch, path, _ in resolve(proj, inp):
        out = out_dir / f"{base}.{ch[:8]}.txt"
        r = subprocess.run([b2t, str(path), str(out), "-detailed"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            outs.append(out)
        else:
            err(f"WARN: binary2text 失败 {path}")
    return outs


# ---------------------------------------------------------------- refs

def refs(proj: Path, inp: str, bin2text: str | None):
    idx = load_index(proj)
    is_guid = bool(GUID_RE.match(inp))

    if is_guid:
        rel, self_guid, abspath = inp, inp.lower(), None
    else:
        abspath = inp if (os.path.isabs(inp) or re.match(r'^[A-Za-z]:', inp)) else str(proj / inp)
        if abspath.endswith(".meta"):
            abspath = abspath[:-5]
        if not os.path.isfile(abspath):
            err(f"ERROR: asset not found: {abspath}")
            sys.exit(1)
        rel = abspath[len(str(proj)) + 1:] if abspath.startswith(str(proj)) else abspath
        rel = rel.replace("\\", "/")
        self_guid, _ = meta_guid_from_input(proj, inp)

    # text YAML -> grep source; binary/guid -> binary2text dump
    guids: set[str] = set()
    is_yaml = False
    if not is_guid:
        try:
            with open(abspath, "rb") as fh:
                is_yaml = fh.read(5) == b"%YAML"
        except OSError:
            pass
    if is_yaml:
        with open(abspath, "rb") as fh:
            for m in YAML_GUID_RE.finditer(fh.read()):
                guids.add(m.group(1).decode())
    else:
        err("Binary/opaque asset: 经 LMDB 找 artifact + binary2text...")
        txts = inspect(proj, inp, bin2text)
        if not txts:
            err(f"ERROR: 无法 inspect '{inp}'")
            sys.exit(3)
        for t in txts:
            with open(t, "r", encoding="utf-8", errors="ignore") as fh:
                for m in B2T_GUID_RE.finditer(fh.read()):
                    guids.add(m.group(1).lower())

    guids.discard(self_guid)
    if not guids:
        print(f"{rel} 没有引用其他 asset")
        return

    print(f"=== {rel} 引用 {len(guids)} 个外部 guid ===")
    if self_guid:
        print(f"(self guid: {self_guid})")
    found = builtin = missing = 0
    for g in sorted(guids):
        res = lookup_guid(g, idx)
        print(f"  {g}  ->  {res}")
        if res == "<builtin>":
            builtin += 1
        elif res == "<not found>":
            missing += 1
        else:
            found += 1
    print(f"\nSummary: {found} resolved / {builtin} builtin / {missing} not found")


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description="Unity asset 引用 / Library artifact 查询")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="构建/刷新 guid->asset 索引")
    p.add_argument("project")

    p = sub.add_parser("resolve", help="guid/asset -> 磁盘 artifact 文件")
    p.add_argument("project"); p.add_argument("target")

    p = sub.add_parser("inspect", help="asset -> binary2text 文本")
    p.add_argument("project"); p.add_argument("target"); p.add_argument("--bin2text")

    p = sub.add_parser("refs", help="查引用")
    p.add_argument("project"); p.add_argument("target"); p.add_argument("--bin2text")

    a = ap.parse_args()
    proj = Path(a.project)
    if not (proj / "Assets").is_dir():
        err(f"ERROR: {proj} 不含 Assets/，不是 Unity 工程?")
        sys.exit(1)

    if a.cmd == "index":
        build_index(proj)
    elif a.cmd == "resolve":
        rows = resolve(proj, a.target)
        for ch, path, sz in rows:
            print(f"{ch}\t{path}\t{sz}")
        sys.exit(0 if rows else 3)
    elif a.cmd == "inspect":
        outs = inspect(proj, a.target, a.bin2text)
        for o in outs:
            print(o)
        sys.exit(0 if outs else 3)
    elif a.cmd == "refs":
        refs(proj, a.target, a.bin2text)


if __name__ == "__main__":
    main()
