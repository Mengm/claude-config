#!/usr/bin/env python3
"""
Unity 本地崩溃分析工具 v2
- 使用 Windows dbghelp.dll (ctypes)，无需 pdbparse / MSVC
- 依赖：pip install minidump pefile
- 用法：python analyze_crash.py <crash_folder> [--metadata <global-metadata.dat>]
        文件夹可直接放 crash.dmp，也可以是 Unity 生成的含子文件夹的结构
"""

import sys
import os
import re
import struct
import ctypes
import ctypes.wintypes
import argparse
from pathlib import Path
from datetime import datetime

# 强制 stdout/stderr 使用 UTF-8，避免 GBK 编码问题
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── 异常码速查表 ─────────────────────────────────────────────────────────────

EXCEPTION_CODES = {
    0xC0000005: "ACCESS_VIOLATION（野指针/空指针/UAF）",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO（除零）",
    0xC00000FD: "STACK_OVERFLOW（栈溢出）",
    0xC0000409: "STACK_BUFFER_OVERRUN（栈缓冲区溢出）",
    0x80000003: "BREAKPOINT（assert 断言失败）",
    0xE06D7363: "C++ EXCEPTION（未捕获 C++ 异常）",
    0xC0000374: "HEAP_CORRUPTION（堆内存损坏）",
    0xC0000008: "INVALID_HANDLE（无效句柄）",
    0xC000001D: "ILLEGAL_INSTRUCTION（非法指令）",
    0xC0000006: "IN_PAGE_ERROR（内存分页错误）",
}


def get_exc_str(code):
    return EXCEPTION_CODES.get(code, f"0x{code:08X}")


def access_violation_hint(exc_info):
    """
    ACCESS_VIOLATION ExceptionInformation 解读
    [0] = 0(读) / 1(写) / 8(DEP)
    [1] = 被访问的非法地址
    """
    if not exc_info or len(exc_info) < 2:
        return ""
    op = {0: "读", 1: "写", 8: "DEP 执行"}.get(exc_info[0], f"op={exc_info[0]}")
    addr = exc_info[1]
    if addr < 0x1000:
        hint = f"空指针 +0x{addr:X} 偏移（对象已释放或未初始化）"
    elif addr > 0xFFFFF000:
        hint = "野指针 / UAF（Use-After-Free）"
    else:
        hint = f"非法地址 0x{addr:X}"
    return f"{op}操作 → {hint}"


# ─── 文件自动发现 ──────────────────────────────────────────────────────────────

def discover_files(crash_folder: Path, log_override=None, metadata_override=None):
    """
    在 crash_folder 及其一级子文件夹中查找：
    - crash.dmp
    - Player.log
    - *.pdb / *.dll（只在根目录）
    - global-metadata.dat
    """
    result = {
        "dmp": None,
        "player_log": None,
        "pdbs": [],   # list of Path
        "dlls": [],   # list of Path
        "metadata": None,
    }

    # crash.dmp / Player.log：根目录 + 一级子目录
    search_dirs = [crash_folder] + sorted(
        [d for d in crash_folder.iterdir() if d.is_dir()]
    )
    for d in search_dirs:
        if result["dmp"] is None and (d / "crash.dmp").exists():
            result["dmp"] = d / "crash.dmp"
        if result["player_log"] is None:
            log = d / "Player.log"
            if log.exists():
                result["player_log"] = log

    if log_override:
        result["player_log"] = Path(log_override)

    # PDB / DLL：只在根目录
    for f in crash_folder.iterdir():
        if f.suffix.lower() == ".pdb":
            result["pdbs"].append(f)
        elif f.suffix.lower() == ".dll":
            result["dlls"].append(f)

    # global-metadata.dat
    meta_default = crash_folder / "global-metadata.dat"
    if metadata_override:
        result["metadata"] = Path(metadata_override)
    elif meta_default.exists():
        result["metadata"] = meta_default

    return result


def match_dll_to_pdb(dll_path: Path, pdb_dir: Path):
    """
    从 DLL debug directory 读取 CodeView 记录，找到对应 PDB 文件名，
    然后在 pdb_dir 中查找（大小写不敏感）。
    """
    try:
        import pefile
        pe = pefile.PE(str(dll_path), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DEBUG"]]
        )
        for entry in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []):
            if entry.struct.Type == 2:  # IMAGE_DEBUG_TYPE_CODEVIEW (RSDS)
                data = pe.get_data(entry.struct.AddressOfRawData, entry.struct.SizeOfData)
                if data[:4] == b"RSDS":
                    # RSDS + GUID (16) + age (4) + null-terminated path
                    raw_path = data[24:].split(b"\x00")[0].decode("utf-8", errors="replace")
                    pdb_name = Path(raw_path).name
                    for f in pdb_dir.iterdir():
                        if f.name.lower() == pdb_name.lower():
                            return f
    except Exception:
        pass
    return None


def build_pdb_map(files: dict):
    """
    构建 module_key (lowercase dll stem) → pdb_path 的映射，使用 pefile 精确匹配。
    回退：pdb 文件名包含 dll stem 的做前缀匹配。
    返回：{module_key: (dll_path, pdb_path)}
    """
    pdb_map = {}
    pdb_dir = files["pdbs"][0].parent if files["pdbs"] else None
    if not pdb_dir:
        return pdb_map

    for dll in files["dlls"]:
        key = dll.stem.lower()
        # 方式 1: pefile 精确匹配
        matched = match_dll_to_pdb(dll, pdb_dir)
        if matched:
            pdb_map[key] = (dll, matched)
            continue
        # 方式 2: pdb 文件名前缀匹配
        for pdb in files["pdbs"]:
            if pdb.stem.lower().startswith(key):
                pdb_map[key] = (dll, pdb)
                break

    return pdb_map


# ─── DbghelpResolver（Windows dbghelp.dll via ctypes）────────────────────────

class DbghelpResolver:
    """
    使用 Windows 内置 dbghelp.dll 加载 PDB 并解析符号。
    不需要 pdbparse，不需要 MSVC 编译。
    原理：SymInitialize → SymLoadModuleEx → SymFromAddr
    """

    _handle_counter = 0x1000  # 每个实例使用不同的假 process handle

    def __init__(self, dll_path: Path, pdb_path: Path):
        DbghelpResolver._handle_counter += 1
        self._handle = ctypes.c_void_p(DbghelpResolver._handle_counter)
        self._dbghelp = None
        self.module_base = 0
        self.loaded = False
        self.dll_name = dll_path.name if dll_path else "?"
        self.pdb_name = pdb_path.name if pdb_path else "?"

        self._init(dll_path, pdb_path)

    def _init(self, dll_path: Path, pdb_path: Path):
        try:
            dbg = ctypes.WinDLL("dbghelp.dll")
            self._dbghelp = dbg

            # SymSetOptions：只开启 undecorate，不开 deferred（必须立即加载 PDB）
            SYMOPT_UNDNAME = 0x2
            dbg.SymSetOptions(SYMOPT_UNDNAME)

            # SymInitialize(hProcess, SearchPath, fInvadeProcess)
            search_path = str(pdb_path.parent).encode("mbcs")
            ret = dbg.SymInitialize(self._handle, search_path, ctypes.c_bool(False))
            if not ret:
                err = ctypes.windll.kernel32.GetLastError()
                print(f"  [DBGHELP] SymInitialize 失败: {self.dll_name} err={err}", file=sys.stderr)
                return

            # SymLoadModuleEx
            dbg.SymLoadModuleEx.restype = ctypes.c_uint64
            dbg.SymLoadModuleEx.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                ctypes.c_uint64, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
            ]
            FIXED_BASE = 0x10000000
            image_name = str(dll_path).encode("mbcs")
            base = dbg.SymLoadModuleEx(
                self._handle, None, image_name, None, FIXED_BASE, 0, None, 0,
            )
            if base == 0:
                err = ctypes.windll.kernel32.GetLastError()
                print(f"  [DBGHELP] SymLoadModuleEx 失败: {self.dll_name} err={err}", file=sys.stderr)
                return

            self.module_base = base
            self.loaded = True
            print(f"  [DBGHELP] {self.dll_name} ({self.pdb_name}): 符号加载成功")

        except Exception as e:
            print(f"  [DBGHELP] 初始化异常: {self.dll_name}: {e}", file=sys.stderr)

    def lookup(self, rva: int):
        """rva → (symbol_name, offset)；失败返回 (None, 0)"""
        if not self.loaded:
            return None, 0
        try:
            dbg = self._dbghelp
            addr = self.module_base + rva

            # 正确的 SYMBOL_INFO 布局：
            # SizeOfStruct 必须等于 "不含 Name 扩展缓冲区" 的基础大小（88 字节，64-bit）
            MAX_NAME_LEN = 2000

            class SYMBOL_INFO_BASE(ctypes.Structure):
                _fields_ = [
                    ("SizeOfStruct", ctypes.c_ulong),
                    ("TypeIndex",    ctypes.c_ulong),
                    ("Reserved",     ctypes.c_uint64 * 2),
                    ("Index",        ctypes.c_ulong),
                    ("Size",         ctypes.c_ulong),
                    ("ModBase",      ctypes.c_uint64),
                    ("Flags",        ctypes.c_ulong),
                    ("Value",        ctypes.c_uint64),
                    ("Address",      ctypes.c_uint64),
                    ("Register",     ctypes.c_ulong),
                    ("Scope",        ctypes.c_ulong),
                    ("Tag",          ctypes.c_ulong),
                    ("NameLen",      ctypes.c_ulong),
                    ("MaxNameLen",   ctypes.c_ulong),
                    ("Name",         ctypes.c_char * 1),
                ]

            class SYMBOL_INFO(ctypes.Structure):
                _fields_ = SYMBOL_INFO_BASE._fields_[:-1] + [
                    ("Name", ctypes.c_char * MAX_NAME_LEN),
                ]

            sym = SYMBOL_INFO()
            # SizeOfStruct = sizeof with Name[1] = 88 bytes (64-bit Windows)
            sym.SizeOfStruct = ctypes.sizeof(SYMBOL_INFO_BASE)
            sym.MaxNameLen = MAX_NAME_LEN
            displacement = ctypes.c_uint64(0)

            dbg.SymFromAddr.restype = ctypes.c_bool
            dbg.SymFromAddr.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint64,
                ctypes.POINTER(ctypes.c_uint64),
                ctypes.c_void_p,   # PSYMBOL_INFO，用 c_void_p 避免 ctypes 类型冲突
            ]
            ok = dbg.SymFromAddr(
                self._handle,
                ctypes.c_uint64(addr),
                ctypes.byref(displacement),
                ctypes.byref(sym),
            )
            if ok:
                name = sym.Name[: sym.NameLen].decode("mbcs", errors="replace")
                return name, int(displacement.value)
        except Exception:
            pass
        return None, 0

    def __del__(self):
        try:
            if self.loaded and self._dbghelp:
                self._dbghelp.SymCleanup(self._handle)
        except Exception:
            pass


# ─── IL2CPP 名称清理 ──────────────────────────────────────────────────────────

def demangle_il2cpp(name: str) -> str:
    """
    将 IL2CPP C++ 符号名转换为可读 C# 格式：
      SkillComponent_OnSkillStart_m12345  → SkillComponent.OnSkillStart
      Combat_CombatManager__ProcessHit_m9 → Combat.CombatManager.ProcessHit
    """
    if not name:
        return name
    # 去掉尾部方法/类型 token
    cleaned = re.sub(r"_m\d+$", "", name)
    cleaned = re.sub(r"_t\d+$", "", cleaned)
    if cleaned == name:
        return name
    # 双下划线（命名空间）→ '.'
    cleaned = cleaned.replace("__", ".")
    # 剩余单下划线（首个）→ '.'（类名_方法名）
    parts = cleaned.split("_", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        cleaned = parts[0] + "." + parts[1]
    return cleaned


# ─── Player.log 解析 ───────────────────────────────────────────────────────────

def parse_player_log(log_path: Path):
    result = {
        "version": None,
        "unity_version": None,
        "last_lines": [],
        "errors": [],
        "lua_stack": None,
        "last_scene": None,
    }
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return result, str(e)

    if not lines:
        return result, "Player.log 为空"

    # 版本信息（前 30 行）
    for line in lines[:30]:
        s = line.strip()
        if re.search(r"Unity\s+\d{4}\.", s):
            result["unity_version"] = s
        if re.search(r"(Version|version)\s*[:=]\s*\S+", s):
            result["version"] = s

    # 最后 80 行
    result["last_lines"] = [l.rstrip() for l in lines[-80:]]

    # 错误行
    ERROR_KW = ["ERROR", "Error", "Exception", "FATAL", "Fatal",
                "Assert", "assert", "Crash", "NullReference", "IndexOutOfRange"]
    for i, line in enumerate(lines):
        if any(kw in line for kw in ERROR_KW):
            result["errors"].append((i + 1, line.strip()))

    # 最后 Lua 调用栈（反向扫描）
    lua_lines = []
    in_block = False
    for line in reversed(lines):
        s = line.strip()
        is_lua = (
            re.match(r"stack traceback:", s, re.I)
            or re.match(r"\[.*\.lua:\d+\]", s)
            or re.match(r"\[C\]", s)
            or (in_block and s.startswith("["))
        )
        if is_lua or (in_block and s):
            lua_lines.insert(0, s)
            in_block = True
        elif in_block and not s:
            break
    if lua_lines:
        result["lua_stack"] = "\n".join(lua_lines[:25])

    # 最后场景
    for line in reversed(lines):
        if re.search(r"(Loading|Unloading)\s+(scene|level|Scene)", line, re.I):
            result["last_scene"] = line.strip()
            break

    return result, None


# ─── crash.dmp 解析 ───────────────────────────────────────────────────────────

def parse_crash_dmp(dmp_path: Path, pdb_map: dict):
    """
    解析 crash.dmp，返回：
    - exception_code / str / address / exc_info_hint
    - crashing_thread_id
    - modules list
    - crashing_thread_frames list
    """
    import logging
    logging.disable(logging.CRITICAL)  # 抑制 minidump 的 ERROR 日志

    from minidump.minidumpfile import MinidumpFile
    from minidump.minidumpreader import MinidumpFileReader

    result = {
        "exception_code": None,
        "exception_code_str": "未知",
        "exception_address": None,
        "exc_info_hint": "",
        "crashing_thread_id": None,
        "modules": [],
        "crashing_thread_frames": [],
    }

    mf = MinidumpFile.parse(str(dmp_path))
    reader = MinidumpFileReader(mf)

    # ── 异常信息（minidump 0.0.24 API）───────────────────────────
    if mf.exception and mf.exception.exception_records:
        exc_stream = mf.exception.exception_records[0]
        rec = exc_stream.ExceptionRecord
        code_raw = rec.ExceptionCode_raw  # int
        result["exception_code"] = code_raw
        result["exception_code_str"] = get_exc_str(code_raw)
        result["exception_address"] = rec.ExceptionAddress
        result["crashing_thread_id"] = exc_stream.ThreadId
        if code_raw == 0xC0000005:
            exc_info = rec.ExceptionInformation  # list of ints or ';' string
            if isinstance(exc_info, str):
                parts = [int(x, 16) if x.startswith("0x") else int(x)
                         for x in exc_info.split(";") if x.strip()]
                exc_info = parts
            result["exc_info_hint"] = access_violation_hint(exc_info)

    # ── 模块列表（0.0.24：baseaddress, size, endaddress）─────────
    modules = []
    if mf.modules:
        for mod in mf.modules.modules:
            name = mod.name or "unknown"
            display = Path(name).name
            key = display.lower().replace(".dll", "").replace(".exe", "")
            modules.append({
                "base":    mod.baseaddress,
                "size":    mod.size,
                "display": display,
                "key":     key,
            })
    modules.sort(key=lambda m: m["base"])
    result["modules"] = modules

    # ── 构建 DbghelpResolver ──────────────────────────────────────
    print("  [符号] 构建解析器...")
    resolvers = {}
    for mod_key, (dll_path, pdb_path) in pdb_map.items():
        r = DbghelpResolver(dll_path, pdb_path)
        if r.loaded:
            resolvers[mod_key] = r

    # ── 地址 → 符号 闭包 ─────────────────────────────────────────
    def find_module(addr):
        lo, hi = 0, len(modules) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            m = modules[mid]
            if m["base"] <= addr:
                if addr < m["base"] + m["size"]:
                    return m
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def resolve(addr):
        if addr < 0x1000:
            return None, None, 0
        mod = find_module(addr)
        if mod is None:
            return None, None, 0
        rva = addr - mod["base"]
        resolver = resolvers.get(mod["key"])
        if resolver:
            sym, off = resolver.lookup(rva)
            if sym:
                return mod["display"], demangle_il2cpp(sym), off
        return mod["display"], f"RVA+0x{rva:X}", 0

    # ── 获取崩溃线程堆栈 ─────────────────────────────────────────
    crashing_tid = result["crashing_thread_id"]
    if crashing_tid is None:
        return result

    frames = _get_frames(mf, reader, crashing_tid, resolve)
    result["crashing_thread_frames"] = frames
    return result


def _get_frames(mf, reader, crashing_tid, resolve):
    frames = []

    # 方式 1: minidump walker
    try:
        from minidump.walker import walk_minidump
        for thread in mf.threads.threads:
            if thread.ThreadId != crashing_tid:
                continue
            for frame in walk_minidump(mf, reader, thread):
                addr = (getattr(frame, "return_address", None)
                        or getattr(frame, "ip", None)
                        or getattr(frame, "pc", None) or 0)
                if addr > 0x1000:
                    mod, sym, off = resolve(addr)
                    frames.append({"addr": addr, "module": mod, "symbol": sym, "offset": off})
            break
        if frames:
            print(f"  [堆栈] walker 展开：{len(frames)} 帧")
            return frames[:60]
    except Exception as e:
        print(f"  [堆栈] walker 不可用（{e}），改用栈扫描", file=sys.stderr)

    # 方式 2: 直接读崩溃线程 RIP（ContextObject 是已解析的 CONTEXT 结构体）
    try:
        for thread in mf.threads.threads:
            if thread.ThreadId != crashing_tid:
                continue
            ctx = thread.ContextObject   # CONTEXT struct with Rip/Rsp etc.
            ip = getattr(ctx, "Rip", None) or getattr(ctx, "Eip", None)
            if ip and ip > 0x1000:
                mod, sym, off = resolve(ip)
                frames.append({"addr": ip, "module": mod, "symbol": sym, "offset": off,
                               "is_crash_ip": True})
                print(f"  [堆栈] 崩溃 RIP: 0x{ip:016X} → {mod}!{sym}")
            break
    except Exception:
        pass

    # 方式 3: 原始栈内存扫描
    try:
        stack_frames = _raw_stack_scan(mf, reader, crashing_tid, resolve)
        frames.extend(stack_frames)
        print(f"  [堆栈] 原始扫描：{len(stack_frames)} 帧")
    except Exception as e:
        print(f"  [堆栈] 扫描失败: {e}", file=sys.stderr)

    return frames[:60]


def _raw_stack_scan(mf, reader, crashing_tid, resolve):
    frames = []
    SCAN_LIMIT = 128 * 1024

    for thread in mf.threads.threads:
        if thread.ThreadId != crashing_tid:
            continue
        try:
            stk = thread.Stack
            start = stk.StartOfMemoryRange
            # minidump 0.0.24: DataSize 在 Stack 上，而不是 Stack.Memory.DataSize
            size = min(stk.DataSize, SCAN_LIMIT)
            data = reader.read(start, size)
            if not data:
                break

            seen = set()
            for i in range(0, len(data) - 7, 8):
                addr = struct.unpack_from("<Q", data, i)[0]
                if addr in seen or addr < 0x10000:
                    continue
                mod, sym, off = resolve(addr)
                if mod is not None:
                    frames.append({"addr": addr, "module": mod, "symbol": sym, "offset": off})
                    seen.add(addr)
                    if len(frames) >= 60:
                        break
        except Exception as e:
            print(f"  [堆栈] 原始扫描异常: {e}", file=sys.stderr)
        break

    return frames


# ─── global-metadata.dat 校验 ────────────────────────────────────────────────

def check_global_metadata(metadata_path: Path):
    MAGIC = b"\xAF\x1B\xB1\xFA"
    try:
        with open(metadata_path, "rb") as f:
            magic = f.read(4)
        if magic == MAGIC:
            size_kb = metadata_path.stat().st_size // 1024
            print(f"  [META] global-metadata.dat 有效（{size_kb}KB）")
            print(f"  [META] 当前版本：使用 dbghelp.dll + IL2CPP 名称清理，供参考")
        else:
            print(f"  [META] 文件无效，magic={magic.hex()}", file=sys.stderr)
    except Exception as e:
        print(f"  [META] 读取失败: {e}", file=sys.stderr)


# ─── 报告格式 ─────────────────────────────────────────────────────────────────

SEP = "─" * 62


def fmt_frame(i, f):
    mod = f.get("module") or "?"
    sym = f.get("symbol") or ""
    off = f.get("offset", 0)
    addr = f.get("addr", 0)
    pfx = "💥" if f.get("is_crash_ip") else f"#{i:02d}"

    if sym and not sym.startswith("RVA+"):
        return f"  {pfx}  {mod}!{sym} +0x{off:X}" if off else f"  {pfx}  {mod}!{sym}"
    return f"  {pfx}  {mod} @ 0x{addr:016X}"


def infer_conclusion(dmp):
    code = dmp.get("exception_code", 0)
    frames = dmp.get("crashing_thread_frames", [])

    # 第一个有意义的符号帧
    top = next((f for f in frames
                if f.get("symbol") and not f["symbol"].startswith("RVA+")), None)

    # 根因描述
    if code == 0xC0000005:
        hint = dmp.get("exc_info_hint", "")
        reason = f"内存访问违例（ACCESS_VIOLATION）{('— ' + hint) if hint else ''}"
    elif code == 0xC00000FD:
        reason = "栈溢出（STACK_OVERFLOW），可能存在无限递归"
    elif code == 0xC0000374:
        reason = "堆内存损坏（HEAP_CORRUPTION），写越界或 double-free"
    elif code == 0xE06D7363:
        reason = "未捕获的 C++ 异常"
    elif code == 0x80000003:
        reason = "断言失败（assert / __debugbreak）"
    else:
        reason = dmp.get("exception_code_str", "未知异常")

    crash_pt = "未能符号化"
    if top:
        mod, sym, off = top["module"], top["symbol"], top.get("offset", 0)
        crash_pt = f"{mod}!{sym} +0x{off:X}" if off else f"{mod}!{sym}"

    chain_frames = [f for f in frames
                    if f.get("symbol") and not f["symbol"].startswith("RVA+")][:5]
    chain = " → ".join(f["symbol"].split(".")[-1] for f in chain_frames) if chain_frames else "（待分析）"

    return reason, crash_pt, chain


def format_report(dmp, log, crash_type, folder_str):
    out = []

    out += [
        "╔══════════════════════════════════════════════════════════════╗",
        "║            Unity 本地崩溃分析报告                           ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
    ]

    # 基本信息
    out += ["📋 基本信息", SEP,
            f"崩溃类型  : {crash_type}",
            f"分析时间  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"崩溃文件夹: {folder_str}"]
    if log.get("unity_version"):
        out.append(f"Unity 版本: {log['unity_version']}")
    if log.get("version"):
        out.append(f"游戏版本  : {log['version']}")
    if log.get("last_scene"):
        out.append(f"最后场景  : {log['last_scene']}")
    out.append("")

    # 异常信息
    out += ["💥 异常信息", SEP]
    out.append(f"异常类型  : {dmp.get('exception_code_str', '未知')}")
    ea = dmp.get("exception_address")
    if ea is not None:
        out.append(f"崩溃地址  : 0x{ea:016X}")
    hint = dmp.get("exc_info_hint")
    if hint:
        out.append(f"地址分析  : {hint}")
    tid = dmp.get("crashing_thread_id")
    if tid is not None:
        out.append(f"崩溃线程  : Thread ID = 0x{tid:X}")
    out.append("")

    # 崩溃堆栈
    out += ["📚 崩溃线程堆栈（已符号化）", SEP]
    frames = dmp.get("crashing_thread_frames", [])
    if frames:
        for i, f in enumerate(frames[:40]):
            out.append(fmt_frame(i, f))
    else:
        out.append("  （堆栈提取失败，请确认 PDB 与 DLL 版本一致）")
    out.append("")

    # 关键模块
    key_mods = [m for m in dmp.get("modules", [])
                if any(k in m["key"] for k in ["gameassembly", "unityplayer"])]
    if key_mods:
        out += ["🔧 关键模块", SEP]
        for m in key_mods[:4]:
            out.append(f"  {m['display']:<50} @ 0x{m['base']:016X}  size=0x{m['size']:X}")
        out.append("")

    # Player.log 上下文
    out += ["📄 Player.log 上下文（崩溃前最后 30 行）", SEP]
    last_lines = log.get("last_lines", [])
    if last_lines:
        for l in last_lines[-30:]:
            out.append(f"  {l[:160]}")
    else:
        out.append("  （未提供 Player.log）")
    out.append("")

    # Lua 调用栈
    lua = log.get("lua_stack")
    if lua:
        out += ["🔷 Lua 调用栈（最后捕获）", SEP, lua, ""]

    # 关键错误行
    errors = log.get("errors", [])
    if errors:
        out += [f"⚠️  关键错误/异常（共 {len(errors)} 处，显示前 15 条）", SEP]
        for lineno, err in errors[:15]:
            out.append(f"  [行{lineno:6d}] {err[:140]}")
        out.append("")

    # 结论
    reason, crash_pt, chain = infer_conclusion(dmp)
    lua_ctx = (log.get("lua_stack") or "").split("\n")[0] if log.get("lua_stack") else "无"

    out += [
        "═" * 62,
        "## 崩溃分析结论",
        "",
        f"**根因**   : {reason}",
        f"**崩溃点** : {crash_pt}",
        f"**调用链** : {chain}",
        f"**Lua上下文**: {lua_ctx}",
        "**修复建议**: （根据上方堆栈分析填写）",
        "**优先级** : P0 / P1 / P2 / P3",
        "",
    ]
    return "\n".join(out)


# ─── 主入口 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unity 本地崩溃分析（离线，使用 dbghelp.dll，无需 WinDbg）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("crash_folder", help="崩溃文件夹（含 crash.dmp / PDB / DLL）")
    parser.add_argument("--metadata", "-m", help="global-metadata.dat 路径（可选）")
    parser.add_argument("--log",      "-l", help="Player.log 路径（默认自动查找）")
    parser.add_argument("--output",   "-o", help="报告输出路径（默认 <folder>/crash-report.txt）")
    args = parser.parse_args()

    crash_folder = Path(args.crash_folder)
    if not crash_folder.exists():
        print(f"错误：文件夹不存在: {crash_folder}")
        sys.exit(1)

    # 检查依赖（只需要 minidump + pefile）
    missing = []
    for pkg in ["minidump", "pefile"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"缺少依赖，请安装：pip install {' '.join(missing)}")
        sys.exit(1)

    print(f"\n{'='*62}")
    print(f"  Unity 本地崩溃分析 — {crash_folder.name}")
    print(f"{'='*62}\n")

    # 自动发现文件
    files = discover_files(crash_folder, args.log, args.metadata)

    print("[文件检测]")
    dmp_str  = "OK " + str(files["dmp"]) if files["dmp"] else "MISSING!"
    log_str  = "OK " + str(files["player_log"]) if files["player_log"] else "MISSING (跳过日志分析)"
    meta_str = "OK" if files["metadata"] else "- 无（可选）"
    print(f"  crash.dmp   : {dmp_str}")
    print(f"  Player.log  : {log_str}")
    print(f"  PDB 文件    : {[f.name for f in files['pdbs']]}")
    print(f"  DLL 文件    : {[f.name for f in files['dlls']]}")
    print(f"  metadata    : {meta_str}")

    if not files["dmp"]:
        print("错误：未找到 crash.dmp")
        sys.exit(1)

    is_pc = any("gameassembly" in p.name.lower() for p in files["pdbs"])
    crash_type = "PC 包体崩溃" if is_pc else "Unity Editor 崩溃"
    print(f"  崩溃类型    : {crash_type}")
    print()

    # PDB 映射
    print("[PDB 匹配]")
    pdb_map = build_pdb_map(files)
    for key, (dll, pdb) in pdb_map.items():
        print(f"  {dll.name} → {pdb.name}")
    if not pdb_map:
        print("  警告：未找到 DLL↔PDB 匹配，将只显示模块名和 RVA")
    print()

    # global-metadata
    if files["metadata"]:
        print("[元数据]")
        check_global_metadata(files["metadata"])
        print()

    # Player.log
    log_result = {}
    if files["player_log"]:
        print("[日志解析]")
        log_result, err = parse_player_log(files["player_log"])
        if err:
            print(f"  警告: {err}")
        else:
            print(f"  错误行: {len(log_result.get('errors', []))}  "
                  f"Lua堆栈: {'✓' if log_result.get('lua_stack') else '无'}")
        print()
    else:
        print("[日志解析] 跳过（无 Player.log）\n")

    # crash.dmp 解析
    print("[崩溃分析]")
    dmp_result = parse_crash_dmp(files["dmp"], pdb_map)
    print(f"  崩溃帧数: {len(dmp_result.get('crashing_thread_frames', []))}")
    print()

    # 生成报告
    report = format_report(dmp_result, log_result, crash_type, str(crash_folder))

    output_path = Path(args.output) if args.output else crash_folder / "crash-report.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\n{'='*62}")
    print(f"报告已保存: {output_path}")


if __name__ == "__main__":
    main()
