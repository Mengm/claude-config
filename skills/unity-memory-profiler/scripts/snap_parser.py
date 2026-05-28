"""
Unity Memory Profiler .snap file parser and analyzer.
Standalone script - no external dependencies beyond Python stdlib.

Usage:
    python snap_parser.py <snap_file_or_directory> [--output-dir <dir>] [--prefix <filter>]

Modes:
    Single file:  python snap_parser.py path/to/file.snap
    Batch:        python snap_parser.py path/to/directory --prefix T3Project_2026-03-06
    Timeline:     python snap_parser.py path/to/directory --prefix T3Project_2026-03-06 --timeline
"""
import struct
import sys
import os
import json
import argparse
from collections import defaultdict

# ============================================================
# Constants
# ============================================================
HEAD_SIGNATURE = 0xAEABCDCD
DIRECTORY_SIGNATURE = 0xCDCDAEAB
TAIL_SIGNATURE = 0xABCDCDAE

ENTRY_TYPES = [
    ("Metadata_Version", "SingleValue"),
    ("Metadata_RecordDate", "SingleValue"),
    ("Metadata_UserMetadata", "SingleValue"),
    ("Metadata_CaptureFlags", "SingleValue"),
    ("Metadata_VirtualMachineInformation", "SingleValue"),
    ("NativeTypes_Name", "DynamicSizeArray"),
    ("NativeTypes_NativeBaseTypeArrayIndex", "ConstantSizeArray"),
    ("NativeObjects_NativeTypeArrayIndex", "ConstantSizeArray"),
    ("NativeObjects_HideFlags", "ConstantSizeArray"),
    ("NativeObjects_Flags", "ConstantSizeArray"),
    ("NativeObjects_InstanceId", "ConstantSizeArray"),
    ("NativeObjects_Name", "DynamicSizeArray"),
    ("NativeObjects_NativeObjectAddress", "ConstantSizeArray"),
    ("NativeObjects_Size", "ConstantSizeArray"),
    ("NativeObjects_RootReferenceId", "ConstantSizeArray"),
    ("GCHandles_Target", "ConstantSizeArray"),
    ("Connections_From", "ConstantSizeArray"),
    ("Connections_To", "ConstantSizeArray"),
    ("ManagedHeapSections_StartAddress", "ConstantSizeArray"),
    ("ManagedHeapSections_Bytes", "DynamicSizeArray"),
    ("ManagedStacks_StartAddress", "ConstantSizeArray"),
    ("ManagedStacks_Bytes", "DynamicSizeArray"),
    ("TypeDescriptions_Flags", "ConstantSizeArray"),
    ("TypeDescriptions_Name", "DynamicSizeArray"),
    ("TypeDescriptions_Assembly", "DynamicSizeArray"),
    ("TypeDescriptions_FieldIndices", "DynamicSizeArray"),
    ("TypeDescriptions_StaticFieldBytes", "DynamicSizeArray"),
    ("TypeDescriptions_BaseOrElementTypeIndex", "ConstantSizeArray"),
    ("TypeDescriptions_Size", "ConstantSizeArray"),
    ("TypeDescriptions_TypeInfoAddress", "ConstantSizeArray"),
    ("TypeDescriptions_TypeIndex", "ConstantSizeArray"),
    ("FieldDescriptions_Offset", "ConstantSizeArray"),
    ("FieldDescriptions_TypeIndex", "ConstantSizeArray"),
    ("FieldDescriptions_Name", "DynamicSizeArray"),
    ("FieldDescriptions_IsStatic", "ConstantSizeArray"),
    ("NativeRootReferences_Id", "ConstantSizeArray"),
    ("NativeRootReferences_AreaName", "DynamicSizeArray"),
    ("NativeRootReferences_ObjectName", "DynamicSizeArray"),
    ("NativeRootReferences_AccumulatedSize", "ConstantSizeArray"),
    ("NativeAllocations_MemoryRegionIndex", "ConstantSizeArray"),
    ("NativeAllocations_RootReferenceId", "ConstantSizeArray"),
    ("NativeAllocations_AllocationSiteId", "ConstantSizeArray"),
    ("NativeAllocations_Address", "ConstantSizeArray"),
    ("NativeAllocations_Size", "ConstantSizeArray"),
    ("NativeAllocations_OverheadSize", "ConstantSizeArray"),
    ("NativeAllocations_PaddingSize", "ConstantSizeArray"),
    ("NativeMemoryRegions_Name", "DynamicSizeArray"),
    ("NativeMemoryRegions_ParentIndex", "ConstantSizeArray"),
    ("NativeMemoryRegions_AddressBase", "ConstantSizeArray"),
    ("NativeMemoryRegions_AddressSize", "ConstantSizeArray"),
    ("NativeMemoryRegions_FirstAllocationIndex", "ConstantSizeArray"),
    ("NativeMemoryRegions_NumAllocations", "ConstantSizeArray"),
    ("NativeMemoryLabels_Name", "DynamicSizeArray"),
    ("NativeAllocationSites_Id", "ConstantSizeArray"),
    ("NativeAllocationSites_MemoryLabelIndex", "ConstantSizeArray"),
    ("NativeAllocationSites_CallstackSymbols", "DynamicSizeArray"),
    ("NativeCallstackSymbol_Symbol", "ConstantSizeArray"),
    ("NativeCallstackSymbol_ReadableStackTrace", "DynamicSizeArray"),
    ("NativeObjects_GCHandleIndex", "ConstantSizeArray"),
    ("ProfileTarget_Info", "SingleValue"),
    ("ProfileTarget_MemoryStats", "SingleValue"),
    ("NativeMemoryLabels_Size", "ConstantSizeArray"),
    ("SceneObjects_Name", "DynamicSizeArray"),
    ("SceneObjects_Path", "DynamicSizeArray"),
    ("SceneObjects_AssetPath", "DynamicSizeArray"),
    ("SceneObjects_BuildIndex", "ConstantSizeArray"),
    ("SceneObjects_RootIdCounts", "ConstantSizeArray"),
    ("SceneObjects_RootIdOffsets", "ConstantSizeArray"),
    ("SceneObjects_RootIds", "ConstantSizeArray"),
    ("NativeMemoryLabels_AllocatorIdentifier", "ConstantSizeArray"),
    ("NativeGfxResourceReferences_Id", "ConstantSizeArray"),
    ("NativeGfxResourceReferences_Size", "ConstantSizeArray"),
    ("NativeGfxResourceReferences_RootId", "ConstantSizeArray"),
    ("NativeAllocatorInfo_AllocatorName", "DynamicSizeArray"),
    ("NativeAllocatorInfo_Identifier", "ConstantSizeArray"),
    ("NativeAllocatorInfo_UsedSize", "ConstantSizeArray"),
    ("NativeAllocatorInfo_ReservedSize", "ConstantSizeArray"),
    ("NativeAllocatorInfo_OverheadSize", "ConstantSizeArray"),
    ("NativeAllocatorInfo_PeakUsedSize", "ConstantSizeArray"),
    ("NativeAllocatorInfo_AllocationCount", "ConstantSizeArray"),
    ("NativeAllocatorInfo_Flags", "ConstantSizeArray"),
    ("ObjectMetaData_MetaDataBufferIndex", "ConstantSizeArray"),
    ("ObjectMetaData_MetaDataBuffer", "DynamicSizeArray"),
    ("SystemMemoryRegions_Address", "ConstantSizeArray"),
    ("SystemMemoryRegions_Size", "ConstantSizeArray"),
    ("SystemMemoryRegions_ResidentSize", "ConstantSizeArray"),
    ("SystemMemoryRegions_Type", "ConstantSizeArray"),
    ("SystemMemoryRegions_Name", "DynamicSizeArray"),
]

ENTRY_NAME_TO_INDEX = {name: i for i, (name, _) in enumerate(ENTRY_TYPES)}

# Resource categories of interest
RESOURCE_CATEGORIES = ['Texture2D', 'RenderTexture', 'Mesh', 'AnimationClip',
                       'Cubemap', 'Shader', 'Font', 'Material', 'AudioClip']


# ============================================================
# Binary format classes
# ============================================================
class Block:
    def __init__(self, f, offset):
        f.seek(offset)
        self.chunk_size = struct.unpack('<Q', f.read(8))[0]
        self.total_bytes = struct.unpack('<Q', f.read(8))[0]
        num_chunks = (self.total_bytes + self.chunk_size - 1) // self.chunk_size if self.chunk_size > 0 else 0
        self.chunk_offsets = []
        for _ in range(num_chunks):
            self.chunk_offsets.append(struct.unpack('<Q', f.read(8))[0])

    def get_data(self, f, start_offset, length):
        result = bytearray()
        cur = 0
        while cur < length:
            block_offset = start_offset + cur
            chunk_idx = block_offset // self.chunk_size
            chunk_local = block_offset % self.chunk_size
            chunk_sz = min(self.chunk_size, self.total_bytes - self.chunk_size * chunk_idx)
            read_sz = min(chunk_sz - chunk_local, length - cur)
            if read_sz == 0:
                raise ValueError("Corrupted file format")
            f.seek(self.chunk_offsets[chunk_idx] + chunk_local)
            result.extend(f.read(read_sz))
            cur += read_sz
        return bytes(result)


class SingleValueChapter:
    def __init__(self, f):
        self.block_index = struct.unpack('<I', f.read(4))[0]
        self.entry_size = struct.unpack('<I', f.read(4))[0]
        self.block_offset = struct.unpack('<Q', f.read(8))[0]

    @property
    def num_entries(self):
        return 1

    def get_size(self, idx):
        return self.entry_size

    def get_offset(self, idx):
        return self.block_offset


class ConstantSizeArrayChapter:
    def __init__(self, f):
        self.block_index = struct.unpack('<I', f.read(4))[0]
        self.entry_size = struct.unpack('<I', f.read(4))[0]
        self._num_entries = struct.unpack('<I', f.read(4))[0]

    @property
    def num_entries(self):
        return self._num_entries

    def get_size(self, idx):
        return self.entry_size

    def get_offset(self, idx):
        return self.entry_size * idx


class DynamicSizeArrayChapter:
    def __init__(self, f):
        self.block_index = struct.unpack('<I', f.read(4))[0]
        self._num_entries = struct.unpack('<I', f.read(4))[0]
        self.block_offsets = []
        for _ in range(self._num_entries + 1):
            self.block_offsets.append(struct.unpack('<Q', f.read(8))[0])

    @property
    def num_entries(self):
        return self._num_entries

    def get_size(self, idx):
        return self.block_offsets[idx + 1] - self.block_offsets[idx]

    def get_offset(self, idx):
        return self.block_offsets[idx]


def read_chapter(f):
    fmt = struct.unpack('<H', f.read(2))[0]
    if fmt == 1:
        return SingleValueChapter(f)
    elif fmt == 2:
        return ConstantSizeArrayChapter(f)
    elif fmt == 3:
        return DynamicSizeArrayChapter(f)
    else:
        raise ValueError(f"Unknown chapter format: {fmt}")


# ============================================================
# SnapReader - core parser
# ============================================================
class SnapReader:
    def __init__(self, filepath):
        self.filepath = filepath
        self.f = open(filepath, 'rb')
        self.chapters = {}
        self.blocks = []
        self._build()

    def _build(self):
        f = self.f
        f.seek(0)
        head = struct.unpack('<I', f.read(4))[0]
        assert head == HEAD_SIGNATURE, f"Bad head signature: {head:#x}"

        f.seek(-4, 2)
        tail = struct.unpack('<I', f.read(4))[0]
        assert tail == TAIL_SIGNATURE, f"Bad tail signature: {tail:#x}"

        f.seek(-4 - 8, 2)
        chapter_offset = struct.unpack('<Q', f.read(8))[0]

        f.seek(chapter_offset)
        dir_sig = struct.unpack('<I', f.read(4))[0]
        assert dir_sig == DIRECTORY_SIGNATURE, f"Bad directory signature: {dir_sig:#x}"

        chap_ver = struct.unpack('<I', f.read(4))[0]
        block_section_pos = struct.unpack('<Q', f.read(8))[0]

        entry_type_count = struct.unpack('<I', f.read(4))[0]
        chapter_offsets = []
        for _ in range(entry_type_count):
            chapter_offsets.append(struct.unpack('<Q', f.read(8))[0])

        for i, off in enumerate(chapter_offsets):
            if off != 0:
                f.seek(off)
                self.chapters[i] = read_chapter(f)

        f.seek(block_section_pos)
        block_ver = struct.unpack('<I', f.read(4))[0]
        num_blocks = struct.unpack('<I', f.read(4))[0]
        block_positions = []
        for _ in range(num_blocks):
            block_positions.append(struct.unpack('<Q', f.read(8))[0])
        for pos in block_positions:
            self.blocks.append(Block(f, pos))

    def get_num_entries(self, entry_name):
        idx = ENTRY_NAME_TO_INDEX.get(entry_name)
        if idx is None or idx not in self.chapters:
            return 0
        return self.chapters[idx].num_entries

    def read_entry_raw(self, entry_name, entry_index):
        idx = ENTRY_NAME_TO_INDEX[entry_name]
        ch = self.chapters[idx]
        block = self.blocks[ch.block_index]
        offset = ch.get_offset(entry_index)
        size = ch.get_size(entry_index)
        if size == 0:
            return b''
        return block.get_data(self.f, offset, size)

    def read_all_entries_raw(self, entry_name):
        idx = ENTRY_NAME_TO_INDEX.get(entry_name)
        if idx is None or idx not in self.chapters:
            return []
        ch = self.chapters[idx]
        block = self.blocks[ch.block_index]
        results = []
        for i in range(ch.num_entries):
            offset = ch.get_offset(i)
            size = ch.get_size(i)
            if size == 0:
                results.append(b'')
            else:
                results.append(block.get_data(self.f, offset, size))
        return results

    def read_strings(self, entry_name):
        raw = self.read_all_entries_raw(entry_name)
        return [r.decode('utf-8', errors='replace') for r in raw]

    def read_uint32_array(self, entry_name):
        idx = ENTRY_NAME_TO_INDEX.get(entry_name)
        if idx is None or idx not in self.chapters:
            return []
        ch = self.chapters[idx]
        block = self.blocks[ch.block_index]
        n = ch.num_entries
        if n == 0:
            return []
        data = block.get_data(self.f, ch.get_offset(0), ch.entry_size * n)
        fmt = f'<{n}I' if ch.entry_size == 4 else f'<{n}i'
        return list(struct.unpack(fmt, data))

    def read_int32_array(self, entry_name):
        idx = ENTRY_NAME_TO_INDEX.get(entry_name)
        if idx is None or idx not in self.chapters:
            return []
        ch = self.chapters[idx]
        block = self.blocks[ch.block_index]
        n = ch.num_entries
        if n == 0:
            return []
        data = block.get_data(self.f, ch.get_offset(0), ch.entry_size * n)
        return list(struct.unpack(f'<{n}i', data))

    def read_uint64_array(self, entry_name):
        idx = ENTRY_NAME_TO_INDEX.get(entry_name)
        if idx is None or idx not in self.chapters:
            return []
        ch = self.chapters[idx]
        block = self.blocks[ch.block_index]
        n = ch.num_entries
        if n == 0:
            return []
        data = block.get_data(self.f, ch.get_offset(0), ch.entry_size * n)
        return list(struct.unpack(f'<{n}Q', data))

    def read_auto_uint_array(self, entry_name):
        """Read unsigned int array, auto-detecting 4 or 8 byte entries."""
        idx = ENTRY_NAME_TO_INDEX.get(entry_name)
        if idx is None or idx not in self.chapters:
            return []
        ch = self.chapters[idx]
        block = self.blocks[ch.block_index]
        n = ch.num_entries
        if n == 0:
            return []
        data = block.get_data(self.f, ch.get_offset(0), ch.entry_size * n)
        if ch.entry_size == 8:
            return list(struct.unpack(f'<{n}Q', data))
        elif ch.entry_size == 4:
            return list(struct.unpack(f'<{n}I', data))
        elif ch.entry_size == 2:
            return list(struct.unpack(f'<{n}H', data))
        else:
            return list(struct.unpack(f'<{n}B', data))

    def close(self):
        self.f.close()


# ============================================================
# Helpers
# ============================================================
def fmt_size(b):
    if b >= 1024**3:
        return f"{b/1024**3:.2f} GB"
    elif b >= 1024**2:
        return f"{b/1024**2:.2f} MB"
    elif b >= 1024:
        return f"{b/1024:.2f} KB"
    return f"{b:.0f} B"


def guess_origin(name):
    """Heuristic: map resource name to category."""
    nl = name.lower()
    if any(k in nl for k in ['ui_', 'ui/', 'atlas', 'uiatlas', 'font', 'emoji']):
        return 'UI'
    if any(k in nl for k in ['fx_', 'vfx/', 'particle', 'effect']):
        return 'VFX'
    if any(k in nl for k in ['env_', 'terrain', 'building', 'tree', 'rock', 'grass']):
        return 'Environment'
    if any(k in nl for k in ['char_', 'hero_', 'monster_', 'npc_', 'avatar']):
        return 'Character'
    if any(k in nl for k in ['bgm_', 'sfx_', 'sound', 'audio', 'music']):
        return 'Audio'
    if any(k in nl for k in ['shader', 'postprocess', 'bloom', 'tonemapping']):
        return 'Shader/PostProcess'
    return 'Other'


# ============================================================
# Data extraction
# ============================================================
def extract_snap_data(filepath):
    """Extract structured data from a single .snap file."""
    snap = SnapReader(filepath)
    d = {}
    d['filepath'] = filepath
    d['filename'] = os.path.basename(filepath)
    ts = os.path.splitext(d['filename'])[0]
    parts = ts.split('_')
    d['timestamp'] = '_'.join(parts[1:]) if len(parts) >= 3 else ts
    d['time_short'] = parts[-1] if parts else ts

    # Metadata
    try:
        ver_data = snap.read_entry_raw("Metadata_Version", 0)
        d['version'] = struct.unpack('<I', ver_data[:4])[0] if len(ver_data) >= 4 else 0
    except:
        d['version'] = 0
    try:
        d['record_date'] = snap.read_entry_raw("Metadata_RecordDate", 0).decode('utf-8', errors='replace')
    except:
        d['record_date'] = ''

    # Scenes
    scene_names = snap.read_strings("SceneObjects_Name")
    d['scenes'] = [s for s in scene_names if s != 'DontDestroyOnLoad']
    d['scene_str'] = ', '.join(d['scenes']) if d['scenes'] else '(none)'

    # Native types
    type_names = snap.read_strings("NativeTypes_Name")

    # Native objects
    obj_names = snap.read_strings("NativeObjects_Name")
    obj_types_i = snap.read_int32_array("NativeObjects_NativeTypeArrayIndex")
    obj_sizes = snap.read_auto_uint_array("NativeObjects_Size")
    obj_ids = snap.read_auto_uint_array("NativeObjects_InstanceId")

    n = min(len(obj_names), len(obj_sizes))
    objects = []
    for i in range(n):
        tname = ''
        if i < len(obj_types_i) and 0 <= obj_types_i[i] < len(type_names):
            tname = type_names[obj_types_i[i]]
        iid = obj_ids[i] if i < len(obj_ids) else 0
        objects.append({
            'name': obj_names[i],
            'size': obj_sizes[i],
            'type': tname,
            'instance_id': iid,
        })
    d['objects'] = objects
    d['total_native'] = sum(o['size'] for o in objects)

    # Type aggregation
    type_agg = defaultdict(lambda: {'count': 0, 'size': 0})
    for o in objects:
        type_agg[o['type']]['count'] += 1
        type_agg[o['type']]['size'] += o['size']
    d['type_agg'] = dict(type_agg)

    # Category totals
    cat_totals = {}
    cat_counts = {}
    for cat in RESOURCE_CATEGORIES:
        items = [o for o in objects if o['type'] == cat]
        cat_totals[cat] = sum(o['size'] for o in items)
        cat_counts[cat] = len(items)
    d['cat_totals'] = cat_totals
    d['cat_counts'] = cat_counts

    # GFX resources
    gfx_sizes = snap.read_auto_uint_array("NativeGfxResourceReferences_Size")
    d['gfx_total'] = sum(gfx_sizes) if gfx_sizes else 0
    d['gfx_count'] = len(gfx_sizes)

    # Duplicates
    dup_map = defaultdict(list)
    for o in objects:
        if o['name']:
            key = (o['name'], o['type'])
            dup_map[key].append(o)
    d['duplicates'] = {k: v for k, v in dup_map.items() if len(v) > 1}

    # Memory labels
    label_names = snap.read_strings("NativeMemoryLabels_Name")
    label_sizes = snap.read_auto_uint_array("NativeMemoryLabels_Size")
    labels = []
    for i in range(min(len(label_names), len(label_sizes))):
        if label_sizes[i] > 0:
            labels.append({'name': label_names[i], 'size': label_sizes[i]})
    labels.sort(key=lambda x: x['size'], reverse=True)
    d['memory_labels'] = labels

    snap.close()
    return d


# ============================================================
# Report generators
# ============================================================
def generate_individual_md(data):
    """Generate individual snapshot report as markdown string."""
    L = []
    a = L.append
    a(f"# {data['filename']}")
    a("")
    a(f"- Record date: {data.get('record_date', 'N/A')}")
    a(f"- Scenes: {data['scene_str']}")
    a(f"- Native objects: {len(data['objects'])}")
    a(f"- Native total: {fmt_size(data['total_native'])}")
    a(f"- GFX VRAM: {fmt_size(data['gfx_total'])} ({data['gfx_count']} refs)")
    a("")

    # Category breakdown
    a("## Resource Categories")
    a("")
    a("| Category | Count | Size |")
    a("|----------|-------|------|")
    for cat in RESOURCE_CATEGORIES:
        cnt = data['cat_counts'].get(cat, 0)
        sz = data['cat_totals'].get(cat, 0)
        if cnt > 0:
            a(f"| {cat} | {cnt} | {fmt_size(sz)} |")
    a("")

    # Top 50 objects
    sorted_objs = sorted(data['objects'], key=lambda x: x['size'], reverse=True)[:50]
    a("## Top 50 Objects by Size")
    a("")
    a("| # | Name | Type | Size |")
    a("|---|------|------|------|")
    for i, o in enumerate(sorted_objs, 1):
        name = o['name'][:60] if o['name'] else '(unnamed)'
        a(f"| {i} | {name} | {o['type']} | {fmt_size(o['size'])} |")
    a("")

    # Type aggregation
    sorted_types = sorted(data['type_agg'].items(), key=lambda x: x[1]['size'], reverse=True)[:30]
    a("## Memory by Type (Top 30)")
    a("")
    a("| Type | Count | Total Size |")
    a("|------|-------|------------|")
    for tname, info in sorted_types:
        a(f"| {tname} | {info['count']} | {fmt_size(info['size'])} |")
    a("")

    # Duplicates
    if data['duplicates']:
        sorted_dups = sorted(data['duplicates'].items(), key=lambda x: sum(o['size'] for o in x[1]), reverse=True)[:20]
        a("## Duplicate Objects (Top 20)")
        a("")
        a("| Name | Type | Count | Total Size |")
        a("|------|------|-------|------------|")
        for (name, ttype), objs in sorted_dups:
            total = sum(o['size'] for o in objs)
            dname = name[:50] if name else '(unnamed)'
            a(f"| {dname} | {ttype} | {len(objs)} | {fmt_size(total)} |")
        a("")

    # Memory labels
    if data['memory_labels']:
        a("## Memory Labels (Top 20)")
        a("")
        a("| Label | Size |")
        a("|-------|------|")
        for lab in data['memory_labels'][:20]:
            a(f"| {lab['name']} | {fmt_size(lab['size'])} |")
        a("")

    return '\n'.join(L)


def generate_comparative_md(all_data):
    """Generate comparative analysis across multiple snapshots."""
    L = []
    a = L.append
    a("# Memory Snapshot Comparative Analysis")
    a("")
    a(f"Total snapshots: {len(all_data)}")
    a("")

    # Overview table
    a("## Overview")
    a("")
    a("| # | Time | Scene | Native | GFX | Tex2D | RT | Mesh | Objects |")
    a("|---|------|-------|--------|-----|-------|----|------|---------|")
    for i, d in enumerate(all_data):
        scene = d['scene_str'][:40]
        a(f"| {i+1} | {d['time_short']} | {scene} | {fmt_size(d['total_native'])} | {fmt_size(d['gfx_total'])} | {fmt_size(d['cat_totals'].get('Texture2D',0))} | {fmt_size(d['cat_totals'].get('RenderTexture',0))} | {fmt_size(d['cat_totals'].get('Mesh',0))} | {len(d['objects'])} |")
    a("")

    # Growth analysis
    if len(all_data) >= 2:
        first, last = all_data[0], all_data[-1]
        a("## Growth Summary")
        a("")
        a("| Metric | First | Last | Delta |")
        a("|--------|-------|------|-------|")
        for label, key in [("Native Total", 'total_native'), ("GFX VRAM", 'gfx_total')]:
            v0 = first[key]
            v1 = last[key]
            delta = v1 - v0
            sign = '+' if delta >= 0 else ''
            a(f"| {label} | {fmt_size(v0)} | {fmt_size(v1)} | {sign}{fmt_size(delta)} |")
        for cat in RESOURCE_CATEGORIES:
            v0 = first['cat_totals'].get(cat, 0)
            v1 = last['cat_totals'].get(cat, 0)
            delta = v1 - v0
            if v0 > 0 or v1 > 0:
                sign = '+' if delta >= 0 else ''
                a(f"| {cat} | {fmt_size(v0)} | {fmt_size(v1)} | {sign}{fmt_size(delta)} |")
        a("")

    # Scene transitions
    a("## Scene Transitions")
    a("")
    for i in range(1, len(all_data)):
        prev_scenes = set(all_data[i-1]['scenes'])
        curr_scenes = set(all_data[i]['scenes'])
        if prev_scenes != curr_scenes:
            removed = prev_scenes - curr_scenes
            added = curr_scenes - prev_scenes
            nd = all_data[i]['total_native'] - all_data[i-1]['total_native']
            sign = '+' if nd >= 0 else ''
            a(f"- **#{i} -> #{i+1}**: removed={removed or 'none'}, added={added or 'none'}, native delta={sign}{fmt_size(nd)}")
    a("")

    return '\n'.join(L)


def generate_timeline_md(all_data):
    """Generate detailed leak timeline comparing consecutive snapshots."""
    L = []
    a = L.append
    a("# Detailed Leak Timeline")
    a("")

    for i in range(1, len(all_data)):
        prev = all_data[i-1]
        curr = all_data[i]
        a(f"## Transition #{i}: {prev['time_short']} -> {curr['time_short']}")
        a("")

        # Basic deltas
        nd = curr['total_native'] - prev['total_native']
        gd = curr['gfx_total'] - prev['gfx_total']
        a(f"- Native delta: {'+' if nd>=0 else ''}{fmt_size(nd)}")
        a(f"- GFX delta: {'+' if gd>=0 else ''}{fmt_size(gd)}")

        # Scene change
        prev_scenes = set(prev['scenes'])
        curr_scenes = set(curr['scenes'])
        if prev_scenes != curr_scenes:
            a(f"- Scene change: {prev['scene_str']} -> {curr['scene_str']}")

        # Diff objects
        prev_keys = {}
        for o in prev['objects']:
            k = (o['name'], o['type'])
            prev_keys[k] = o
        curr_keys = {}
        for o in curr['objects']:
            k = (o['name'], o['type'])
            curr_keys[k] = o

        new_objs = [(k, curr_keys[k]) for k in curr_keys if k not in prev_keys]
        removed_objs = [(k, prev_keys[k]) for k in prev_keys if k not in curr_keys]

        new_objs.sort(key=lambda x: x[1]['size'], reverse=True)
        removed_objs.sort(key=lambda x: x[1]['size'], reverse=True)

        new_total = sum(o['size'] for _, o in new_objs)
        removed_total = sum(o['size'] for _, o in removed_objs)

        a(f"- New objects: {len(new_objs)} (+{fmt_size(new_total)})")
        a(f"- Removed objects: {len(removed_objs)} (-{fmt_size(removed_total)})")
        a("")

        # Top new by type
        if new_objs:
            new_by_type = defaultdict(lambda: {'count': 0, 'size': 0})
            for (name, ttype), o in new_objs:
                new_by_type[ttype]['count'] += 1
                new_by_type[ttype]['size'] += o['size']
            sorted_new = sorted(new_by_type.items(), key=lambda x: x[1]['size'], reverse=True)[:10]
            a("### New Objects by Type")
            a("")
            a("| Type | Count | Size |")
            a("|------|-------|------|")
            for ttype, info in sorted_new:
                a(f"| {ttype} | {info['count']} | +{fmt_size(info['size'])} |")
            a("")

        # Top new by origin
        if new_objs:
            new_by_origin = defaultdict(lambda: {'count': 0, 'size': 0})
            for (name, ttype), o in new_objs:
                origin = guess_origin(name)
                new_by_origin[origin]['count'] += 1
                new_by_origin[origin]['size'] += o['size']
            sorted_orig = sorted(new_by_origin.items(), key=lambda x: x[1]['size'], reverse=True)
            a("### New Objects by Origin")
            a("")
            a("| Origin | Count | Size |")
            a("|--------|-------|------|")
            for origin, info in sorted_orig:
                a(f"| {origin} | {info['count']} | +{fmt_size(info['size'])} |")
            a("")

        # Scene transition leak check
        if prev_scenes != curr_scenes:
            removed_scenes = prev_scenes - curr_scenes
            if removed_scenes:
                a("### Scene Transition Leak Check")
                a("")
                # Objects that existed in previous snapshot and still exist, possibly from old scene
                surviving = [(k, curr_keys[k]) for k in curr_keys if k in prev_keys]
                a(f"Scenes removed: {removed_scenes}")
                a(f"Objects surviving from previous snapshot: {len(surviving)}")
                a("")

        a("---")
        a("")

    # Cumulative leak summary (first vs last)
    if len(all_data) >= 2:
        first = all_data[0]
        last = all_data[-1]
        first_keys = {(o['name'], o['type']): o for o in first['objects']}
        last_keys = {(o['name'], o['type']): o for o in last['objects']}
        leaked = [(k, last_keys[k]) for k in last_keys if k not in first_keys]
        leaked.sort(key=lambda x: x[1]['size'], reverse=True)

        a("## Cumulative Leak Summary (First vs Last)")
        a("")
        a(f"Objects in final snapshot not present in initial: {len(leaked)}")
        a(f"Total leaked size: {fmt_size(sum(o['size'] for _, o in leaked))}")
        a("")

        if leaked:
            a("### Top 30 Leaked Objects")
            a("")
            a("| # | Name | Type | Size | Origin |")
            a("|---|------|------|------|--------|")
            for i, ((name, ttype), o) in enumerate(leaked[:30], 1):
                dname = name[:50] if name else '(unnamed)'
                a(f"| {i} | {dname} | {ttype} | {fmt_size(o['size'])} | {guess_origin(name)} |")
            a("")

            # Leaked by type
            leak_by_type = defaultdict(lambda: {'count': 0, 'size': 0})
            for (name, ttype), o in leaked:
                leak_by_type[ttype]['count'] += 1
                leak_by_type[ttype]['size'] += o['size']
            sorted_leak = sorted(leak_by_type.items(), key=lambda x: x[1]['size'], reverse=True)[:15]
            a("### Leaked by Type")
            a("")
            a("| Type | Count | Total Size |")
            a("|------|-------|------------|")
            for ttype, info in sorted_leak:
                a(f"| {ttype} | {info['count']} | {fmt_size(info['size'])} |")
            a("")

    return '\n'.join(L)


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='Unity Memory Profiler .snap analyzer')
    parser.add_argument('path', help='.snap file or directory containing .snap files')
    parser.add_argument('--output-dir', '-o', default=None, help='Output directory for reports')
    parser.add_argument('--prefix', '-p', default=None, help='Filename prefix filter (e.g., T3Project_2026-03-06)')
    parser.add_argument('--timeline', '-t', action='store_true', help='Generate detailed leak timeline')
    args = parser.parse_args()

    target = args.path
    out_dir = args.output_dir or os.path.join(os.path.dirname(target), 'MemoryReports')
    os.makedirs(out_dir, exist_ok=True)

    if os.path.isfile(target):
        # Single file mode
        print(f"Parsing: {target}")
        data = extract_snap_data(target)
        report = generate_individual_md(data)
        out_file = os.path.join(out_dir, os.path.splitext(data['filename'])[0] + '.md')
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report written to: {out_file}")
    else:
        # Batch mode
        snap_files = sorted([
            os.path.join(target, f) for f in os.listdir(target)
            if f.endswith('.snap') and (args.prefix is None or f.startswith(args.prefix))
        ])
        if not snap_files:
            print(f"No .snap files found in {target}" + (f" with prefix '{args.prefix}'" if args.prefix else ''))
            sys.exit(1)

        print(f"Found {len(snap_files)} .snap files")

        # Individual reports
        ind_dir = os.path.join(out_dir, '01_Individual')
        os.makedirs(ind_dir, exist_ok=True)

        all_data = []
        for sf in snap_files:
            print(f"  Parsing: {os.path.basename(sf)}")
            data = extract_snap_data(sf)
            all_data.append(data)
            report = generate_individual_md(data)
            out_file = os.path.join(ind_dir, os.path.splitext(data['filename'])[0] + '.md')
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(report)

        # Comparative
        comp_md = generate_comparative_md(all_data)
        comp_file = os.path.join(out_dir, '02_Comparative_Analysis.md')
        with open(comp_file, 'w', encoding='utf-8') as f:
            f.write(comp_md)
        print(f"Comparative analysis: {comp_file}")

        # Timeline
        if args.timeline:
            timeline_md = generate_timeline_md(all_data)
            timeline_file = os.path.join(out_dir, '03_Detailed_Leak_Timeline.md')
            with open(timeline_file, 'w', encoding='utf-8') as f:
                f.write(timeline_md)
            print(f"Leak timeline: {timeline_file}")

        # Summary JSON
        summary = []
        for d in all_data:
            summary.append({
                'timestamp': d['timestamp'],
                'total_native_mb': round(d['total_native'] / 1048576, 2),
                'gfx_mb': round(d['gfx_total'] / 1048576, 2),
                'texture2d_mb': round(d['cat_totals'].get('Texture2D', 0) / 1048576, 2),
                'render_texture_mb': round(d['cat_totals'].get('RenderTexture', 0) / 1048576, 2),
                'mesh_mb': round(d['cat_totals'].get('Mesh', 0) / 1048576, 2),
                'object_count': len(d['objects']),
                'scenes': d['scenes'],
            })
        json_file = os.path.join(out_dir, 'summary.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"Summary JSON: {json_file}")

        print("Done!")


if __name__ == '__main__':
    main()
