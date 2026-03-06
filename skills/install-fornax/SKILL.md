# install-fornax

Install and configure Fornax Trace integration for Claude Code. This skill sets up automatic tracing of all Claude Code interactions to ByteDance's Fornax observability platform.

## Instructions

When the user invokes this skill, follow these steps in order:

### Step 1: Collect required information

Ask the user for the following (skip any they've already provided):
- `FORNAX_AK` — Fornax space Access Key
- `FORNAX_SK` — Fornax space Secret Key
- `FORNAX_REGION` — Fornax region (default: `CN`)

### Step 2: Install Fornax SDK

```bash
pip install --upgrade bytedance.fornax --index-url=https://bytedpypi.byted.org/simple/
pip install tiktoken --index-url=https://bytedpypi.byted.org/simple/
```

`tiktoken` is an indirect dependency required by the `cozeloop → langchain` chain within the Fornax SDK.

Verify the installation:
```bash
python -c "from bytedance.fornax.infra import initialize; print('OK')"
```

If the `python` command is not found, try `python3`. Note which command works — it must match in the hook configuration (Step 4).

### Step 3: Install the hook script

Create `~/.claude/hooks/` directory if it doesn't exist, then write `fornax_hook.py` there.

The hook script source is at: `C:\Users\Admin\Downloads\fornax_hook.py`

```bash
mkdir -p ~/.claude/hooks
cp "C:\Users\Admin\Downloads\fornax_hook.py" ~/.claude/hooks/fornax_hook.py
chmod +x ~/.claude/hooks/fornax_hook.py
```

If the source file is not found, ask the user to provide the `fornax_hook.py` file path.

### Step 4: Configure global Stop hook

Read `~/.claude/settings.json`, then add (merge, not replace) the following `hooks` section:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/hooks/fornax_hook.py"
          }
        ]
      }
    ]
  }
}
```

**Important**: Use the same `python` command that was verified in Step 2. If `python3` was needed, use `python3` here.

Preserve all existing fields in `settings.json`. Only add/merge the `hooks` key.

### Step 5: Configure project environment variables

Read the current project's `.claude/settings.local.json`, then add (merge, not replace) the following `env` section using the credentials collected in Step 1:

```json
{
  "env": {
    "TRACE_TO_FORNAX": "true",
    "FORNAX_AK": "<user-provided>",
    "FORNAX_SK": "<user-provided>",
    "FORNAX_REGION": "<user-provided, default CN>"
  }
}
```

Preserve all existing fields in `settings.local.json`. Only add/merge the `env` key.

### Step 6: Verify and report

Run a final import check:
```bash
python -c "from bytedance.fornax.infra import initialize; print('Fornax SDK OK')"
```

Then summarize what was done and remind the user:
- The hook takes effect on the **next** Claude Code session (restart required).
- To enable debug logging, add `"CC_FORNAX_DEBUG": "true"` to the project env.
- To disable tracing for a specific project, set `"TRACE_TO_FORNAX": "false"` in that project's `.claude/settings.local.json`.
