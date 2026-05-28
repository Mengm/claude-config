#!/usr/bin/env python3
"""
Unity Profiler .data file parser and performance analyzer.

Parses the "processed" binary format used by Unity 2022.3 Profiler's
SaveProfile/LoadProfile (Editor save format).

Binary format reverse-engineered from Unity Engine source:
  - Modules/ProfilerEditor/Public/ProfilerSession.cpp (SaveToFile/LoadFromFile)
  - Modules/ProfilerEditor/ProfilerHistory/ProfilerFrameData.cpp (Serialize/Deserialize)
  - Modules/Profiler/Public/ProfilerStats.cpp (AllStats serialization)
  - Modules/Profiler/Public/Int32StreamReader.cpp (String/Array encoding)
"""

import struct
import sys
import os
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Version Constants ──────────────────────────────────────────────────────

VERSION_INITIAL                    = 0x20170327
VERSION_UPDATED_PHYSICS_2D         = 0x20171110
VERSION_UPDATED_CHART_SAMPLE       = 0x20180123
VERSION_ADDED_UI_STATS             = 0x20180704
VERSION_ADDED_FRAME_META_GI       = 0x20181101
VERSION_ADDED_GATHER_DATA_FLAGS    = 0x20180306
VERSION_ADDED_METHOD_JIT           = 0x20190514
VERSION_UPDATED_START_TIME_64      = 0x20190821
VERSION_ADDED_MARKER_METADATA      = 0x20191104
VERSION_ADDED_GPU_STATS_UNITY_VER  = 0x20191122
VERSION_ADDED_FLOW_EVENTS          = 0x20200312
VERSION_UPDATED_CALLSTACKS_64      = 0x20200828
VERSION_UPDATED_THREAD_ID_64       = 0x20200924
VERSION_ADDED_DYNAMIC_CATEGORIES   = 0x20210412
VERSION_ADDED_UNITY_OBJECT_NAMES   = 0x20210919
VERSION_ADDED_CATEGORY_STATE       = 0x20211025
VERSION_HEADER_V2                  = 0x20211028
VERSION_ADDED_GFX_RESOURCE_INFO    = 0x20220328

COMPATIBLE_VERSIONS = {
    VERSION_INITIAL, VERSION_UPDATED_PHYSICS_2D, VERSION_UPDATED_CHART_SAMPLE,
    VERSION_ADDED_UI_STATS, VERSION_ADDED_FRAME_META_GI, VERSION_ADDED_GATHER_DATA_FLAGS,
    VERSION_ADDED_METHOD_JIT, VERSION_UPDATED_START_TIME_64, VERSION_ADDED_MARKER_METADATA,
    VERSION_ADDED_GPU_STATS_UNITY_VER, VERSION_ADDED_FLOW_EVENTS,
    VERSION_UPDATED_CALLSTACKS_64, VERSION_UPDATED_THREAD_ID_64,
    VERSION_ADDED_DYNAMIC_CATEGORIES, VERSION_ADDED_UNITY_OBJECT_NAMES,
    VERSION_ADDED_CATEGORY_STATE, VERSION_HEADER_V2, VERSION_ADDED_GFX_RESOURCE_INFO,
}

# Number of int32s for ReadArray of known structs (for skipping)
# PhysicsStats: 7 ints + 8 platform = 15
PHYSICS_STATS_DWORDS = 15
# NetworkOperationStats: 11 ints + 8 platform = 19
NETWORK_OP_STATS_DWORDS = 19
# NetworkMessageStats: 12 ints + 8 platform = 20
NETWORK_MSG_STATS_DWORDS = 20
# AudioStats: counted from struct = 37 ints + 8 platform (not used for ReadArray since it's int-aligned)
# UIStats: 2 ints + 8 platform = 10
CALLSTACK_FRAMES_COUNT = 32


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class MarkerInfo:
    marker_id: int = 0
    name: str = ""
    category: int = 0
    flags: int = 0


@dataclass
class SampleInfo:
    """One profiler sample (begin/end pair already resolved)."""
    marker_name: str = ""
    duration_ns: float = 0.0    # self time in nanoseconds
    start_time_ns: int = 0
    child_count: int = 0
    gc_alloc: int = 0


@dataclass
class ThreadInfo:
    thread_id: int = 0
    group_name: str = ""
    thread_name: str = ""
    samples: List[SampleInfo] = field(default_factory=list)
    total_gc_alloc: int = 0
    max_depth: int = 0


@dataclass
class FrameStats:
    """Summary statistics extracted from AllProfilerStats."""
    # Memory
    mem_used_total: int = 0
    mem_used_mono: int = 0
    mem_gc_alloc_count: int = 0
    mem_gc_alloc_bytes: int = 0
    # Draw
    set_pass_calls: int = 0
    batches: int = 0
    draw_calls: int = 0
    triangles: int = 0
    vertices: int = 0
    shadow_casters: int = 0
    # Chart sample (CPU breakdown in nanoseconds)
    cpu_rendering: float = 0.0
    cpu_scripts: float = 0.0
    cpu_physics: float = 0.0
    cpu_animation: float = 0.0
    cpu_gc: float = 0.0
    cpu_vsync: float = 0.0
    cpu_gi: float = 0.0
    cpu_ui: float = 0.0
    cpu_others: float = 0.0
    # GPU chart
    gpu_opaque: float = 0.0
    gpu_transparent: float = 0.0
    gpu_shadows: float = 0.0
    gpu_post_process: float = 0.0


@dataclass
class FrameData:
    frame_index: int = 0
    real_frame: int = 0
    start_time_ns: int = 0
    total_cpu_us: int = 0
    total_gpu_us: int = 0
    stats: FrameStats = field(default_factory=FrameStats)
    threads: List[ThreadInfo] = field(default_factory=list)


# ── Int32 Stream Reader ───────────────────────────────────────────────────

class Int32Stream:
    """Mimics Unity's Int32StreamReader - reads int32-aligned data."""

    def __init__(self, data: bytes):
        # data is the raw bytes of the frame payload
        # Interpret as array of int32
        n = len(data) // 4
        self.ints = struct.unpack(f'<{n}i', data[:n*4])
        self.uints = struct.unpack(f'<{n}I', data[:n*4])
        self.floats = struct.unpack(f'<{n}f', data[:n*4])
        self.raw = data
        self.pos = 0  # position in int32 units
        self.size = n

    def remaining(self) -> int:
        return self.size - self.pos

    def read_int32(self) -> int:
        if self.pos >= self.size:
            raise EOFError(f"Int32Stream: read past end at dword {self.pos}/{self.size}")
        v = self.ints[self.pos]
        self.pos += 1
        return v

    def read_uint32(self) -> int:
        if self.pos >= self.size:
            raise EOFError(f"Int32Stream: read past end at dword {self.pos}/{self.size}")
        v = self.uints[self.pos]
        self.pos += 1
        return v

    def read_uint64(self) -> int:
        lo = self.read_uint32()
        hi = self.read_uint32()
        return lo | (hi << 32)

    def read_float(self) -> float:
        if self.pos >= self.size:
            raise EOFError(f"Int32Stream: read past end at dword {self.pos}/{self.size}")
        v = self.floats[self.pos]
        self.pos += 1
        return v

    def peek_int32(self) -> int:
        if self.pos >= self.size:
            raise EOFError("Int32Stream: peek past end")
        return self.ints[self.pos]

    def read_string(self) -> str:
        """Read null-terminated string, padded to 4-byte boundary."""
        byte_offset = self.pos * 4
        # Find null terminator
        end = byte_offset
        max_end = len(self.raw)
        while end < max_end and self.raw[end] != 0:
            end += 1
        length = end - byte_offset
        s = self.raw[byte_offset:byte_offset + length]
        # Advance by ceil((length+1) / 4) dwords (null terminator included)
        dwords = (length // 4) + 1
        self.pos += dwords
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError:
            return s.decode('utf-8', errors='replace')

    def read_array_raw(self, size_bytes: int):
        """Read size_bytes, advancing by aligned dword count."""
        dwords = (size_bytes + 3) // 4
        if self.pos + dwords > self.size:
            raise EOFError(f"ReadArray: need {dwords} dwords, only {self.remaining()} left")
        byte_offset = self.pos * 4
        data = self.raw[byte_offset:byte_offset + size_bytes]
        self.pos += dwords
        return data

    def skip_dwords(self, n: int):
        self.pos += n

    def skip_bytes(self, n: int):
        self.pos += (n + 3) // 4

    def read_int32_array(self) -> list:
        """Read dynamic_array<int> - count then data."""
        count = self.read_int32()
        dwords = (count * 4 + 3) // 4  # count ints = count dwords
        result = []
        for _ in range(count):
            result.append(self.read_int32())
        return result

    def skip_struct_array(self, struct_size_bytes: int):
        """Read count, then skip count * struct_size bytes."""
        count = self.read_int32()
        if count > 0:
            total_bytes = count * struct_size_bytes
            self.skip_bytes(total_bytes)
        return count


# ── Parser ─────────────────────────────────────────────────────────────────

class UnityProfilerParser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.version = 0
        self.unity_version = (0, 0, 0, 0)
        self.frames: List[FrameData] = []
        self.markers: Dict[int, MarkerInfo] = {}  # global marker table (accumulated across frames)
        self.parse_errors = 0
        self._last_marker_id = 0

    def parse(self):
        file_size = os.path.getsize(self.filepath)
        print(f"Parsing: {self.filepath}")
        print(f"File size: {file_size / (1024*1024):.2f} MB")

        with open(self.filepath, 'rb') as f:
            data = f.read()

        pos = 0
        frame_count = 0
        prev_frame = None

        while pos + 8 <= len(data):
            # Read frame chunk header
            signature = struct.unpack_from('<i', data, pos)[0]
            if signature not in COMPATIBLE_VERSIONS:
                # Try to find next valid signature
                found = False
                for v in COMPATIBLE_VERSIONS:
                    vb = struct.pack('<i', v)
                    idx = data.find(vb, pos + 1)
                    if idx >= 0:
                        pos = idx
                        found = True
                        break
                if not found:
                    break
                continue

            self.version = signature
            pos += 4

            # Read size
            frame_size = struct.unpack_from('<I', data, pos)[0]
            pos += 4

            if frame_size % 4 != 0 or frame_size > len(data) - pos:
                print(f"  [WARN] Invalid frame size {frame_size} at offset {pos-8}, skipping")
                self.parse_errors += 1
                pos += 4
                continue

            # Read Unity version (5 ints: Major, Minor, Revision, ReleaseType, IncrementalVersion)
            # for version >= kVersion_HeaderV2
            if self.version >= VERSION_HEADER_V2:
                if pos + 20 > len(data):
                    break
                uv = struct.unpack_from('<5I', data, pos)
                self.unity_version = uv
                pos += 20
            else:
                # Old format: thread count follows (we read it as part of frame data)
                pass

            # Read frame payload
            if pos + frame_size > len(data):
                print(f"  [WARN] Frame data truncated, stopping")
                break

            frame_payload = data[pos:pos + frame_size]
            pos += frame_size

            try:
                frame = self._parse_frame(frame_payload, prev_frame)
                self.frames.append(frame)
                prev_frame = frame
                frame_count += 1
                if frame_count % 100 == 0:
                    print(f"  Parsed {frame_count} frames...")
            except Exception as e:
                self.parse_errors += 1
                if self.parse_errors <= 10:
                    print(f"  [WARN] Frame parse error at frame {frame_count}: {e}")

        print(f"\nParsing complete:")
        print(f"  Frames: {len(self.frames)}")
        print(f"  Markers: {len(self.markers)}")
        if self.unity_version[0] > 0:
            v = self.unity_version
            rt = {0: 'a', 1: 'b', 2: 'f', 3: 'p', 4: 'x'}.get(v[3], 'f') if len(v) > 3 else 'f'
            inc = v[4] if len(v) > 4 else 0
            print(f"  Unity: {v[0]}.{v[1]}.{v[2]}{rt}{inc}")
        print(f"  Version: 0x{self.version:08X}")
        if self.parse_errors:
            print(f"  Parse errors: {self.parse_errors}")

    def _parse_frame(self, payload: bytes, prev_frame: Optional[FrameData]) -> FrameData:
        s = Int32Stream(payload)
        version = self.version
        frame = FrameData()

        # The last dword is kEndOfFrameSignature (0xAFAFAFAF), don't parse it
        if s.size > 0 and s.uints[s.size - 1] == 0xAFAFAFAF:
            s.size -= 1

        # Basic frame info
        frame.frame_index = s.read_int32()
        frame.real_frame = s.read_int32()

        # Frame start time
        start_time = s.read_uint32()
        if version >= VERSION_UPDATED_CALLSTACKS_64:
            start_time |= s.read_uint32() << 32
        elif version >= VERSION_UPDATED_START_TIME_64:
            start_time |= s.read_uint32() << 32
            start_time *= 1000
        frame.start_time_ns = start_time

        frame.total_cpu_us = s.read_int32()
        frame.total_gpu_us = s.read_int32()

        if version >= VERSION_ADDED_GPU_STATS_UNITY_VER:
            _gathered_data = s.read_int32()

        # AllProfilerStats
        frame.stats = self._deserialize_all_stats(s)

        # Audio/UI instance data arrays (skip with correct struct sizes)
        for elem_sz in [64, 56, 1, 52, 1, 12, 1, 4]:
            self._skip_typed_array(s, elem_sz)

        # Markers
        is_new_session = False
        if version >= VERSION_HEADER_V2:
            marker_count = s.read_int32()
            if marker_count > 0:
                is_new_session = True
                for mi in range(marker_count):
                    mid = s.read_uint32()
                    name, cat, flags, meta = self._deserialize_marker_info(s)
                    self.markers[mid] = MarkerInfo(marker_id=mid, name=name, category=cat, flags=flags)
        else:
            pass

        # Threads
        thread_count = s.read_int32()
        for t in range(thread_count):
            ti = ThreadInfo()

            if version >= VERSION_UPDATED_THREAD_ID_64:
                ti.thread_id = s.read_uint64()
            ti.group_name = s.read_string()
            ti.thread_name = s.read_string()

            # Samples
            sample_count = s.read_int32()
            for i in range(sample_count):
                sample = SampleInfo()

                if version >= VERSION_HEADER_V2:
                    marker_id = s.read_uint32()
                    marker = self.markers.get(marker_id)
                    sample.marker_name = marker.name if marker else f"Marker_{marker_id}"
                else:
                    marker_id = 0  # will be filled later

                if version >= VERSION_UPDATED_CALLSTACKS_64:
                    sample.duration_ns = s.read_float()
                    st = s.read_uint32()
                    st |= s.read_uint32() << 32
                    sample.start_time_ns = st
                elif version >= VERSION_UPDATED_START_TIME_64:
                    sample.duration_ns = s.read_float() * 1e3
                    st = s.read_uint32()
                    st |= s.read_uint32() << 32
                    sample.start_time_ns = st * 1000
                else:
                    sample.duration_ns = s.read_int32() * 1000
                    sample.start_time_ns = s.read_uint32() * 1000

                sample.child_count = s.read_int32()
                ti.samples.append(sample)

            # GPU time samples
            gpu_count = s.read_int32()
            s.skip_dwords(gpu_count * 3)  # 3 ints per GPU sample

            # InstanceID samples
            if version >= VERSION_ADDED_UNITY_OBJECT_NAMES:
                iid_count = s.read_int32()
                s.skip_dwords(iid_count * 2)  # relatedSampleIndex + instanceID

            # GC Alloc samples
            gc_count = s.read_int32()
            for _ in range(gc_count):
                related_idx = s.read_int32()
                alloc_size = s.read_int32()
                if 0 <= related_idx < len(ti.samples):
                    ti.samples[related_idx].gc_alloc += alloc_size
                    ti.total_gc_alloc += alloc_size

            # Per-sample markers (old format only)
            if version < VERSION_HEADER_V2:
                for i in range(sample_count):
                    has_marker = s.peek_int32()
                    # ReadMarkerConditionaly logic: read string, if empty skip
                    name = s.read_string()
                    if name:
                        cat = s.read_uint32() & 0xFFFF
                        flags = (s.read_uint32() >> 16) & 0xFFFF
                        if version >= VERSION_ADDED_MARKER_METADATA:
                            meta_count = s.read_int32()
                            for _ in range(meta_count):
                                _mname = s.read_string()
                                _mtype = s.read_int32()
                        ti.samples[i].marker_name = name
                    else:
                        # Use previous marker with same name
                        if i > 0:
                            ti.samples[i].marker_name = ti.samples[i-1].marker_name

            # Warning samples (dynamic_array<int>, 4 bytes per elem)
            self._skip_int_array(s)

            # Metadata
            meta_count = s.read_int32()
            for _ in range(meta_count):
                _related = s.read_int32()
                md_count = s.read_int32()
                for _ in range(md_count):
                    _mtype = s.read_int32()
                    # metadata value as byte array: count + ceil(count/4) dwords
                    byte_count = s.read_int32()
                    if byte_count > 0:
                        s.skip_dwords((byte_count + 3) // 4)

            # FrameStatSamples + MaxDepth
            if version > VERSION_ADDED_FRAME_META_GI:
                self._skip_int_array(s)  # FrameStatSamples
                ti.max_depth = s.read_int32()
            elif version == VERSION_ADDED_FRAME_META_GI:
                value = s.read_int32()
                if value == 0:
                    self._skip_int_array(s)  # empty FrameStatSamples was already consumed as 0
                    ti.max_depth = s.read_int32()
                else:
                    ti.max_depth = value
            else:
                ti.max_depth = 0

            # Callstack samples
            if version >= VERSION_ADDED_METHOD_JIT:
                cs_count = s.read_int32()
                if version >= VERSION_UPDATED_CALLSTACKS_64:
                    s.skip_dwords(cs_count * (1 + CALLSTACK_FRAMES_COUNT * 2))
                else:
                    s.skip_dwords(cs_count * (1 + CALLSTACK_FRAMES_COUNT))

            # Flow events
            if version >= VERSION_ADDED_FLOW_EVENTS:
                if version > VERSION_UPDATED_THREAD_ID_64 or (s.remaining() > 0 and s.peek_int32() >= 0):
                    fe_count = s.read_int32()
                    s.skip_dwords(fe_count * 3)

            frame.threads.append(ti)

        # JIT info (global, after all threads)
        if version >= VERSION_ADDED_METHOD_JIT:
            jit_count = s.read_int32()
            for _ in range(jit_count):
                s.read_string()  # name
                s.read_string()  # fileName
                s.read_uint32()  # addr lo
                if version >= VERSION_UPDATED_CALLSTACKS_64:
                    s.read_uint32()  # addr hi
                s.read_int32()   # size
                s.read_int32()   # sourceFileLine

        # Dynamic categories
        if version >= VERSION_ADDED_DYNAMIC_CATEGORIES:
            cat_count = s.read_int32()
            for _ in range(cat_count):
                _cat_id = s.read_uint32()
                _color = s.read_int32()
                _flags = s.read_int32()
                _name = s.read_string()
                if version >= VERSION_ADDED_CATEGORY_STATE:
                    _enabled = s.read_uint32()

        # Unity object names
        if version >= VERSION_ADDED_UNITY_OBJECT_NAMES:
            # Native types
            nt_count = s.read_int32()
            for _ in range(nt_count):
                _base_type = s.read_uint32()
                _name = s.read_string()

            # Unity objects
            obj_count = s.read_int32()
            for _ in range(obj_count):
                _inst_id = s.read_int32()
                if version >= VERSION_ADDED_GFX_RESOURCE_INFO:
                    _related_go = s.read_int32()
                _type_id = s.read_uint32()
                _name = s.read_string()
                if version >= VERSION_ADDED_GFX_RESOURCE_INFO:
                    _root_id = s.read_uint64()

        # GfxResource info
        if version >= VERSION_ADDED_GFX_RESOURCE_INFO:
            gfx_count = s.read_int32()
            s.skip_dwords(gfx_count * 4)  # 2x uint64 = 4 dwords each

        return frame

    def _deserialize_marker_info(self, s: Int32Stream):
        name = s.read_string()
        packed = s.read_uint32()
        category = (packed >> 16) & 0xFFFF
        flags = packed & 0xFFFF
        meta = []
        if self.version >= VERSION_ADDED_MARKER_METADATA:
            meta_count = s.read_int32()
            for _ in range(meta_count):
                m_param_and_unit = s.read_int32()
                m_name = s.read_string()
                meta.append((m_name, m_param_and_unit))
        return name, category, flags, meta

    def _deserialize_all_stats(self, s: Int32Stream) -> FrameStats:
        stats = FrameStats()
        version = self.version

        # _deprecated_memoryStats.Deserialize (33 fields)
        stats.mem_used_total = s.read_int32() * 1024
        _unity = s.read_int32() * 1024
        stats.mem_used_mono = s.read_int32() * 1024
        for _ in range(4):  # gfx, audio, video, profiler
            s.read_int32()
        for _ in range(7):  # reserved: total, unity, mono, gfx, audio, video, profiler
            s.read_int32()
        s.read_int32()  # bytesVirtual
        for _ in range(2):  # textureCount, textureBytes
            s.read_int32()
        for _ in range(2):  # meshCount, meshBytes
            s.read_int32()
        for _ in range(2):  # materialCount, materialBytes
            s.read_int32()
        for _ in range(2):  # animClipCount, animClipBytes
            s.read_int32()
        for _ in range(2):  # audioCount, audioBytes
            s.read_int32()
        for _ in range(3):  # assetCount, sceneObjectCount, gameObjectCount
            s.read_int32()
        s.read_int32()  # totalObjectsCount
        s.read_int32()  # profilerMemUsed
        s.read_int32()  # profilerNumAllocations
        stats.mem_gc_alloc_count = s.read_int32()
        stats.mem_gc_alloc_bytes = s.read_int32() * 1024
        # classCount map - robust sentinel search
        cc_size = s.read_int32()  # classCount.size (resize hint)
        sentinel_pos = s.pos
        found_sentinel = False
        max_search = min(cc_size * 2 + 1, 10000)
        for offset in range(max_search + 1):
            check_pos = s.pos + offset
            if check_pos + 17 >= s.size:
                break
            if s.ints[check_pos] == -1:
                draw_start = check_pos + 1 + 16
                if draw_start < s.size:
                    spc = s.ints[draw_start]
                    if 0 <= spc <= 100000:
                        sentinel_pos = check_pos
                        found_sentinel = True
                        break
        if found_sentinel:
            s.pos = sentinel_pos + 1
        else:
            pid = s.read_int32()
            while pid != -1:
                _cnt = s.read_int32()
                pid = s.read_int32()
        # platformDependentStats
        for _ in range(16):
            s.read_int32()

        # _deprecated_drawStats.Deserialize
        stats.set_pass_calls = s.read_int32()
        stats.batches = s.read_int32()
        stats.draw_calls = s.read_int32()
        stats.triangles = s.read_int32() * 1024
        stats.vertices = s.read_int32() * 1024
        for _ in range(4):  # dynamic batch stats
            s.read_int32()
        for _ in range(4):  # static batch stats
            s.read_int32()
        for _ in range(5):  # instancing stats
            s.read_int32()
        stats.shadow_casters = s.read_int32()
        for _ in range(2):  # usedTextureCount, usedTextureBytes
            s.read_int32()
        for _ in range(3):  # renderTextureCount, renderTextureBytes, renderTextureStateChanges
            s.read_int32()
        for _ in range(3):  # screen stats
            s.read_int32()
        for _ in range(7):  # VBO/IB stats + skinned meshes
            s.read_int32()
        s.read_int32()  # totalAvailableVRamMBytes
        for _ in range(16):  # platformDependentStats
            s.read_int32()

        # _deprecated_physicsStats (ReadArray - struct)
        for _ in range(PHYSICS_STATS_DWORDS):
            s.read_int32()

        # _deprecated_physics2DStats.Deserialize
        for _ in range(13):  # base fields
            s.read_int32()
        if version >= VERSION_UPDATED_PHYSICS_2D:
            s.read_int32()  # DiscreteIslandCount
            s.read_int32()  # ContinuousIslandCount
        else:
            s.skip_dwords(8)  # 8 old floats
        # platformDependentStats: ReadArray(T&) = sizeof(int[8]) = 8 dwords, NO count prefix
        s.skip_dwords(8)
        # networkOperationStats (ReadArray)
        for _ in range(NETWORK_OP_STATS_DWORDS):
            s.read_int32()

        # networkMessageStats (ReadArray)
        for _ in range(NETWORK_MSG_STATS_DWORDS):
            s.read_int32()

        # debugStats.Deserialize
        s.read_int32()  # profilerMemoryUsage
        s.read_int32()  # profilerMemoryUsageOthers
        s.read_int32()  # allocatedProfileSamples
        if version >= VERSION_ADDED_GPU_STATS_UNITY_VER:
            for _ in range(7):
                s.read_int32()

        # audioStats (ReadArray) - full struct
        AUDIO_STATS_DWORDS = 45
        for _ in range(AUDIO_STATS_DWORDS):
            s.read_int32()

        # videoStats.Deserialize
        s.read_int32()  # totalVideoSourceCount
        s.read_int32()  # playingSources
        s.read_int32()  # swPlayingSources
        if version >= VERSION_UPDATED_PHYSICS_2D:
            s.read_int32()  # preBufferedFrames
            s.read_int32()  # preBufferedFrameLimit
            s.read_int32()  # framesDropped
        s.read_int32()  # pausedSources
        s.read_int32()  # videoClipCount
        # platformDependentStats: ReadArray(T&) = sizeof(int[8]) = 8 dwords, NO count prefix
        s.skip_dwords(8)

        # chartSample.Deserialize
        stats.cpu_rendering = s.read_float()
        stats.cpu_scripts = s.read_float()
        stats.cpu_physics = s.read_float()
        if version >= VERSION_UPDATED_CHART_SAMPLE:
            stats.cpu_animation = s.read_float()
        stats.cpu_gc = s.read_float()
        stats.cpu_vsync = s.read_float()
        stats.cpu_gi = s.read_float()
        stats.cpu_ui = s.read_float()
        stats.cpu_others = s.read_float()
        stats.gpu_opaque = s.read_float()
        stats.gpu_transparent = s.read_float()
        stats.gpu_shadows = s.read_float()
        stats.gpu_post_process = s.read_float()
        s.read_float()  # gpuDeferredGeometry
        s.read_float()  # gpuDeferredLighting
        s.read_float()  # gpuOther
        s.read_int32()   # hasGPUProfiler
        s.read_float()  # uisystemLayouting
        s.read_float()  # uisystemRendering

        # chartSampleSelected.Deserialize (same layout)
        s.read_float()  # rendering
        s.read_float()  # scripts
        s.read_float()  # physics
        if version >= VERSION_UPDATED_CHART_SAMPLE:
            s.read_float()  # animation
        for _ in range(12):  # gc, vsync, gi, UI, others, gpu*7 = 12 floats
            s.read_float()
        s.read_int32()  # hasGPUProfiler
        s.read_float()  # uisystemLayouting
        s.read_float()  # uisystemRendering

        # uiStats
        if version >= VERSION_ADDED_UI_STATS:
            UI_STATS_DWORDS = 10  # 2 + 8 platform
            for _ in range(UI_STATS_DWORDS):
                s.read_int32()

        # globalIlluminationStats.Deserialize
        s.read_float()   # m_TotalCPUTime
        s.read_int32()   # m_TotalSystemCount
        s.read_int32()   # m_TotalProbeSetCount
        s.read_float()   # m_ProbeTime
        s.read_int32()   # m_TotalProbesCount
        s.read_int32()   # m_SolvedProbesCount
        for _ in range(8):  # SetupTime, EnvironmentTime, InputLightingTime, SystemsTime,
            s.read_float()   # SolveTasksTime, DynamicObjectsTime, TimeBetweenUpdates, OtherCommandsTime
        s.read_int32()   # m_BlockedBufferWritesCount
        s.read_float()   # m_BlockedCommandWriteTime
        if version >= VERSION_ADDED_FRAME_META_GI:
            s.read_int32()   # m_PendingMaterialUpdateCount
            s.read_int32()   # m_PendingAlbedoUpdateCount


        return stats

    def _skip_typed_array(self, s: Int32Stream, elem_bytes: int):
        """Skip a dynamic_array<T> serialized as count + raw data."""
        count = s.read_int32()
        if count > 0:
            total_bytes = elem_bytes * count
            dwords = (total_bytes + 3) // 4
            s.skip_dwords(dwords)
        return count

    def _skip_int_array(self, s: Int32Stream):
        """Skip a dynamic_array<int/uint32> (4 bytes per element)."""
        return self._skip_typed_array(s, 4)

    # ── Analysis ───────────────────────────────────────────────────────────

    def analyze(self) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append("  UNITY PROFILER DATA ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append("")

        if not self.frames:
            lines.append("  No frames parsed. File may be corrupted or unsupported.")
            return "\n".join(lines)

        # File info
        lines.append("[File Info]")
        lines.append(f"  File: {os.path.basename(self.filepath)}")
        v = self.unity_version
        if v[0] > 0:
            rt = {0: 'a', 1: 'b', 2: 'f', 3: 'p', 4: 'x'}.get(v[3], 'f') if len(v) > 3 else 'f'
            inc = v[4] if len(v) > 4 else 0
            lines.append(f"  Unity: {v[0]}.{v[1]}.{v[2]}{rt}{inc}")
        lines.append(f"  Protocol: 0x{self.version:08X}")
        lines.append(f"  Total Frames: {len(self.frames)}")
        lines.append(f"  Unique Markers: {len(self.markers)}")
        lines.append("")

        # Frame timing overview
        cpu_times = [f.total_cpu_us / 1000.0 for f in self.frames]
        gpu_times = [f.total_gpu_us / 1000.0 for f in self.frames if f.total_gpu_us > 0]
        avg_cpu = sum(cpu_times) / len(cpu_times) if cpu_times else 0
        max_cpu = max(cpu_times) if cpu_times else 0
        min_cpu = min(cpu_times) if cpu_times else 0
        p95_cpu = sorted(cpu_times)[int(len(cpu_times) * 0.95)] if cpu_times else 0

        lines.append("[Frame Timing Overview]")
        lines.append(f"  CPU Frame Time:")
        lines.append(f"    Average: {avg_cpu:.2f} ms  ({1000/avg_cpu:.1f} FPS)" if avg_cpu > 0 else "    Average: N/A")
        lines.append(f"    Min:     {min_cpu:.2f} ms")
        lines.append(f"    Max:     {max_cpu:.2f} ms")
        lines.append(f"    P95:     {p95_cpu:.2f} ms  ({1000/p95_cpu:.1f} FPS)" if p95_cpu > 0 else "    P95: N/A")

        if gpu_times:
            avg_gpu = sum(gpu_times) / len(gpu_times)
            max_gpu = max(gpu_times)
            lines.append(f"  GPU Frame Time:")
            lines.append(f"    Average: {avg_gpu:.2f} ms")
            lines.append(f"    Max:     {max_gpu:.2f} ms")

        # Determine bottleneck
        if gpu_times and avg_cpu > 0:
            avg_gpu = sum(gpu_times) / len(gpu_times)
            if avg_gpu > avg_cpu * 1.2:
                lines.append(f"  >> GPU BOUND (GPU avg {avg_gpu:.1f}ms > CPU avg {avg_cpu:.1f}ms)")
            elif avg_cpu > avg_gpu * 1.2:
                lines.append(f"  >> CPU BOUND (CPU avg {avg_cpu:.1f}ms > GPU avg {avg_gpu:.1f}ms)")
            else:
                lines.append(f"  >> BALANCED (CPU ~= GPU)")
        lines.append("")

        # CPU breakdown (from chart samples)
        lines.append("[CPU Time Breakdown (Average per Frame)]")
        cpu_cats = defaultdict(list)
        for f in self.frames:
            s = f.stats
            cpu_cats["Rendering"].append(s.cpu_rendering)
            cpu_cats["Scripts"].append(s.cpu_scripts)
            cpu_cats["Physics"].append(s.cpu_physics)
            cpu_cats["Animation"].append(s.cpu_animation)
            cpu_cats["GC"].append(s.cpu_gc)
            cpu_cats["VSync"].append(s.cpu_vsync)
            cpu_cats["UI"].append(s.cpu_ui)
            cpu_cats["Others"].append(s.cpu_others)

        total_cpu_chart = 0
        cat_avgs = []
        for cat, vals in cpu_cats.items():
            avg_ns = sum(vals) / len(vals)
            avg_ms = avg_ns / 1_000_000.0
            cat_avgs.append((cat, avg_ms))
            total_cpu_chart += avg_ms

        cat_avgs.sort(key=lambda x: x[1], reverse=True)
        for cat, avg_ms in cat_avgs:
            pct = (avg_ms / total_cpu_chart * 100) if total_cpu_chart > 0 else 0
            bar_len = int(pct / 2)
            bar = "#" * bar_len
            lines.append(f"  {cat:<15} {avg_ms:>8.2f} ms  ({pct:>5.1f}%)  {bar}")
        lines.append("")

        # Rendering stats
        lines.append("[Rendering Stats (Average per Frame)]")
        avg_batches = sum(f.stats.batches for f in self.frames) / len(self.frames)
        avg_setpass = sum(f.stats.set_pass_calls for f in self.frames) / len(self.frames)
        avg_dc = sum(f.stats.draw_calls for f in self.frames) / len(self.frames)
        avg_tris = sum(f.stats.triangles for f in self.frames) / len(self.frames)
        avg_verts = sum(f.stats.vertices for f in self.frames) / len(self.frames)
        avg_shadow = sum(f.stats.shadow_casters for f in self.frames) / len(self.frames)
        lines.append(f"  Batches:       {avg_batches:>10.0f}")
        lines.append(f"  SetPass Calls: {avg_setpass:>10.0f}")
        lines.append(f"  Draw Calls:    {avg_dc:>10.0f}")
        lines.append(f"  Triangles:     {avg_tris:>10,.0f}")
        lines.append(f"  Vertices:      {avg_verts:>10,.0f}")
        lines.append(f"  Shadow Casters:{avg_shadow:>10.0f}")
        lines.append("")

        # Memory stats
        lines.append("[Memory Stats (Average)]")
        avg_mem = sum(f.stats.mem_used_total for f in self.frames) / len(self.frames)
        avg_mono = sum(f.stats.mem_used_mono for f in self.frames) / len(self.frames)
        avg_gc_count = sum(f.stats.mem_gc_alloc_count for f in self.frames) / len(self.frames)
        avg_gc_bytes = sum(f.stats.mem_gc_alloc_bytes for f in self.frames) / len(self.frames)
        max_gc_bytes = max(f.stats.mem_gc_alloc_bytes for f in self.frames)
        lines.append(f"  Total Used:      {avg_mem / (1024*1024):>10.1f} MB")
        lines.append(f"  Mono Heap:       {avg_mono / (1024*1024):>10.1f} MB")
        lines.append(f"  GC Alloc/Frame:  {avg_gc_count:>10.0f} allocations")
        lines.append(f"  GC Bytes/Frame:  {avg_gc_bytes:>10,.0f} bytes (avg)")
        lines.append(f"  GC Bytes/Frame:  {max_gc_bytes:>10,} bytes (max)")
        lines.append("")

        # Thread overview
        if self.frames and self.frames[0].threads:
            lines.append("[Threads]")
            for ti in self.frames[0].threads:
                label = f"{ti.group_name}/{ti.thread_name}" if ti.group_name else ti.thread_name or "(unnamed)"
                sample_count = len(ti.samples)
                lines.append(f"  {label:<40} samples: {sample_count}")
            lines.append("")

        # Per-marker aggregation across all frames
        marker_agg = defaultdict(lambda: {"total_ns": 0.0, "self_ns": 0.0, "calls": 0, "gc_alloc": 0})
        for f in self.frames:
            for ti in f.threads:
                for sample in ti.samples:
                    name = sample.marker_name
                    marker_agg[name]["total_ns"] += sample.duration_ns
                    marker_agg[name]["calls"] += 1
                    marker_agg[name]["gc_alloc"] += sample.gc_alloc

        # Top markers by total time
        lines.append("[Top 30 Markers by Total Time]")
        sorted_markers = sorted(marker_agg.items(), key=lambda x: x[1]["total_ns"], reverse=True)[:30]
        lines.append(f"  {'Marker':<50} {'Calls':>8} {'Total ms':>12} {'Avg ms':>10} {'GC Alloc':>12}")
        lines.append(f"  {'-'*50} {'-'*8} {'-'*12} {'-'*10} {'-'*12}")
        for name, agg in sorted_markers:
            total_ms = agg["total_ns"] / 1_000_000.0
            avg_ms = total_ms / agg["calls"] if agg["calls"] > 0 else 0
            gc = agg["gc_alloc"]
            gc_str = f"{gc:,}" if gc > 0 else "-"
            lines.append(f"  {name:<50} {agg['calls']:>8} {total_ms:>12.2f} {avg_ms:>10.4f} {gc_str:>12}")
        lines.append("")

        # GC hotspots
        gc_markers = [(n, a) for n, a in marker_agg.items() if a["gc_alloc"] > 0]
        if gc_markers:
            gc_markers.sort(key=lambda x: x[1]["gc_alloc"], reverse=True)
            lines.append("[GC Allocation Hotspots]")
            for name, agg in gc_markers[:20]:
                lines.append(f"  {name:<50} {agg['gc_alloc']:>12,} bytes  ({agg['calls']} calls)")
            lines.append("")

        # Sample tree for first meaningful frame (frame with most samples)
        best_frame = max(self.frames[:min(100, len(self.frames))],
                        key=lambda f: sum(len(t.samples) for t in f.threads))
        if best_frame.threads:
            main_thread = best_frame.threads[0]
            if main_thread.samples:
                lines.append(f"[Main Thread Sample Tree - Frame {best_frame.frame_index}]")
                self._print_sample_tree(main_thread.samples, lines, max_depth=5, max_children=6)
                lines.append("")

        # Performance recommendations
        lines.append("=" * 80)
        lines.append("  PERFORMANCE RECOMMENDATIONS")
        lines.append("=" * 80)
        lines.append("")
        self._generate_recommendations(lines, marker_agg, cpu_cats, cat_avgs, avg_cpu, avg_gc_bytes)

        return "\n".join(lines)

    def _print_sample_tree(self, samples: List[SampleInfo], lines: list, max_depth: int, max_children: int):
        """Print hierarchical sample tree from flat pre-order array with child counts."""
        if not samples:
            return

        stack = []  # (remaining_children, depth)
        shown_at_depth = defaultdict(int)

        for sample in samples:
            # Pop completed parents
            while stack and stack[-1][0] <= 0:
                stack.pop()

            depth = len(stack)

            if depth > max_depth:
                # Skip but still track tree structure
                if sample.child_count > 0:
                    stack.append([sample.child_count, depth])
                if stack:
                    stack[-1][0] -= 1
                continue

            indent = "  " + "  " * depth
            dur_ms = sample.duration_ns / 1_000_000.0
            gc_str = f" [GC:{sample.gc_alloc:,}B]" if sample.gc_alloc else ""
            lines.append(f"{indent}{sample.marker_name}: {dur_ms:.3f} ms{gc_str}")

            if sample.child_count > 0:
                stack.append([sample.child_count, depth])

            if stack:
                stack[-1][0] -= 1

    def _generate_recommendations(self, lines, marker_agg, cpu_cats, cat_avgs, avg_cpu_ms, avg_gc_bytes):
        recs = []
        num_frames = len(self.frames)

        # Frame rate assessment
        if avg_cpu_ms > 33.3:
            recs.append((100, f"[Low Frame Rate] Average {avg_cpu_ms:.1f} ms/frame ({1000/avg_cpu_ms:.0f} FPS)\n"
                        f"    Target 30 FPS = 33.3 ms budget. Currently over budget."))
        elif avg_cpu_ms > 16.6:
            recs.append((50, f"[Medium Frame Rate] Average {avg_cpu_ms:.1f} ms/frame ({1000/avg_cpu_ms:.0f} FPS)\n"
                        f"    Runs at 30 FPS but not reaching 60 FPS target (16.6 ms)."))

        # CPU category analysis
        for cat, avg_ms in cat_avgs:
            if cat == "VSync":
                continue  # VSync wait is intentional
            if avg_ms > avg_cpu_ms * 0.3 and avg_ms > 2.0:
                advice_map = {
                    "Rendering": "Reduce draw calls/batches, simplify shaders, lower resolution, reduce overdraw.",
                    "Scripts": "Profile C# code hotspots. Check Update() methods, avoid per-frame allocations.",
                    "Physics": "Reduce rigidbody count, simplify colliders, increase Fixed Timestep.",
                    "Animation": "Reduce Animator count, use simpler rigs, optimize animation curves.",
                    "GC": "Reduce per-frame managed allocations. Use object pooling, avoid LINQ/boxing/string ops.",
                    "UI": "Split canvases (static vs dynamic), reduce UI element count, avoid frequent rebuilds.",
                    "Others": "Investigate with Profiler Hierarchy view for detailed breakdown.",
                }
                advice = advice_map.get(cat, "Investigate this category.")
                pct = avg_ms / avg_cpu_ms * 100
                recs.append((avg_ms, f"[CPU: {cat} is {pct:.0f}% of frame] {avg_ms:.2f} ms avg\n    {advice}"))

        # GC analysis
        if avg_gc_bytes > 4096:
            recs.append((avg_gc_bytes / 10000,
                f"[GC Allocations: {avg_gc_bytes:,.0f} bytes/frame avg]\n"
                f"    Per-frame GC pressure is significant. Aim for < 1 KB/frame.\n"
                f"    Common causes: string operations, LINQ, boxing, temporary collections, delegate creation."))

        # Rendering specific
        avg_batches = sum(f.stats.batches for f in self.frames) / num_frames
        avg_setpass = sum(f.stats.set_pass_calls for f in self.frames) / num_frames
        avg_tris = sum(f.stats.triangles for f in self.frames) / num_frames

        if avg_batches > 500:
            recs.append((avg_batches / 100,
                f"[High Batch Count: {avg_batches:.0f} avg]\n"
                f"    Consider: SRP Batcher, GPU Instancing, static batching, mesh combining, LODs."))

        if avg_setpass > 200:
            recs.append((avg_setpass / 50,
                f"[High SetPass Calls: {avg_setpass:.0f} avg]\n"
                f"    Too many material variations. Consolidate materials, use material property blocks."))

        if avg_tris > 2_000_000:
            recs.append((avg_tris / 1_000_000,
                f"[High Triangle Count: {avg_tris:,.0f} avg]\n"
                f"    Consider LOD groups, occlusion culling, mesh simplification for mobile."))

        # Known expensive markers
        known_markers = {
            "Gfx.WaitForPresent": "CPU is idle waiting for GPU. GPU bound - reduce shader complexity / resolution / overdraw.",
            "Gfx.WaitForCommands": "Main thread waiting for render thread. Consider reducing rendering workload.",
            "GC.Collect": "GC spike! Reduce managed allocations to prevent GC stalls.",
            "Canvas.SendWillRenderCanvases": "UI canvas rebuild. Split static/dynamic canvases.",
            "Canvas.BuildBatch": "UI batching cost. Reduce canvas complexity.",
            "Loading.UpdatePreloading": "Synchronous asset loading. Use async APIs.",
            "Shader.CreateGPUProgram": "Runtime shader compilation. Pre-warm shaders.",
            "RenderTexture.GrabPixels": "GPU readback to CPU - extremely expensive.",
        }

        for marker_name, advice in known_markers.items():
            if marker_name in marker_agg:
                agg = marker_agg[marker_name]
                total_ms = agg["total_ns"] / 1_000_000.0
                avg_ms = total_ms / num_frames
                if avg_ms > 0.5:
                    recs.append((avg_ms, f"[{marker_name}] {avg_ms:.2f} ms/frame avg\n    {advice}"))

        if recs:
            recs.sort(key=lambda x: x[0], reverse=True)
            for i, (_, text) in enumerate(recs, 1):
                lines.append(f"  {i}. {text}")
                lines.append("")
        else:
            lines.append("  No major performance issues detected.")
            lines.append("  The capture looks healthy based on available metrics.")
        lines.append("")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python unity_profiler_parser.py <path_to.data> [--json output.json]")
        print("\nParses Unity Profiler .data files and generates performance analysis.")
        sys.exit(1)

    filepath = sys.argv[1]
    json_output = None
    if "--json" in sys.argv:
        idx = sys.argv.index("--json")
        if idx + 1 < len(sys.argv):
            json_output = sys.argv[idx + 1]

    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    parser = UnityProfilerParser(filepath)

    try:
        parser.parse()
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    report = parser.analyze()
    print()
    print(report)

    report_path = filepath + ".analysis.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Report saved to: {report_path}")

    if json_output:
        data = {
            "file": os.path.basename(parser.filepath),
            "unity_version": list(parser.unity_version),
            "protocol_version": hex(parser.version),
            "frame_count": len(parser.frames),
            "frames": []
        }
        for frame in parser.frames:
            fd = {
                "index": frame.frame_index,
                "cpu_ms": frame.total_cpu_us / 1000.0,
                "gpu_ms": frame.total_gpu_us / 1000.0,
                "gc_alloc_bytes": frame.stats.mem_gc_alloc_bytes,
                "batches": frame.stats.batches,
                "tris": frame.stats.triangles,
                "threads": [{
                    "name": t.thread_name,
                    "group": t.group_name,
                    "sample_count": len(t.samples),
                    "gc_alloc": t.total_gc_alloc
                } for t in frame.threads]
            }
            data["frames"].append(fd)

        with open(json_output, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"JSON exported to: {json_output}")


if __name__ == "__main__":
    main()
