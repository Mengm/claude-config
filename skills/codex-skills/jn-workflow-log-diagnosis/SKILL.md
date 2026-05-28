---
name: jn-workflow-log-diagnosis
description: 通用 JN Workflow/Alfred/Jenkins 日志诊断流程。Use when Codex needs to access internal build/workflow web pages with Chrome login state, check job/build status, inspect Alfred/JN Workflow records, open Jenkins workspace or console logs, download large logs or all-files zip, analyze failed CI/build logs, or diagnose failures from links like jn-workflow.bytedance.net and jn-jenkins.bytedance.net. Triggers: JN Workflow, Alfred, Jenkins, Unity日志, 构建失败, 编译失败, 查看日志, 下载日志, BuildPlayer.log, Console Output, workspace, all files in zip.
---

# JN Workflow Log Diagnosis

## Core Rules

- 面向用户默认用简体中文。
- 对 `jn-workflow.bytedance.net`、`jn-jenkins.bytedance.net` 等需要登录态的网站，使用 `chrome:Chrome`；不要从本机读取 Cookie、浏览器 Profile、Local Storage。
- 只读查看状态、日志和下载日志不需要确认。点击会触发新构建、停止构建、重试阶段、提交表单前必须向用户确认。
- 不要直接打开 100MB+ 的文本日志页面；优先下载 zip 或文件后在本地扫描。
- 下载日志后用二进制/容错编码扫描；不要假设日志是 UTF-8。
- 汇报时区分“页面显示状态 / 最终失败现象 / 原始根因 / 建议下一步”。
- 输出日志片段时屏蔽 token、ticket、cookie、secret、password、credential 等敏感环境变量。

## Workflow

1. 打开用户给的 JN Workflow/Alfred 链接。
2. 读取列表页或详情页状态：
   - `构建成功` / `成功`：成功。
   - `构建失败` / `失败`：失败，继续查日志。
   - `构建中止` / `已取消`：中止。
   - `构建中` / `阶段` / `运行中`：仍在执行。
3. 在详情页找日志入口，常见入口：
   - `Unity日志`
   - `工作区`
   - `Console Output`
   - Jenkins `Workspace`
   - Jenkins `Open Blue Ocean`
4. 先读页面可见阶段日志，搜索 `ERROR`、`Exception`、`Traceback`、`FAILURE:`、`FAILED`、`exit code`、`Build failed`、`CommandInvokationFailure`。
5. 如果页面日志不足，进入 Jenkins workspace 下载日志。
6. 本地分析日志，输出根因和修复方向。

## Download Strategy

优先顺序：

1. Jenkins workspace 底部 `(all files in zip)`：
   - 用 Chrome 的 `waitForEvent("download")` 等待下载。
   - 对返回的 download 对象调用 `path()` 获取本地路径。
2. 单文件链接右键 `链接另存为...`，适合只要 `BuildPlayer.log`、`consoleText`、`Editor.log` 等大文件。
3. 小文件可直接打开 `*view*` 或点击文件名读取。

不要左键打开大日志文件，例如 2GB+ `BuildPlayer.log`。Chrome 会尝试渲染整页文本，可能导致自动化卡死。

Jenkins workspace 常见 zip 链接形式：

`./*zip*/<build-id>.zip`

解压单个日志示例：

```powershell
$out = "E:\Downloads\workflow-log"
New-Item -ItemType Directory -Force -Path $out | Out-Null
tar -tf "E:\Downloads\87.zip" | Select-String -Pattern "BuildPlayer|Editor|console|log"
tar -xf "E:\Downloads\87.zip" -C $out "87/BuildPlayer.log"
```

## Local Log Scan

优先使用 bundled script：

```powershell
python ".agents\skills\jn-workflow-log-diagnosis\scripts\scan_large_log.py" "E:\Downloads\workflow-log\some.log"
```

指定额外关键字：

```powershell
python ".agents\skills\jn-workflow-log-diagnosis\scripts\scan_large_log.py" "E:\Downloads\workflow-log\some.log" --pattern "xcodebuild" --pattern "clang:" --pattern "CMake Error"
```

扫描原则：

- 优先看最后几次高信号错误，而不是第一个 `Error`。
- `exit code 1`、`.apk miss`、`script returned exit code 1` 往往是最终现象；继续向前找原始错误。
- 如果日志分析脚本自身出现 `UnicodeDecodeError`，这是日志读取问题，不一定是构建根因。
- 产物检查失败时，查更早的编译、导出、打包、上传阶段。

## Report Format

使用这个格式：

```text
构建：<任务名/#build-id>
状态：<成功/失败/中止/进行中>
日志：<本地路径或 Jenkins 入口>

结论：
<一句话根因>

关键日志：
<最短必要片段，屏蔽敏感行>

下一步：
<建议检查的配置、脚本、工程文件或重试方式>
```
