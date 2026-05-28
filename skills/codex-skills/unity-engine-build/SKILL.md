---
name: unity-engine-build
description: Unity 引擎编译与构建日志诊断助手。Use when inspecting JN Workflow/Alfred engine build jobs such as jne/unity_build/mac_2022, checking Unity engine compile status, diagnosing failed macOS/Windows engine builds, reading Jenkins Console Output/workspace logs for native engine compilation, or analyzing errors from clang, xcodebuild, CMake, MSBuild, Bee, il2cpp, Unity editor/player build artifacts, 引擎编译, 引擎打包, mac_2022, unity_build.
---

# Unity Engine Build

## Coordination

- 先使用 `jn-workflow-log-diagnosis` 的通用流程访问 JN Workflow/Jenkins、判定状态、下载日志、扫描大文件。
- 本 skill 只补充 Unity 引擎编译领域判断。
- 使用 `chrome:Chrome` 访问登录态网页；触发新构建、停止构建、重试构建前必须确认。

## Known Entry Points

macOS 2022 引擎编译示例：

`https://jn-workflow.bytedance.net/alfred/projects/jne/jobs/jne/unity_build/mac_2022/-/?page=0&size=10`

常见页面动作：

- 列表页读取最近构建状态、构建号、触发人、分支/参数。
- 详情页进入 `Console Output`、`Workspace`、阶段日志或构建产物。
- 失败时下载 Jenkins workspace zip 或具体日志，不直接打开超大日志。

## Engine Build Diagnosis

优先搜索这些关键词：

- Native/C++：`clang: error`、`fatal error:`、`ld: error`、`Undefined symbols`、`duplicate symbol`
- Xcode/macOS：`xcodebuild`、`** BUILD FAILED **`、`CodeSign`、`provisioning profile`
- CMake：`CMake Error`、`CMake Generate step failed`
- Windows/MSBuild：`MSB`、`error C`、`LINK : fatal error`
- Unity build system：`Bee`、`Jam`、`il2cpp`、`UnityEditor`、`BuildFailedException`
- Environment：`No space left on device`、`Permission denied`、`file is locked`、`timeout`

判断顺序：

1. 先确认失败阶段：拉代码、准备环境、编译 C++、构建 Editor/Player、打包/归档、上传产物。
2. 再定位第一个真正导致构建停止的 compiler/build-system error。
3. 最后的 `exit code 1`、`BUILD FAILED`、`script returned exit code` 只是汇总，不当作根因。
4. 如果同一日志里有大量 warning，只引用最终失败 task 周围的 fatal/error 片段。
5. 对引擎升级相关问题，尽量区分：
   - 项目代码不兼容新引擎 API。
   - PackageRepo/包版本不兼容。
   - 引擎源码或构建脚本问题。
   - 机器环境/证书/缓存/磁盘问题。

## Report Format

输出：

```text
构建：<job/#build>
状态：<失败/成功/进行中>
失败阶段：<阶段名>
根因：<一句话>
关键日志：<短片段>
归类：<项目代码 / PackageRepo / 引擎源码 / 构建环境 / 暂不确定>
建议：<下一步检查或修复点>
```

如果只是学习一个新构建流程，记录：

- 入口 URL。
- 触发按钮/构建参数。
- 成功判定。
- 失败日志入口。
- 产物入口。
- 常见日志文件名和下载方式。
