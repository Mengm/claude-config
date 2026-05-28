---
name: unity-hang-analysis
version: 1.0.0
description: "分析 Unity Editor 进程卡死/挂起问题。当用户反映 Unity 进程 CPU 极低但无响应、界面点击无反应、进程 Not Responding 时使用。"
metadata:
  platform: windows
  requires:
    bins: ["powershell", "python"]
    optional: ["WinDbg Preview (Microsoft Store)"]
---

# Unity 进程卡死分析

## 总体流程

```
1. 确认进程状态（Responding=False？）
2. 读 Editor.log 末尾（找卡住前最后一条操作）
3. 生成 minidump（Python + ctypes，需要管理员提权）
4. 用 cdb.exe 加载 dump，分析线程栈
5. 识别死锁模式
6. 在日志/代码里找根因触发点
```

---

## Step 1：确认进程状态

```powershell
Get-Process Unity -ErrorAction SilentlyContinue |
  Select-Object Id, CPU, WorkingSet, Responding, Threads |
  Format-List
```

关键指标：
- `Responding: False` → 主线程卡死
- `CPU` 极低（< 1%）→ 不是死循环，是阻塞等待

查所有线程等待原因：
```powershell
(Get-Process -Id <PID>).Threads |
  Select-Object Id, ThreadState, WaitReason |
  Sort-Object WaitReason | Format-Table
```

典型卡死特征：所有线程 `WaitReason: UserRequest`（即 WaitForSingleObject）。

---

## Step 2：读 Editor.log

**日志路径：** `e:\WorkSpace\T3Trunk\client\logs\Editor.log`

```bash
tail -150 "e:/WorkSpace/T3Trunk/client/logs/Editor.log"
```

重点关注：
- 最后一条业务日志是什么操作（场景卸载？地形加载？shader 编译？）
- 是否有 `UnloadUnusedAssets`、`GC cycle`、`ShaderCacheRemote` 等关键字
- 日志是否在某个操作进行中突然停止

---

## Step 3：生成 minidump（管理员提权）

Unity 进程通常以管理员身份运行，直接 OpenProcess 会被拒绝（error 5）。
需要用 PowerShell 提权执行 Python 脚本。

**写入脚本 `dump_unity.py`：**

```python
import ctypes, ctypes.wintypes as wt, sys

PROCESS_ALL_ACCESS = 0x1F0FFF
MiniDumpWithFullMemory = 0x2
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x00000002

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
dbghelp  = ctypes.WinDLL('dbghelp',  use_last_error=True)

class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]

class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wt.DWORD)]

class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wt.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

def enable_debug_privilege():
    hToken = wt.HANDLE()
    advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),
                              TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                              ctypes.byref(hToken))
    luid = LUID()
    advapi32.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(luid))
    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    tp.Privileges[0].Luid = luid
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
    advapi32.AdjustTokenPrivileges(hToken, False, ctypes.byref(tp), ctypes.sizeof(tp), None, None)
    kernel32.CloseHandle(hToken)

pid       = <PID>   # 替换为实际 PID
dump_path = r"e:\WorkSpace\T3Trunk\client\logs\unity_hang.dmp"

enable_debug_privilege()
hProcess = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
hFile = kernel32.CreateFileW(dump_path, 0x40000000, 0, None, 2, 0x80, None)
dbghelp.MiniDumpWriteDump(hProcess, pid, hFile, MiniDumpWithFullMemory, None, None, None)
kernel32.CloseHandle(hFile)
kernel32.CloseHandle(hProcess)
print("Dump written:", dump_path)
```

**提权运行（UAC 弹窗）：**

```powershell
# 先把脚本放到 Windows 路径
Copy-Item /tmp/dump_unity.py "e:\WorkSpace\T3Trunk\client\logs\dump_unity.py"

# 提权执行
$result = Start-Process -FilePath 'python' `
  -ArgumentList 'e:\WorkSpace\T3Trunk\client\logs\dump_unity.py' `
  -Verb RunAs -Wait -PassThru
Write-Output "Exit: $($result.ExitCode)"
```

---

## Step 4：用 cdb.exe 分析 dump

### 找 cdb.exe（动态查最新版 WinDbg Preview）

```powershell
$cdb = Get-ChildItem 'C:\Program Files\WindowsApps' -Filter 'cdb.exe' -Recurse -Depth 4 |
  Where-Object { $_.FullName -match 'WinDbg.*x64' } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
Write-Output $cdb
```

典型路径：
`C:\Program Files\WindowsApps\Microsoft.WinDbg_1.2603.20001.0_x64__8wekyb3d8bbwe\amd64\cdb.exe`

### 写 cdb 命令脚本（必须用 -cf 文件方式，不能用 -c 内联）

```
# C:\tmp\cdb_cmds.txt
.sympath SRV*C:\Symbols*https://msdl.microsoft.com/download/symbols;e:\WorkSpace\T3Trunk\unity\WindowsEditor
.echo === Main Thread (Thread 0) ===
~0s
kn 40
.echo === All threads brief (RIP) ===
~*e .if (1) { .echo ---TID @$tid---; kn 5 }
q
```

### 运行（同步等待完成）

```bash
"$cdb" -z "e:/WorkSpace/T3Trunk/client/logs/unity_hang.dmp" \
       -cf "C:/tmp/cdb_cmds.txt" \
       -logo "e:/WorkSpace/T3Trunk/client/logs/cdb_out.txt"
```

### 查看关键线程

读输出文件，先 grep 找 Unity 符号：
```bash
grep -n "Unity!\|DynamicHeap\|GarbageCollect\|AGCThread\|ShaderCache\|Unload\|RtlEnter" \
    "e:/WorkSpace/T3Trunk/client/logs/cdb_out.txt" | head -60
```

找到关键 TID 后，单独对其全栈分析：
```
# 追加到 cdb 命令脚本
~~[0x<TID>]s
kn 30
```

---

## Step 5：识别死锁模式

### 模式一：GarbageCollectSharedAssets 阻塞（最常见）

```
主线程:
  ntdll!NtWaitForSingleObject
  KERNELBASE!WaitForSingleObjectEx
  Unity!Semaphore::WaitForSignalNoProfile
  Unity!AGCThread::WaitForTask         ← 等 AGC 线程完成
  Unity!WaitJobs
  Unity!GarbageCollectSharedAssets
  Unity!UnloadUnusedAssetsOperation::IntegrateMainThread
  Unity!PreloadManager::UpdatePreloading
  Unity!PlayerLoop → WinMain
```

触发条件：`Resources.UnloadUnusedAssets()` 或场景卸载时的自动 GC。

### 模式二：AGCThread 被堆锁阻塞

```
AGC 线程:
  ntdll!NtWaitForAlertByThreadId
  ntdll!RtlpWaitOnCriticalSection     ← 等堆锁
  ntdll!RtlEnterCriticalSection
  Unity!DynamicHeapAllocator::Allocate
  Unity!MemoryManager::Reallocate
  Unity!dynamic_array::push_back
  Unity!PhysicsManager::Transfer<RemapPPtrTransfer>  ← 遍历 PhysX 对象
  Unity!MarkDependencies
  Unity!MarkAllDependencies
  Unity!AGCThread::Run → AGCThread::RunThread
```

说明：场景中 PhysX 对象（Terrain Collider 等）越多，`MarkAllDependencies` 越慢。

### 模式三：IOService 线程持有堆锁（Shader Cache 上传）

```
IOService 线程:
  Unity!remove_free_block / Unity!tlsf_free
  Unity!DynamicHeapAllocator::Deallocate   ← 持有堆锁
  Unity!operator delete
  Unity!CacheServer::PutRequest::~PutRequest
  Unity!AcceleratorClient::InternalPut     ← shader cache 上传回调
  Unity!asio::detail::win_iocp_io_context::run
  Unity!IOService::Run
```

说明：shader cache 上传完成后销毁 protobuf 对象，持有堆锁，卡住 AGC 线程。

### 完整死锁链

```
主线程 ──等信号量──► AGC 线程
                         │
                     等堆锁
                         │
                    IOService 线程
                    (持有堆锁，处理 shader cache 上传)
```

---

## Step 6：从日志和代码里找触发点

### 日志里找 UnloadUnusedAssets

```bash
grep -n "Unload\|GC cycle\|UnloadScene\|unload" \
    "e:/WorkSpace/T3Trunk/client/logs/Editor.log" | \
    grep "14:5[0-9]" | tail -40
```

典型触发序列：
```
14:53:12  UnloadScene CustomAvatar
14:53:14  Unloading 1699 unused Assets
14:53:16  UnloadScene SuperComputingCenter
14:53:23  Unloading 1083 unused Assets         ← 同时大量 Terrain Collider 加载中
14:53:26  Unloading 480 Unused Serialized files ← 这次 GC 卡死
```

### 代码里找调用点

```bash
# Lua 脚本
grep -rn "UnloadUnusedAssets" \
    "e:/WorkSpace/T3Trunk/code/LuaScripts/"

# C# 脚本
grep -rn "UnloadUnusedAssets" \
    "e:/WorkSpace/T3Trunk/client/Assets/Scripts/Game/"
```

已知调用点：
| 文件 | 位置 | 条件 |
|------|------|------|
| `Avatar.lua:149` | `afterAllModelFinish()` | `#if UNITY_EDITOR` |
| `GameScene.cs:980` | 场景加载完成回调 | `#if UNITY_EDITOR` |
| `GameScene.cs:1052` | 场景卸载完成回调 | `#if UNITY_EDITOR` |

> **注意**：以上均为 Editor-only，生产环境不触发。但 Editor 调试时可能在 Terrain 流式加载高峰期触发，造成长时间卡顿。

---

## 常见结论与修复建议

| 症状 | 根因 | 修复方向 |
|------|------|---------|
| GC 时 PhysX 对象多 → 慢 | `MarkAllDependencies` 遍历 PhysicsManager 太慢 | 避免在大量 Terrain Collider 活跃时触发 `UnloadUnusedAssets` |
| IOService 反复争堆锁 | Shader cache 上传回调与 AGC 内存分配竞争 | 可降低 shader cache 并发上传数，减少堆锁争用 |
| Editor 调试时频繁卡住 | `#if UNITY_EDITOR` 路径在不合适时机触发 GC | 加 Guard：StreamingTerrain 活跃期间跳过或延迟 `UnloadUnusedAssets` |

---

## 关键路径速查

| 资源 | 路径 |
|------|------|
| Editor.log | `e:\WorkSpace\T3Trunk\client\logs\Editor.log` |
| Dump 输出 | `e:\WorkSpace\T3Trunk\client\logs\unity_hang.dmp` |
| PDB 目录 | `e:\WorkSpace\T3Trunk\unity\WindowsEditor` |
| Symbol cache | `C:\Symbols` |
| cdb.exe | `C:\Program Files\WindowsApps\Microsoft.WinDbg_1.2603.*_x64__*\amd64\cdb.exe` |
