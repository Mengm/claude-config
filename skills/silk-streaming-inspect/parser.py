#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Silk Streaming 导出数据解析工具

解析 ReleaseData/Silk/BlockV2~/ 下的二进制导出数据。

文件格式（ZeroFormatter，结构来源 PackageRepo/com.jngame.silk-streaming/Runtime/）：

  background_info.bin
    NativeArray<StreamingLayerInfoHeader>
    [int32 arrayLen][StreamingLayerInfoHeader x arrayLen]

  layer_block_XX_YY.bin
    Dictionary<int chunkIndex, NativeArray<StreamingLayerInfoHeader>>
    [int32 dictCount][[int32 chunkIndex][int32 arrayLen][LayerInfoHeader x arrayLen]] x dictCount
    chunkIndex = (sectorX << 16) | sectorY

  block_XX_YY.bin / background.bin
    每个 layer 的数据布局（起点由对应 LayerInfoHeader.BinaryHeader.FileOffset 指定）：
      [binary data ... 长度 = allBinarySize]
      [asset header data ... 长度 = InsideOffset - 0]
      [serialized StreamingLayerHeader]      <-- 起点 = FileOffset + InsideOffset
      [int32 checkBytes = FileOffset]

ZeroFormattable struct 序列化约定：
  - struct 整体: [int32 bodyLen][fields...]
  - 复合字段（嵌套 ZeroFormattable struct: Bounds/Vector3/Vector2Int/BinaryDataHeader/
    StreamingAssetHeader/StreamingLayerInfoHeader 等）自带 [int32 bodyLen] 前缀
  - 原始字段（int/float/short/long/bool）直接裸字节，无前缀
  - array<T>: [int32 length][T x length]
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path("f:/Perforce/Project-T3-baiyuan")
SCENE_BASE = PROJECT_ROOT / "client/Assets/ResTemp/Scene/PCGLevel/Lithos"


# StreamingAssetType / SceneObjectLevel：未知值原样输出
ASSET_TYPE_NAMES = {
    0: "ECS_Legacy",
    1: "GameObject",
    2: "ECS",
    3: "HIMR",
    4: "Collision",
    5: "VirtualGeometry",
    6: "Light",
    7: "VolumetricFog",
    8: "Trigger",
}

SCENE_OBJECT_LEVEL_NAMES = {
    0: "Level1",
    1: "Level2",
    2: "Level3",
}


# ---------- 字节读取 ----------

class Reader:
    __slots__ = ("buf", "size")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.size = len(buf)

    def i32(self, off: int) -> int:
        return struct.unpack_from("<i", self.buf, off)[0]

    def i64(self, off: int) -> int:
        return struct.unpack_from("<q", self.buf, off)[0]

    def i16(self, off: int) -> int:
        return struct.unpack_from("<h", self.buf, off)[0]

    def f32(self, off: int) -> float:
        return struct.unpack_from("<f", self.buf, off)[0]

    def u8(self, off: int) -> int:
        return self.buf[off]


# ---------- 数据结构 ----------

@dataclass
class BinaryDataHeader:
    file_offset: int
    file_size: int
    resource_id: int


@dataclass
class Bounds:
    cx: float; cy: float; cz: float
    sx: float; sy: float; sz: float


@dataclass
class StreamingLayerInfoHeader:
    LoadDistance: float
    UnloadDistance: float
    NearLoadDistance: float
    NearUnloadDistance: float
    Bounds: Bounds
    SectorIndex: tuple[int, int]
    HLODLevel: int
    RegionId: int
    BinaryHeader: BinaryDataHeader
    InsideOffset: int
    SkipLoadDistanceScale: bool
    AssetMask: int
    UniqueId: int
    YSplitId: int = 0


@dataclass
class StreamingAssetHeader:
    Bounds: Bounds
    CustomLayerId: int
    Offset: int
    AssetType: int
    SceneObjectLevel: int
    LoadDistance: float
    CustomLoadControlData: int


@dataclass
class StreamingLayerHeader:
    HasGameObjectInAssets: bool
    HasCustomLayer: bool
    AssetHeaders: list[StreamingAssetHeader] = field(default_factory=list)


# ---------- ZeroFormatter struct 反序列化 ----------

def read_bounds(r: Reader, off: int) -> tuple[Bounds, int]:
    """Bounds: [int32 bodyLen=32][Vector3 center][Vector3 size]
    Vector3: [int32 bodyLen=12][f32 x][f32 y][f32 z] = 16 字节
    总大小 = 4 + 16 + 16 = 36"""
    p = off + 4
    cx = r.f32(p + 4); cy = r.f32(p + 8); cz = r.f32(p + 12)
    p += 16
    sx = r.f32(p + 4); sy = r.f32(p + 8); sz = r.f32(p + 12)
    return Bounds(cx, cy, cz, sx, sy, sz), 36


def read_vector2int(r: Reader, off: int) -> tuple[tuple[int, int], int]:
    """[int32 bodyLen=8][int32 x][int32 y] = 12 字节"""
    x = r.i32(off + 4)
    y = r.i32(off + 8)
    return (x, y), 12


def read_binary_data_header(r: Reader, off: int) -> tuple[BinaryDataHeader, int]:
    """[int32 bodyLen=16][int32 FileOffset][int32 FileSize][int64 ResourceId] = 20 字节"""
    fo = r.i32(off + 4)
    fs = r.i32(off + 8)
    rid = r.i64(off + 12)
    return BinaryDataHeader(fo, fs, rid), 20


def read_layer_info_header(r: Reader, off: int) -> tuple[StreamingLayerInfoHeader, int]:
    """StreamingLayerInfoHeader:
      [int32 bodyLen]
      [f32 LoadDistance][f32 UnloadDistance]
      [f32 NearLoadDistance][f32 NearUnloadDistance]
      [Bounds=36][Vector2Int=12]
      [int32 HLODLevel][int32 RegionId]
      [BinaryDataHeader=20]
      [int32 InsideOffset]
      [bool SkipLoadDistanceScale]  1 字节
      [int64 AssetMask][int64 UniqueId]
      [int32 YSplitId]  Optional — 仅当 bodyLen 仍有剩余时存在
    """
    body_len = r.i32(off)
    body_end = off + 4 + body_len
    p = off + 4
    LoadDistance       = r.f32(p); p += 4
    UnloadDistance     = r.f32(p); p += 4
    NearLoadDistance   = r.f32(p); p += 4
    NearUnloadDistance = r.f32(p); p += 4
    bounds, n = read_bounds(r, p); p += n
    sector, n = read_vector2int(r, p); p += n
    HLODLevel = r.i32(p); p += 4
    RegionId  = r.i32(p); p += 4
    bdh, n = read_binary_data_header(r, p); p += n
    InsideOffset = r.i32(p); p += 4
    SkipLoadDistanceScale = bool(r.u8(p)); p += 1
    AssetMask = r.i64(p); p += 8
    UniqueId  = r.i64(p); p += 8
    YSplitId = 0
    if p < body_end:
        YSplitId = r.i32(p); p += 4
    return (StreamingLayerInfoHeader(
        LoadDistance, UnloadDistance, NearLoadDistance, NearUnloadDistance,
        bounds, sector, HLODLevel, RegionId, bdh,
        InsideOffset, SkipLoadDistanceScale, AssetMask, UniqueId, YSplitId,
    ), body_end - off)


def read_asset_header(r: Reader, off: int) -> tuple[StreamingAssetHeader, int]:
    """StreamingAssetHeader:
      [int32 bodyLen]
      [Bounds=36]
      [int32 CustomLayerId][int32 Offset]
      [int16 AssetType][int16 SceneObjectLevel]
      [f32   LoadDistance]
      [int32 CustomLoadControlData]
    """
    body_len = r.i32(off)
    body_end = off + 4 + body_len
    p = off + 4
    bounds, n = read_bounds(r, p); p += n
    CustomLayerId    = r.i32(p); p += 4
    Offset           = r.i32(p); p += 4
    AssetType        = r.i16(p); p += 2
    SceneObjectLevel = r.i16(p); p += 2
    LoadDistance     = r.f32(p); p += 4
    CustomLoadControlData = r.i32(p); p += 4
    return (StreamingAssetHeader(
        bounds, CustomLayerId, Offset, AssetType, SceneObjectLevel,
        LoadDistance, CustomLoadControlData,
    ), body_end - off)


def read_layer_header(r: Reader, off: int) -> tuple[StreamingLayerHeader, int]:
    """StreamingLayerHeader:
      [int32 bodyLen]
      [bool HasGameObjectInAssets]
      [bool HasCustomLayer]
      [int32 arrLen][StreamingAssetHeader x arrLen]
    """
    body_len = r.i32(off)
    body_end = off + 4 + body_len
    p = off + 4
    HasGameObjectInAssets = bool(r.u8(p)); p += 1
    HasCustomLayer        = bool(r.u8(p)); p += 1
    arr_len = r.i32(p); p += 4
    if arr_len < 0 or arr_len > 1_000_000:
        raise ValueError(f"invalid asset header array length: {arr_len}")
    headers: list[StreamingAssetHeader] = []
    for _ in range(arr_len):
        h, n = read_asset_header(r, p)
        headers.append(h)
        p += n
    return StreamingLayerHeader(HasGameObjectInAssets, HasCustomLayer, headers), body_end - off


# ---------- 文件级解析 ----------

def parse_native_array_of_layer_info(buf: bytes) -> list[StreamingLayerInfoHeader]:
    """background_info.bin 反序列化：NativeArray<StreamingLayerInfoHeader>。
    格式: [int32 length][LayerInfoHeader x length]"""
    r = Reader(buf)
    length = r.i32(0)
    if length <= 0 or length > 1_000_000:
        raise ValueError(f"invalid NativeArray length: {length}")
    p = 4
    out: list[StreamingLayerInfoHeader] = []
    for _ in range(length):
        item, n = read_layer_info_header(r, p)
        out.append(item)
        p += n
    return out


def parse_dict_of_layer_info(buf: bytes) -> dict[int, list[StreamingLayerInfoHeader]]:
    """layer_block_XX_YY.bin 反序列化：Dictionary<int, NativeArray<StreamingLayerInfoHeader>>。
    格式: [int32 dictCount][[int32 key][int32 arrLen][LayerInfoHeader x arrLen]] x dictCount"""
    r = Reader(buf)
    dict_count = r.i32(0)
    if dict_count <= 0 or dict_count > 1_000_000:
        raise ValueError(f"invalid dict count: {dict_count}")
    p = 4
    out: dict[int, list[StreamingLayerInfoHeader]] = {}
    for _ in range(dict_count):
        key = r.i32(p); p += 4
        arr_len = r.i32(p); p += 4
        if arr_len < 0 or arr_len > 1_000_000:
            raise ValueError(f"invalid inner array length: {arr_len}")
        items: list[StreamingLayerInfoHeader] = []
        for _ in range(arr_len):
            item, n = read_layer_info_header(r, p)
            items.append(item)
            p += n
        out[key] = items
    return out


def decode_chunk_index(chunk_index: int) -> tuple[int, int]:
    """chunkIndex = (sectorX << 16) | sectorY；分量是带符号 int16。"""
    u = chunk_index & 0xFFFFFFFF
    sx_u = (u >> 16) & 0xFFFF
    sy_u = u & 0xFFFF
    sx = sx_u - 0x10000 if sx_u & 0x8000 else sx_u
    sy = sy_u - 0x10000 if sy_u & 0x8000 else sy_u
    return sx, sy


# ---------- 业务工具 ----------

def resolve_scene_dir(scene_arg: str) -> Path:
    p = Path(scene_arg)
    if p.is_dir():
        if (p / "ReleaseData").is_dir():
            return p
        if p.name.endswith("BlockV2~"):
            return p.parent.parent.parent
    if p.is_file() and p.suffix == ".prefab":
        return p.parent
    candidate = SCENE_BASE / scene_arg
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(f"无法定位场景目录: {scene_arg}")


def get_block_dir(scene_dir: Path) -> Path:
    return scene_dir / "ReleaseData" / "Silk" / "BlockV2~"


def find_streaming_prefab(scene_dir: Path) -> Optional[Path]:
    for f in scene_dir.glob("*_streaming.prefab"):
        return f
    return None


def parse_layer_mapping(streaming_prefab: Path) -> list[tuple[int, str]]:
    """从 _streaming.prefab YAML 解析 (layerId, layerName)。"""
    text = streaming_prefab.read_text(encoding="utf-8", errors="replace")
    names: list[str] = []
    in_names = False
    hex_str: Optional[str] = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("AvailableCustomLayerNames:"):
            in_names = True
            continue
        if in_names:
            if s.startswith("- "):
                names.append(s[2:])
                continue
            in_names = False
        if s.startswith("AvailableCustomLayerIds:"):
            hex_str = s.split(":", 1)[1].strip()
            break
    if not hex_str or not names:
        return []
    raw = bytes.fromhex(hex_str)
    ids = [struct.unpack_from("<i", raw, i)[0] for i in range(0, len(raw), 4)]
    return list(zip(ids, names))


def load_info_file(info_path: Path):
    """返回 (kind, data) 其中 kind 为 'background'|'chunk'。"""
    buf = info_path.read_bytes()
    if info_path.name.lower().startswith("background_info"):
        return ("background", parse_native_array_of_layer_info(buf))
    return ("chunk", parse_dict_of_layer_info(buf))


def read_layer_header_from_block(block_buf: bytes, info: StreamingLayerInfoHeader) -> StreamingLayerHeader:
    r = Reader(block_buf)
    start = info.BinaryHeader.file_offset + info.InsideOffset
    if start < 0 or start >= r.size:
        raise ValueError(f"LayerHeader 起点 {start} 越界，block size={r.size}")
    lh, _ = read_layer_header(r, start)
    return lh


def block_path_for_chunk(block_dir: Path, sx: int, sy: int) -> Optional[Path]:
    """返回 chunk 对应的 block 文件路径（含 _patch_N 兼容）。"""
    candidates: list[Path] = [block_dir / f"block_{sx:02d}_{sy:02d}.bin"]
    candidates += sorted(block_dir.glob(f"block_{sx:02d}_{sy:02d}_patch_*.bin"))
    for c in candidates:
        if c.is_file():
            return c
    return None


# ---------- 子命令 ----------

def cmd_list_layers(args) -> int:
    scene_dir = resolve_scene_dir(args.scene)
    prefab = find_streaming_prefab(scene_dir)
    if prefab is None:
        print(f"[!] 未找到 *_streaming.prefab on {scene_dir}")
        return 1
    mapping = parse_layer_mapping(prefab)
    print(f"场景: {scene_dir.name}")
    print(f"streaming prefab: {prefab.relative_to(PROJECT_ROOT)}")
    print(f"动态图层共 {len(mapping)} 个：\n")
    print(f"{'idx':>3}  {'layerId':>13}  {'layer name':<30}")
    print("-" * 55)
    for idx, (lid, name) in enumerate(mapping):
        print(f"{idx:>3}  {lid:>13}  {name:<30}")
    return 0


def cmd_inspect(args) -> int:
    info_path = Path(args.info)
    block_path = Path(args.block)
    if not info_path.is_file():
        print(f"[!] info 文件不存在: {info_path}")
        return 1
    if not block_path.is_file():
        print(f"[!] block 文件不存在: {block_path}")
        return 1

    kind, data = load_info_file(info_path)
    block_buf = block_path.read_bytes()
    print(f"info:  {info_path}  ({info_path.stat().st_size} bytes)")
    print(f"block: {block_path}  ({len(block_buf)} bytes)")
    print(f"kind:  {kind}\n")

    if kind == "background":
        infos: list[StreamingLayerInfoHeader] = data
        print(f"Background LayerCount: {len(infos)}\n")
        _dump_layer_infos("background", infos, block_buf, args.full)
    else:
        layer_map: dict[int, list[StreamingLayerInfoHeader]] = data
        print(f"ChunkCount: {len(layer_map)}")
        if args.chunk is not None:
            keep = set()
            for token in args.chunk:
                keep.add(int(token, 0))
            layer_map = {k: v for k, v in layer_map.items() if k in keep}
        for chunk_index, infos in layer_map.items():
            sx, sy = decode_chunk_index(chunk_index)
            print(f"\n=== Chunk {chunk_index}  sector=({sx},{sy})  layers={len(infos)} ===")
            _dump_layer_infos(f"chunk:{chunk_index}", infos, block_buf, args.full)
    return 0


def _dump_layer_infos(owner: str, infos: list[StreamingLayerInfoHeader],
                       block_buf: bytes, full: bool) -> None:
    for i, info in enumerate(infos):
        bh = info.BinaryHeader
        print(
            f"  Layer[{i}] Owner={owner} Region={info.RegionId} UniqueId={info.UniqueId}\n"
            f"    LoadDist={info.LoadDistance:.1f} UnloadDist={info.UnloadDistance:.1f}"
            f" Sector={info.SectorIndex} HLOD={info.HLODLevel} YSplit={info.YSplitId}\n"
            f"    BinaryHeader: FileOffset={bh.file_offset} FileSize={bh.file_size}"
            f" InsideOffset={info.InsideOffset} ResId={bh.resource_id}"
        )
        try:
            lh = read_layer_header_from_block(block_buf, info)
        except Exception as e:
            print(f"    [!] LayerHeader 读取失败: {e}")
            continue
        print(
            f"    LayerHeader: HasGO={lh.HasGameObjectInAssets} "
            f"HasCustomLayer={lh.HasCustomLayer} AssetCount={len(lh.AssetHeaders)}"
        )
        types = Counter(a.AssetType for a in lh.AssetHeaders)
        layers = Counter(a.CustomLayerId for a in lh.AssetHeaders)
        sols = Counter(a.SceneObjectLevel for a in lh.AssetHeaders)
        print("    AssetTypes=" + ", ".join(
            f"{ASSET_TYPE_NAMES.get(t, t)}:{c}" for t, c in types.items()))
        print("    CustomLayers=" + ", ".join(
            f"{lid}:{c}" for lid, c in layers.items()))
        print("    SceneObjectLevels=" + ", ".join(
            f"{SCENE_OBJECT_LEVEL_NAMES.get(s, s)}:{c}" for s, c in sols.items()))
        if full:
            for j, a in enumerate(lh.AssetHeaders):
                print(
                    f"      Asset[{j}] CustomLayerId={a.CustomLayerId} "
                    f"Type={ASSET_TYPE_NAMES.get(a.AssetType, a.AssetType)} "
                    f"SOL={SCENE_OBJECT_LEVEL_NAMES.get(a.SceneObjectLevel, a.SceneObjectLevel)} "
                    f"LoadDist={a.LoadDistance:.1f} CLCD={a.CustomLoadControlData} "
                    f"Center=({a.Bounds.cx:.1f},{a.Bounds.cy:.1f},{a.Bounds.cz:.1f}) "
                    f"Size=({a.Bounds.sx:.1f},{a.Bounds.sy:.1f},{a.Bounds.sz:.1f})"
                )


def cmd_query_layer(args) -> int:
    """跨整个场景查询 CustomLayerId 命中的 asset。"""
    scene_dir = resolve_scene_dir(args.scene)
    prefab = find_streaming_prefab(scene_dir)
    mapping = parse_layer_mapping(prefab) if prefab else []

    target_id: Optional[int] = None
    target_name = "(unknown)"
    try:
        candidate = int(args.layer)
        for lid, name in mapping:
            if lid == candidate:
                target_id, target_name = lid, name
                break
        if target_id is None:
            target_id = candidate
    except ValueError:
        for lid, name in mapping:
            if name.lower() == args.layer.lower():
                target_id, target_name = lid, name
                break
        if target_id is None:
            print(f"[!] 未识别 layer 参数 {args.layer}")
            print("可用图层：")
            for lid, name in mapping:
                print(f"  {lid:>13}  {name}")
            return 1

    block_dir = get_block_dir(scene_dir)
    if not block_dir.is_dir():
        print(f"[!] BlockV2~ 目录不存在: {block_dir}")
        return 1

    print(f"场景: {scene_dir.name}")
    print(f"图层: layerId={target_id} name={target_name}\n")

    bg_info = block_dir / "background_info.bin"
    info_files = sorted(block_dir.glob("layer_block_*.bin"))
    if bg_info.is_file():
        info_files.insert(0, bg_info)
    if not info_files:
        print("[!] 未找到任何 info 文件")
        return 0

    total_hits = 0
    for info_path in info_files:
        try:
            kind, data = load_info_file(info_path)
        except Exception as e:
            print(f"  [!] 解析 {info_path.name} 失败: {e}")
            continue

        if kind == "background":
            bg_block = block_dir / "background.bin"
            if not bg_block.is_file():
                continue
            block_buf = bg_block.read_bytes()
            total_hits += _scan_layer_infos(
                target_id, "background", data, bg_block.name, block_buf)
        else:
            # 按 chunk 分组对应到各自 block_XX_YY.bin
            chunk_to_block: dict[int, Path] = {}
            for chunk_index in data.keys():
                sx, sy = decode_chunk_index(chunk_index)
                bp = block_path_for_chunk(block_dir, sx, sy)
                if bp is not None:
                    chunk_to_block[chunk_index] = bp
            block_cache: dict[Path, bytes] = {}
            for chunk_index, infos in data.items():
                bp = chunk_to_block.get(chunk_index)
                if bp is None:
                    continue
                if bp not in block_cache:
                    block_cache[bp] = bp.read_bytes()
                sx, sy = decode_chunk_index(chunk_index)
                total_hits += _scan_layer_infos(
                    target_id, f"chunk:{chunk_index}({sx},{sy})",
                    infos, bp.name, block_cache[bp])

    print(f"\n共命中 {total_hits} 个 StreamingAssetHeader。")
    print("CLCD=1 表示该 asset 由 VirtualGeometry 替代，开启 VG 时会被运行时过滤掉。")
    return 0


def _scan_layer_infos(target_id: int, owner_label: str,
                       infos: list[StreamingLayerInfoHeader],
                       block_name: str, block_buf: bytes) -> int:
    hits = 0
    for li, info in enumerate(infos):
        try:
            lh = read_layer_header_from_block(block_buf, info)
        except Exception:
            continue
        matched = [a for a in lh.AssetHeaders if a.CustomLayerId == target_id]
        if not matched:
            continue
        for j, a in enumerate(matched):
            hits += 1
            print(
                f"  [{owner_label}] LayerInfo#{li} Region={info.RegionId} "
                f"block={block_name}\n"
                f"    Asset#{j}: Type={ASSET_TYPE_NAMES.get(a.AssetType, a.AssetType)} "
                f"SOL={SCENE_OBJECT_LEVEL_NAMES.get(a.SceneObjectLevel, a.SceneObjectLevel)} "
                f"LoadDist={a.LoadDistance:.1f} CLCD={a.CustomLoadControlData} "
                f"Center=({a.Bounds.cx:.1f},{a.Bounds.cy:.1f},{a.Bounds.cz:.1f})"
            )
    return hits


# ---------- 入口 ----------

def main() -> int:
    p = argparse.ArgumentParser(prog="silk-streaming-inspect")
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list-layers", help="列出场景所有动态图层")
    p1.add_argument("scene", help="场景名 / streaming.prefab 路径 / 场景目录")
    p1.set_defaults(func=cmd_list_layers)

    p2 = sub.add_parser("inspect", help="解析 info+block 配对，输出每个 layer 的详情")
    p2.add_argument("info", help="layer info 文件路径（background_info.bin 或 layer_block_XX_YY.bin）")
    p2.add_argument("block", help="对应 block 文件路径（background.bin 或 block_XX_YY.bin）")
    p2.add_argument("--full", action="store_true", help="列出每个 AssetHeader 详情")
    p2.add_argument("--chunk", nargs="+", help="只输出指定 chunkIndex（int，可多个）")
    p2.set_defaults(func=cmd_inspect)

    p3 = sub.add_parser("query-layer", help="跨场景所有 chunk 查询 CustomLayerId 命中的 asset")
    p3.add_argument("scene", help="场景名 / streaming.prefab 路径 / 场景目录")
    p3.add_argument("layer", help="layerId 或 layer 名")
    p3.set_defaults(func=cmd_query_layer)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
