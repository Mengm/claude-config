---
name: crash-debug
description: >
  Systematic debugging protocol for crashes, memory corruption, race conditions,
  and other complex low-level bugs in Unity Engine (2022.3) C++ / C# codebase.
  Use this skill whenever the user reports or investigates: native crashes, editor
  freezes, segfaults, access violations, use-after-free, data races, deadlocks,
  Job System safety errors, or any non-trivial runtime failure. Trigger phrases
  include "crash", "崩溃", "闪退", "race condition", "竞态", "corruption",
  "内存损坏", "死锁", "deadlock", "access violation", "segfault", "调试崩溃",
  or /crash-debug. Do NOT trigger for simple build errors, compile failures,
  or straightforward logic bugs that don't involve crashes or undefined behavior.
---

# Crash Debug Protocol

You are entering **diagnostic mode**. Your primary objective is to find the **root cause**, not to propose a quick fix. A wrong fix shipped is worse than no fix — it hides the real bug and creates a second one.

## The Cardinal Rule

**NEVER propose a fix before completing Steps 1–4.** If you catch yourself wanting to say "try adding a null check here" before you've traced the full call chain and formed a hypothesis, stop. Go back to Step 1.

---

## 6-Step Diagnostic Protocol

### Step 1: Read the Actual Error

Read the full error output — not a summary, not just the exception type. The answer is almost always in the details you'd skip.

**What to read, in order:**
1. **Editor.log** — search backward from the end for `crash`, `fatal`, `exception`, `assert`, `abort`. The last 200 lines before crash often contain the smoking gun.
2. **Crash dump / stack trace** — read the ENTIRE native stack, not just the top frame. The bug is often 3-5 frames deep.
3. **Console errors preceding the crash** — crashes are often preceded by warnings that reveal the setup conditions.

**Tool sequence:**
```
Read Editor.log (last 500 lines) →
Grep for "crash|fatal|exception|assert|ABORT|stacktrace|====" →
Identify the crash point (file:line or symbol name)
```

**What to extract:**
- Exact crash address / assertion message
- Thread ID — is this the main thread or a worker?
- The object/pointer that's invalid — is it null, dangling, or corrupted?
- Any preceding log lines that show what operation was in progress

### Step 2: Trace the Call Chain

Starting from the crash site, read each function upward through the call chain. Don't guess what a function does — read it.

**Tool sequence:**
```
Grep for the crashing function name → Read the source file →
Identify the caller → Read the caller → Repeat until you reach the entry point
```

**Key questions at each frame:**
- What are the preconditions this function assumes?
- Which argument or member could be the invalid value?
- Is there a thread safety assumption? (check for `AssertForMainThread()`, `Mutex::AutoLock`, `atomic`)
- Is this code path reachable from multiple threads?

### Step 3: Check Recent Changes

The bug is very likely in recently changed code. Check git history for all files in the call chain.

```bash
git log --oneline -20 -- <file1> <file2> ...
git log --oneline --since="2 weeks ago" -- <directory/>
```

If a recent commit touches the crash area, read the full diff:
```bash
git show <commit-hash> -- <file>
```

### Step 4: Form a Hypothesis

Before writing any fix, state your hypothesis explicitly:

> **Root cause hypothesis:** [What exactly is wrong and why]
> **Evidence:** [What you observed that supports this]
> **What this predicts:** [If this hypothesis is correct, what else should be true?]

Then verify the prediction. For example:
- If you think it's a race condition, identify the two threads and the unprotected shared state
- If you think it's use-after-free, find where the object is freed and where the dangling pointer is retained
- If you think it's a null pointer, trace backward to find why the value is null — don't just add a null check

### Step 5: Propose a Minimal Fix

Only now may you propose a fix. The fix must:
- Address the root cause, not the symptom
- Be minimal — change only what's necessary
- Not introduce new assumptions about thread safety or lifetime

**Anti-patterns to avoid:**
- Adding a null check without understanding why it's null → hides the real bug
- Adding a lock without understanding the lock ordering → risks deadlock
- Copying data "just to be safe" → hides lifetime issues, adds perf cost

### Step 6: Verify the Fix Won't Break Invariants

Before declaring done:
1. **Check all callers** of any modified function — use Grep to find every call site
2. **Check the reverse direction** — if you changed how A calls B, also check what calls A
3. **Check sibling code paths** — if you fixed the Update path, check FixedUpdate, LateUpdate
4. **Run related tests** if available:
   ```bash
   run test native <relevant_test_name>
   ```

---

## The 2-Attempt Rule

If your first two fix attempts fail (the crash persists or moves), **stop and reset**:

1. Re-read the crash from scratch — your mental model is probably wrong
2. Ask yourself: "Am I looking at the right layer?"
   - Is this a C++ issue surfacing through C# bindings?
   - Is this a threading issue disguised as a data integrity bug?
   - Is this a build configuration issue (release vs debug, IL2CPP vs Mono)?
3. Widen the search: check if other engineers have hit this pattern (search commit messages, comments)
4. If still stuck, tell the user what you know vs. what you're assuming, and ask for more context

---

## Unity-Specific Crash Patterns

### C++ / C# Boundary Issues

The managed/native boundary is a major source of crashes:

- **GC relocation during native calls** — If C# passes a managed object reference to C++ and GC runs during the native call, the pointer becomes invalid. Look for `GCHandle`, `pin_ptr`, `fixed` statements.
- **Marshalling type mismatches** — struct layout differences between C# and C++ (packing, alignment, bool size). Check `[StructLayout]` attributes and `BIND_MANAGED_TYPE_NAME()` macros.
- **Calling destroyed objects** — C# wrapper alive but native object already destroyed. Look for m_InstanceID checks and `Object::IsNullOrDestroyed()`.
- **Script binding generation** — `*.bindings` files generate `*.gen.cs`. If the generated code is stale, types can mismatch. Check if `*.bindings` was modified without regeneration.

### Job System & Threading

- **NativeContainer safety** — Jobs can only access `NativeArray`, `NativeList` etc. with correct `[ReadOnly]` / `[WriteOnly]` attributes. Missing attributes → race conditions that manifest as random data corruption.
- **Safety handles** — `AtomicSafetyHandle` errors mean a container is being accessed from the wrong context (wrong job, main thread during job execution, or after disposal). Read the exact error message — it tells you the violation type.
- **Job dependencies** — Missing `JobHandle` dependencies let jobs run concurrently when they shouldn't. Trace the `Schedule()` calls and verify the dependency chain.
- **Main thread assertions** — Many Unity APIs can only be called from the main thread. If you see `AssertForMainThread()` or `VerifyMainThread()` in the stack, the issue is threading, not the API itself.

### Memory Corruption Heuristics

When the crash looks like corrupted data (nonsensical values, crashes in allocator code, heap validation failures):

- **Use-after-free signs:** crash in destructor, crash accessing a vtable pointer (0xfeeefeee on Windows = freed heap memory), object fields contain 0xcdcdcdcd (uninitialized heap) or 0xdddddddd (freed heap in debug builds).
- **Buffer overrun:** crash in adjacent allocation, allocator metadata corruption, crash happens in `free()`/`delete` rather than at the point of overrun. Check array index bounds, string operations, memcpy sizes.
- **Allocator mismatch:** Unity uses typed allocators (TLS, Frame, Persistent, Temp). Allocating with one and freeing with another corrupts the allocator state. Check `MemoryManager` allocator labels.
- **Double-free:** crash in allocator with a valid-looking pointer. Add logging to both free sites to find the duplicate.

### Lock Ordering & Deadlocks

If the editor freezes (not crashes):
1. Check if it's a deadlock — are multiple threads waiting on locks?
2. Unity's lock ordering: lower-level systems must not call into higher-level systems while holding a lock
3. Look for nested lock acquisitions — `Mutex::AutoLock` inside another `Mutex::AutoLock` scope

---

## Diagnostic Output Format

When presenting your findings, structure them as:

```
## Crash Analysis

**Crash site:** <file:line> — <function name>
**Thread:** <main thread / worker N / job system>
**Immediate cause:** <what value/state is invalid>

## Call Chain
<numbered list of relevant frames with key observations>

## Root Cause Hypothesis
<clear statement of why this happens>

## Evidence
<what you observed that supports this>

## Proposed Fix
<minimal diff with explanation>

## Verification
<what callers you checked, what tests confirm the fix>
```
