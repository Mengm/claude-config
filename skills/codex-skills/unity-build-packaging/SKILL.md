---
name: unity-build-packaging
description: Unity/JN Workflow 打包流程助手。Use when working on Atom Unity engine upgrade packaging tests, triggering builds on JN Workflow/Alfred, checking Android/iOS build status, downloading Jenkins workspace logs such as BuildPlayer.log, diagnosing Unity/Gradle/Android packaging failures, or analyzing errors like apk miss, CommandInvokationFailure, Gradle build failed, Android namespace/package issues, Unity日志, 构建失败, 打包失败, 触发打包.
---

# Unity Build Packaging

## Core Rules

- 先叠加使用 `jn-workflow-log-diagnosis` 的通用网页访问、状态判定、Jenkins 日志下载和大日志扫描流程；本 skill 只补充 Unity 客户端打包领域判断。
- 面向用户默认用简体中文说明结论。
- 操作 JN Workflow/Alfred 这类登录态网页时，先加载并使用 `chrome:Chrome`。不要用命令行读取 Cookie、浏览器 Profile 或会话存储。
- 触发新打包前必须向用户确认；只读查看列表、详情、日志、下载日志不需要确认。
- 不要直接打开超大的 `BuildPlayer.log` 文本页；2GB+ 日志会卡住 Chrome 自动化。优先下载 zip 或链接另存为后本地分析。
- 下载或解压日志后，使用容错编码/二进制扫描，不要假设 `BuildPlayer.log` 是纯 UTF-8。
- 输出失败原因时区分“最终现象”和“根因”。例如 `.apk miss` 通常只是产物检查失败，真正根因要看前面的 Unity/Gradle 错误。

## JN Workflow Build Flow

Android trunk 打包页示例：

`https://jn-workflow.bytedance.net/alfred/projects/atom/jobs/atom/game/abp_online/atom_trunk/Android_j1_win12/-/?page=0&size=10`

常用操作：

1. 打开列表页，读取最近构建状态。
2. 触发打包时点顶部 `自定义构建`，检查 `立即构建` 表单参数，用户确认后点 `OK`。
3. 关键参数通常包括 `P4版本`、`清理增量缓存`、`清理BuildCache`、`开启Patch`、`项目配置区域`、`场景模式`、`引擎版本`、`固定版本号`、`PGO优化打包`、`打包平台`。
4. 判定状态：
   - `构建成功`：成功，通常有 `查看包体`，流程跑到 `制作patch / 上传GOPS / 创建ADP应用 / 后置任务处理`。
   - `构建失败`：失败，继续看阶段日志和 `BuildPlayer.log`。
   - `构建中止`：被停止或取消。
   - `打包管线开始 阶段`、`打包 阶段`：仍在进行中。

详情页入口：

- `Unity日志`：打开 Jenkins workspace 日志目录。
- `打包配置`：查看该次构建参数。
- `构建产物` / `查看包体`：成功后检查产物。
- 阶段日志里优先搜索 `ERROR`、`Exception`、`Traceback`、`Build Failed`、`CommandInvokationFailure`、`Gradle`、`apk miss`。

## Download Logs

Jenkins workspace 常见路径：

`https://jn-jenkins.bytedance.net/job/atom/job/game/job/abp_online/job/atom_trunk/job/Android_j1_win12/<BUILD_ID>/execution/node/5/ws/p4/client/logs/build/<BUILD_ID>/`

推荐下载方式：

1. 进入 `Unity日志` 打开的 Jenkins workspace 目录。
2. 优先点击底部 `(all files in zip)`。Chrome Playwright `waitForEvent("download")` 可拿到下载对象，随后调用 `download.path()` 获取本地路径。
3. 如果只要单个文件，手动或浏览器右键 `BuildPlayer.log` -> `链接另存为...`。
4. 不要左键打开 `BuildPlayer.log`；Chrome 会尝试加载整个大文本页，容易卡死。
5. 下载后只解出需要的日志：

```powershell
$out = "E:\Downloads\build87-log"
New-Item -ItemType Directory -Force -Path $out | Out-Null
tar -xf "E:\Downloads\87.zip" -C $out "87/BuildPlayer.log"
```

如果命令行直连 Jenkins 返回 `403`，说明需要 Chrome 登录态；继续使用浏览器下载。

## Analyze BuildPlayer.log

优先使用 bundled script：

```powershell
python ".agents\skills\unity-build-packaging\scripts\analyze_buildplayer_log.py" "E:\Downloads\build87-log\87\BuildPlayer.log"
```

分析顺序：

1. 扫最后一次 `FAILURE:`、`CommandInvokationFailure`、`Build failed`、`Build Failed`。
2. 看 Unity 调用栈对应阶段，例如 `ExportPlayer`、`PostProcessAndroidPlayer`、`Gradle.cs`。
3. 对 Gradle 失败，重点提取 `* What went wrong:`、失败 task、`stderr/stdout`。
4. 对 `.apk miss`，继续往前找 Unity/Gradle 原始错误。
5. 对编码报错，说明日志分析器本身读日志失败，但不要把它误判为打包根因，除非没有更早构建错误。

常见 Android 引擎升级失败模式：

- `Execution failed for task ':launcher:generateDebugBuildConfig'`
- `Package Name not found in ... launcher/src/main/AndroidManifest.xml, and namespace not specified`
- `Please specify a namespace ... via android.namespace`

这类通常表示升级后的 Android Gradle Plugin/Unity Android 构建链要求 `launcher` 模块有 `namespace`，但生成的 `launcher` Manifest 没有可推断 `package`，且 `launcher/build.gradle` 没有显式 `android { namespace ... }`。优先验证生成工程或 Gradle 模板是否补了：

```gradle
android {
    namespace 'com.hermes.atom'
}
```

## Report Format

结论要短而明确：

- 构建号、状态、下载/分析的日志路径。
- 最终现象：例如 `.apk miss`。
- 真正根因：引用关键 Gradle/Unity 错误。
- 修复方向：指出应该查生成的 Gradle 工程、Manifest、Gradle 模板或构建脚本的哪一类问题。
- 若日志里出现 token、ticket、cookie、secret 等环境变量，不要原样贴出。
