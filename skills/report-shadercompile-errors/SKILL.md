---
name: report-shadercompile-errors
description: Collect Unity shadercompile or BuildPlayer log `Shader error` entries, identify affected shaders, platforms, passes, kernels, source lines, and keyword variants, generate a Chinese Markdown report, and optionally import that Markdown as a Feishu/Lark online doc. Use when the user provides a shader compile log and asks to list shader errors, variants, export a report, translate the report to Chinese, or upload the report to Feishu.
---

# Report Shadercompile Errors

Use this skill to turn a Unity shader compile log into a concise Chinese Markdown report, then upload the report to Feishu when requested.

## Workflow

1. Confirm the input log path exists.
2. Generate the Chinese Markdown report with `scripts/collect_shadercompile_errors.py`.
3. Inspect the top of the report and at least one summary row before delivering.
4. If upload is requested, import the Markdown as a Feishu online document through `lark-drive`.

## Generate Report

Run the bundled script from any working directory:

```powershell
python C:\workflow\skills\report-shadercompile-errors\scripts\collect_shadercompile_errors.py `
  "C:\Users\Admin\Downloads\shadercompile.log" `
  --out "C:\workflow\ShaderReport\shadercompile_errors_YYYYMMDD.md"
```

Default behavior:

- Output language is Chinese.
- Shader names, keywords, kernel names, file paths, and compiler messages stay in original text for searchability.
- Texture-count errors that include `for keywords : ...` are listed as exact keyword/platform variant records.
- Compute errors are grouped by shader + platform + kernel + file line because Unity does not print keywords for them.
- Other errors are grouped by shader + platform + compiler message + file/program hint.
- Identical records are collapsed with occurrence counts and source log line ranges.

For a quick parse check without writing a report:

```powershell
python C:\workflow\skills\report-shadercompile-errors\scripts\collect_shadercompile_errors.py `
  "C:\Users\Admin\Downloads\shadercompile.log" `
  --summary-only
```

## Upload To Feishu

When the user asks to upload the Markdown report:

1. Use the `lark-drive` skill and read its shared auth rules.
2. Import as a docx cloud document, not as a plain file attachment.
3. Run `drive +import` from the report directory and pass a relative `--file`; absolute paths can trigger CLI path-safety failures.

Example:

```powershell
Set-Location C:\workflow\ShaderReport
lark-cli drive +import --as user --type docx --file .\shadercompile_errors_YYYYMMDD.md --name "Shader 编译错误报告 YYYYMMDD"
```

If `need_user_authorization` or a scope error appears, follow `lark-shared`:

```powershell
lark-cli auth login --domain drive --no-wait --json
```

Show the returned `verification_url` to the user if the normal auth link is not visible, complete the device-code flow, then retry the same `drive +import`.

## Reporting Rules

- Lead with counts: matched `Shader error` lines, de-duplicated records, exact keyword/platform records, and unique keyword sets.
- Clearly separate `keyword set` from `platform variant record`; the same keywords can fail on both `d3d11` and `d3d12`.
- Do not claim keywords for errors where the log did not print them. Mark those as `log 未打印 keywords`.
- Keep the local Markdown path and Feishu URL in the final response.
