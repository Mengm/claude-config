---
name: gpm-crash-analysis
description: >-
  GPM 崩溃分析。通过 GPM API 获取崩溃详情、符号化堆栈、原始崩溃日志，并进行根因分析。
  当用户提供 GPM 崩溃链接（gpm.bytedance.com）、说"分析崩溃"、"crash analysis"、
  "崩溃堆栈"、"看下这个 crash"、"GPM" 时使用。支持 iOS/Android。
  Skill 自包含：脚本、依赖声明、登录工具全在 skill 目录内。
  Cookies 存储在 skill 目录的 cookies.json，跨项目共享。
argument-hint: <GPM_CRASH_URL>
user-invocable: true
allowed-tools: Bash, Read
---

# GPM 崩溃分析

通过 GPM API 获取崩溃详情和符号化堆栈，进行根因分析。无需打开浏览器（登录除外）。

## Skill 目录结构

```
skills/gpm-crash-analysis/
├── SKILL.md                # 本文件
├── gpm-api.js              # API 客户端（零额外依赖，Node 18+ 内置 fetch）
├── gpm-login.js            # SSO 登录方式 A：Playwright 浏览器扫码（仅登录时需要）
├── gpm-chrome-cookies.py   # SSO 登录方式 B：从系统 Chrome 读取 cookies（零交互）
├── package.json            # 依赖声明（playwright）
├── cookies.json            # 登录后自动生成，有效期 15-30 天
└── node_modules/           # npm install 后生成（仅 Playwright 登录需要）
```

## 定位 Skill 目录

执行任何操作前，先定位 skill 目录路径。skill 在项目的 `skills/gpm-crash-analysis/` 下：

```bash
# 方法 1：从当前项目定位
SKILL_DIR="$(pwd)/skills/gpm-crash-analysis"

# 方法 2：通过 find 定位（跨项目）
SKILL_DIR=$(find / -path "*/skills/gpm-crash-analysis/gpm-api.js" -printf "%h" -quit 2>/dev/null)

# 方法 3：已知项目路径
SKILL_DIR="f:/bytegit/feishu-cli-1.8.2/skills/gpm-crash-analysis"
```

后续所有命令中使用 `$SKILL_DIR` 引用。

## 执行流程

### Step 1: 前置检查

```bash
# 检查脚本
test -f "$SKILL_DIR/gpm-api.js" && echo "OK:scripts" || echo "MISSING:scripts"

# 检查 cookies（skill 目录优先，回退 ~/.gpm/）
test -f "$SKILL_DIR/cookies.json" -o -f "$USERPROFILE/.gpm/cookies.json" && echo "OK:cookies" || echo "MISSING:cookies"

# 检查 Node.js
node --version 2>/dev/null && echo "OK:node" || echo "MISSING:node"
```

### Step 2: 如果缺少 cookies → 认证

提供两种方式，按优先级选择：

#### 方式 A：从 Chrome 读取（推荐，零交互）

前提：用户已在系统 Chrome 中登录过 gpm.bytedance.com。

```bash
# 需要 browser_cookie3（首次）: pip install browser_cookie3
python "$SKILL_DIR/gpm-chrome-cookies.py"
```

如果报 "No cookies found"，说明 Chrome 里没有 GPM 登录态，需要用户先在 Chrome 打开 https://gpm.bytedance.com 登录一次，然后重新运行。

如果报 "Unable to get key for cookie decryption"，可能是 Chrome 正在运行导致 DB 锁定，让用户关闭 Chrome 再试。

#### 方式 B：Playwright 浏览器扫码

当 Chrome 读取不可用时（无 Chrome、未登录、cookie 加密问题等），使用 Playwright 打开独立浏览器进行飞书扫码登录：

```bash
# 安装 Playwright（首次）
cd "$SKILL_DIR" && npm install

# 登录：打开浏览器完成飞书扫码，cookies 自动保存到 skill 目录
SKILL_DIR="$SKILL_DIR" node "$SKILL_DIR/gpm-login.js"
```

提示用户：浏览器会打开飞书 SSO 登录页，扫码后 cookies 自动保存，有效期 15-30 天。

### Step 3: 调用 API 获取崩溃数据

```bash
node "$SKILL_DIR/gpm-api.js" '<GPM_URL>' 2>&1
```

**输入**: 完整 GPM 崩溃 URL，格式：
```
https://gpm.bytedance.com/app/abnormal/detail/crash/<issue_id>?aid=<aid>&os=<os>&start_time=...&end_time=...
```

**输出**:
1. Issue 概要（状态、备注、标题）
2. 崩溃事件数量
3. 符号化堆栈（崩溃线程完整调用栈）
4. 保存文件路径：`./gpm-output/crash-<id>-full.json` 和 `crash-<id>.txt`

**如果返回 401**: cookies 过期，重新执行 Step 2 登录。

### Step 4: 读取完整数据做深度分析

```bash
# 读取完整结构化数据
Read gpm-output/crash-<id>-full.json
```

JSON 中的关键字段：
- `events[0].event_detail.main_thread.backtrace` — 符号化崩溃线程堆栈
- `events[0].event_detail.other_threads` — 其他线程堆栈
- `events[0].event_detail.detail` — 崩溃点函数
- `log.data` — 原始崩溃日志（未符号化，包含所有线程）
- `log.custom` — 自定义字段（场景、服务器、GPU、SDK 版本等）
- `log.header` — 设备信息（机型、OS、App 版本、SDK 版本）
- `log.crash_detail` — 崩溃类型、fault_address、mach_code

### Step 5: 崩溃根因分析

按以下框架分析：

#### 5.1 崩溃签名
- 异常类型 + 崩溃点函数名 + 偏移

#### 5.2 堆栈解读
- 区分 **App 代码帧**（UnityFramework / BD_GameSDK 等）和 **系统帧**（UIKit / CoreFoundation 等）
- 最顶层的 App 代码帧 = 最可能的崩溃根因
- 分析调用链逻辑

#### 5.3 崩溃类型速查

| 类型 | 特征 | 常见原因 |
|------|------|----------|
| SIGSEGV (EXC_BAD_ACCESS) | 访问无效地址 | 野指针、UAF、空指针+偏移 |
| SIGABRT | 主动 abort | assert 失败、uncaught exception |
| SIGBUS | 总线错误 | 内存对齐、mmap 失败 |
| OOM | Jetsam / 内存不足 | 内存泄漏、大资源加载 |
| Watchdog | 超时 kill | 主线程阻塞 |

#### 5.4 fault_address 解读
- `0x0` ~ `0xFFF` → 空指针 + 成员偏移（对象已释放）
- 很大的值 → 野指针 / UAF
- 对齐地址 → 可能是有效对象被覆写

#### 5.5 结论输出格式

```
## 崩溃分析结论

**根因**: 一句话总结
**崩溃点**: 函数名 + 偏移
**调用链**: 关键调用路径
**影响**: 版本/设备/用户量
**修复建议**: 具体代码修改方向
**优先级**: P0-P3
```

## GPM API 参考

| API | 用途 |
|-----|------|
| `/v2/api/app/crash/issue/detail` | Issue 概要（状态、备注） |
| `/v2/api/app/crash/event/list` | 事件列表 + **符号化堆栈**（在 event_detail 字段） |
| `/v2/api/app/crash/event/log/get` | 原始崩溃日志（未符号化，全线程） |
| `/v2/api/app/crash/issue/group_dimensions` | 可筛选维度列表 |
| `/v2/api/app/crash/issue/field/percent` | 字段分布（设备/OS/版本占比） |
| `/v2/api/app/crash/issue/field/aggr` | 字段聚合（内存/磁盘均值） |
| `/v2/api/app/crash/filter_dimensions` | 筛选维度枚举值 |

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `MISSING:scripts` | skill 目录定位失败 | 确认项目包含 `skills/gpm-crash-analysis/` |
| `MISSING:cookies` | 未登录 | 执行 Step 2 登录 |
| `401 Unauthorized` | cookies 过期 | 重新执行 Step 2 登录 |
| `No events found` | 时间范围无数据 | URL 中添加/调整 start_time & end_time |
| `Cannot find module playwright` | 未安装依赖 | `cd $SKILL_DIR && npm install` |
| `ECONNREFUSED` | 网络问题 | 检查 VPN / 内网连接 |
