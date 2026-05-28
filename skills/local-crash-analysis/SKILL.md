---
name: local-crash-analysis
description: >-
  Unity 本地崩溃分析（离线）。解析本地 crash.dmp + Player.log + PDB 文件，还原崩溃线程堆栈、异常类型，
  提取 Player.log 上下文和 Lua 调用栈，进行根因分析。
  触发场景：(1) 用户提供 crash.dmp 文件 (2) "分析本地崩溃" (3) "PC 崩溃" "Editor 崩溃" (4) 用户给出含 dmp/pdb 的文件夹路径。
  支持：PC 包体崩溃（GameAssembly.pdb）和 Unity Editor 崩溃。
  不需要网络连接，纯本地分析。
argument-hint: <crash_folder_path> [--metadata <global-metadata.dat路径>]
user-invocable: true
allowed-tools: Bash, Read
---

# Unity 本地崩溃分析（离线）

解析 `crash.dmp` + `Player.log` + PDB 文件，还原崩溃堆栈并进行根因分析。**无需网络，完全离线**。

## Skill 目录结构

```
skills/local-crash-analysis/
├── SKILL.md                 # 本文件
├── scripts/
│   └── analyze_crash.py     # 主分析脚本（minidump + pdbparse）
└── requirements.txt         # pip 依赖
```

## 输入文件说明

| 文件 | 必须 | 说明 |
|------|------|------|
| `crash.dmp` | ✅ | Windows Minidump，崩溃现场快照 |
| `Player.log` | ✅ | Unity 运行日志，含 Lua 调用栈和最后日志 |
| `UnityPlayer.pdb` | ✅ | Unity 引擎层符号（UnityPlayer.dll 对应） |
| `GameAssembly.pdb` | PC包才有 | IL2CPP 游戏代码符号，Editor 崩溃没有 |
| `GameAssembly.dll` | PC包才有 | IL2CPP 游戏代码（用于模块基址匹配） |
| `UnityPlayer.dll` | PC包才有 | Unity 引擎 DLL（用于模块基址匹配） |
| `global-metadata.dat` | 可选 | 还原 IL2CPP 方法名为完整 C# 签名 |

**崩溃类型自动识别**：有 `GameAssembly.pdb` → PC 包体崩溃；无 → Editor 崩溃。

## 执行流程

### Step 1: 定位 Skill 目录

```bash
SKILL_DIR=$(find / -path "*/skills/local-crash-analysis/scripts/analyze_crash.py" -printf "%h" -quit 2>/dev/null)
# 或直接使用已知路径
SKILL_DIR="$USERPROFILE/.claude/skills/local-crash-analysis/scripts"
```

### Step 2: 前置检查

```bash
# 检查脚本
test -f "$SKILL_DIR/analyze_crash.py" && echo "OK:scripts" || echo "MISSING:scripts"

# 检查 Python + 依赖
python --version 2>/dev/null && echo "OK:python" || echo "MISSING:python"
python -c "import minidump, pdbparse" 2>/dev/null && echo "OK:deps" || echo "MISSING:deps"
```

如果缺少依赖，执行：
```bash
pip install -r "$SKILL_DIR/../requirements.txt"
```

### Step 3: 运行崩溃分析

```bash
python "$SKILL_DIR/analyze_crash.py" "<crash_folder_path>"
```

**带 global-metadata.dat**（可选，还原完整 C# 方法名）：
```bash
python "$SKILL_DIR/analyze_crash.py" "<crash_folder_path>" --metadata "<global-metadata.dat路径>"
```

**输出**：
1. 终端打印完整分析报告
2. 保存到 `<crash_folder>/crash-report.txt`

### Step 4: 读取报告做深度分析

```bash
Read <crash_folder>/crash-report.txt
```

报告关键字段：
- `💥 异常信息` — 异常类型（ACCESS_VIOLATION / STACK_OVERFLOW 等）+ 崩溃地址
- `📚 崩溃线程堆栈` — 符号化调用栈（模块!函数名 + 偏移）
- `📄 Player.log 上下文` — 崩溃前最后 30 行日志
- `🔷 Lua 调用栈` — 最后捕获的 Lua 堆栈（如有）
- `⚠️ 关键错误` — 日志中的 ERROR/Exception 行

### Step 5: 崩溃根因分析

按以下框架分析报告内容：

#### 5.1 异常类型速查

| 异常码 | 类型 | 常见原因 |
|--------|------|----------|
| 0xC0000005 | ACCESS_VIOLATION | 野指针/空指针 + 偏移、UAF（Use-After-Free） |
| 0xC00000FD | STACK_OVERFLOW | 递归无终止条件、大型局部变量 |
| 0xC0000374 | HEAP_CORRUPTION | 写越界、double free |
| 0xE06D7363 | C++ EXCEPTION | 未捕获的 C++ 异常（`std::bad_alloc` 等） |
| 0x80000003 | BREAKPOINT | assert 失败、`__debugbreak()` |
| 0xC0000094 | DIVIDE_BY_ZERO | 除零 |

#### 5.2 堆栈解读

- 区分 **游戏帧**（`GameAssembly.dll`）和 **引擎帧**（`UnityPlayer.dll`）和 **系统帧**（`ntdll`/`kernel32`）
- 最顶层的游戏帧（`GameAssembly!XxxComponent_YyyMethod`）= 最可能的崩溃根因
- IL2CPP 符号格式：`ClassName_MethodName_mXXXXX` → 对应 C# 类 `ClassName.MethodName`

#### 5.3 崩溃地址解读

- `0x0000000000000000` ~ `0x00000000000000FF` → 空指针 + 成员偏移（对象已被 GC 或提前释放）
- `0xCDCDCDCD...` → 未初始化内存（Debug 构建特有）
- 很大的值（如 `0xFFFFFFFFFFFFFFFF`）→ 野指针 / UAF
- 与某模块基址对齐 → 可能是虚表被覆写

#### 5.4 Lua 调用栈与 Player.log 关联

- 如果有 Lua 堆栈，优先确认崩溃发生的游戏逻辑上下文（哪个场景、哪个功能）
- Player.log 最后日志揭示崩溃前的游戏状态（场景加载、资源请求等）

#### 5.5 结论输出格式（参考 GPM 风格）

```
## 崩溃分析结论

**根因**   : 一句话总结（如：SkillComponent 空指针访问，对象在技能释放时已被销毁）
**崩溃点** : GameAssembly.dll!SkillComponent_OnHit_m12345 + 0x24
**调用链** : OnHit → ProcessDamage → GetTarget → [NULL 访问]
**Lua 上下文**: 最后 Lua 调用（场景/功能）
**修复建议**: 具体代码修改方向（如：在 OnHit 开头增加 entity 有效性检查）
**优先级** : P0-P3
```

## 常见问题

| 问题 | 原因 | 处理 |
|------|------|------|
| `堆栈提取失败` | minidump walker 不支持该 dmp 格式 | 脚本自动回退到原始栈扫描 |
| `PDB 符号为空` | PDB 版本与 DLL 不匹配 | 确认 PDB 来自同一构建 |
| `无法导入 minidump` | 依赖未安装 | `pip install minidump pdbparse` |
| `IL2CPP 函数名含 _mXXXX` | 正常，IL2CPP 生成的 token | 提供 global-metadata.dat 可得到完整 C# 名 |
| `Player.log 为空` | Editor 模式路径不同 | 手动指定 log 路径 `--log <path>` |
