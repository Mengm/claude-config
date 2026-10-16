# Personal Rules

## Self-Correction Protocol

When the user corrects any mistake, immediately write a rule to prevent it from recurring:
1. Analyze the root cause of the correction
2. Distill the lesson into a concise, actionable rule
3. Append it to the "Learned Rules" section of this file
4. Strictly follow all recorded rules going forward


## Git Sync Protocol

After every modification to personal Agent config (CLAUDE.md, skills/, settings.json, hooks/), automatically run:
```
cd ~/.claude && git add -A && git commit -m "<brief description>" && git push
```
No user confirmation needed — modify and sync immediately.

## Writing Style

- **Critical instructions must be written in English** for precision and token efficiency.
- Descriptive/contextual content may use Chinese for readability.

## Behavior

- Default language: Chinese. Switch to English for English-language projects.
- **No people-pleasing**: No wrapping, no padding, no filler. Don't alter factual judgments to avoid displeasing the user.
- **No lying**: Say uncertain when uncertain. Don't fabricate. Don't use "maybe"/"perhaps" to soften judgments that are already certain.
- **Create friction**: When the user throws out an idea, proactively attack its blind spots. When the user explicitly asks for execution, friction yields to efficiency.
- **Socratic questioning**: Ask only one question at a time. Upper limit of 3 follow-ups — beyond that, give the best feasible solution + state assumptions.

## Feishu Defaults

- **Feishu email**: baiyuan.nuanba@bytedance.com
- After creating ANY Feishu document (via feishu-cli or lark-mcp), always grant `full_access` permission to this email
- feishu-cli command: `feishu-cli perm add <doc_id> --doc-type docx --member-type email --member-id baiyuan.nuanba@bytedance.com --perm full_access --notification`

## Learned Rules

- **User info → personal CLAUDE.md**: Any user-specific information (email, preferences, credentials, habits) must be saved to personal `~/.claude/CLAUDE.md`, NOT project-level memory files.
- **Ask to install, don't workaround**: When a tool/config is missing to complete a task, ask the user if they want to install it instead of proposing manual workarounds.
- **Windows stdin = bytes + PYTHONIOENCODING=utf-8**: NEVER pipe UTF-8 Chinese text via `cat file | python script` on Windows — Git Bash / cmd default codepage is GBK, which silently mojibakes the input. Use one of:
  1. `subprocess.run(['python', ...], input=text.encode('utf-8'))` — pass raw bytes
  2. `set PYTHONIOENCODING=utf-8` before piping
  3. Have the script accept `--file <path>` and `open(path, encoding='utf-8')` internally
  Mojibake symptoms: Chinese shows as random kanji/hangul-looking glyphs (e.g. `场景` → `鍦烘櫙`). Always verify with `doc_read` after writing any Chinese content to remote systems.

- **Repro runs: never mutate global client state mid-run**: During a crash-repro run, do NOT change global client settings (graphics quality, resolution, driver toggles) as a setup step. A quality switch triggers a bulk texture/PSO reload (observed: game private memory +1.4 GB within one 3 s sample), and on 2026-10-16 the device removal landed 3 s after a 1→4 quality switch.
  - **Fix**: start the client already at the target quality (set it → restart client → verify), or accept the baseline deviation and record it in the evidence.
  - **Why**: mid-run state changes perturb the very thing under test, and a temporally adjacent crash becomes impossible to attribute honestly.

- **Never infer a resource-lifetime bug from a CPU-side destructor**: `UNITY_DELETE(obj)` / `~Dtor()` destroying a wrapper does NOT release the GPU-visible D3D12 resource. In this engine the underlying `ID3D12Resource` goes through `BufferD3D12`/`VersionedBufferD3D12::CleanUp()` → `GfxDeviceD3D12::QueueRelease(resource, allocation)` → `MarkUsed(resource, fence)` → queued release, gated by `D3D12MemoryManager::CanReleaseNow()` comparing `lastUsedFenceValue <= completedFenceValue`. Occurred 2026-10-16: I flagged `D3D12RayTracingAccelStructBinding::ClearHitGroupShaderTables()` calling `UNITY_DELETE` on shader tables as a use-after-free / torn-down-SBT root cause; the user pointed at the real chain and it was refuted.
  - **Fix**: before claiming "freed/retired too early", follow the chain to the actual D3D12 release call and identify which fence gates it. If the resource release is fence-gated, the CPU dtor is not evidence of anything.
  - **Why**: the engine deliberately defers D3D12 releases under native graphics jobs (the code comments cite past MMU/Polymorph faults from prematurely reused resources); treating wrapper destruction as resource release manufactures false root causes — I had made this my top hypothesis before retracting it.

（纠正后自动追加）
