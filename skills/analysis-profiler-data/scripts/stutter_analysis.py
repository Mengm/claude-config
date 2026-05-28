#!/usr/bin/env python3
"""Unity Profiler stutter/lag frame analyzer."""

import sys
import os
import statistics
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unity_profiler_parser import UnityProfilerParser


def get_deep_hotspots(samples, min_time_ms=0.5):
    """Get all markers above threshold with their depth in the call tree."""
    results = []
    depth = 0
    remaining_children = []

    for s in samples:
        while remaining_children and remaining_children[-1] == 0:
            remaining_children.pop()
            depth -= 1

        time_ms = s.duration_ns / 1_000_000.0
        if time_ms >= min_time_ms:
            results.append((s.marker_name, time_ms, depth))

        if remaining_children:
            remaining_children[-1] -= 1

        if s.child_count > 0:
            remaining_children.append(s.child_count)
            depth += 1

    return results


def build_call_tree_string(samples, max_depth=4, min_time_ms=0.5):
    """Build indented call tree string for a frame's main thread."""
    lines = []
    depth = 0
    remaining_children = []

    for s in samples:
        while remaining_children and remaining_children[-1] == 0:
            remaining_children.pop()
            depth -= 1

        time_ms = s.duration_ns / 1_000_000.0
        if time_ms >= min_time_ms and depth <= max_depth:
            indent = "  " * depth
            lines.append(f"{indent}{s.marker_name}: {time_ms:.3f} ms")

        if remaining_children:
            remaining_children[-1] -= 1

        if s.child_count > 0:
            remaining_children.append(s.child_count)
            depth += 1

    return "\n".join(lines)


def find_main_thread(frame):
    """Find the main thread in a frame."""
    for t in frame.threads:
        if t.thread_name == "" and t.group_name == "":
            return t
        if "Main Thread" in t.thread_name or t.group_name == "Main Thread":
            return t
    return frame.threads[0] if frame.threads else None


def analyze_stutter_frames(data_file, output_file=None):
    print(f"Parsing {data_file}...")
    parser = UnityProfilerParser(data_file)
    parser.parse()
    frames = parser.frames

    if not frames:
        print("No frames parsed!")
        return

    # Calculate frame times from main thread root sample
    frame_data = []  # (frame, main_thread, frame_time_ms)
    for f in frames:
        mt = find_main_thread(f)
        if mt and mt.samples:
            root_time_ms = mt.samples[0].duration_ns / 1_000_000.0
            frame_data.append((f, mt, root_time_ms))
        else:
            frame_data.append((f, mt, 0.0))

    times_only = [t for _, _, t in frame_data if t > 0]
    if not times_only:
        print("No valid frame times found!")
        return

    avg_time = statistics.mean(times_only)
    median_time = statistics.median(times_only)
    stdev_time = statistics.stdev(times_only) if len(times_only) > 1 else 0
    sorted_times = sorted(times_only)
    p90 = sorted_times[int(len(sorted_times) * 0.90)]
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[int(len(sorted_times) * 0.99)]

    # Stutter thresholds
    stutter_threshold = max(median_time * 1.5, 50.0)
    severe_threshold = max(median_time * 3.0, 100.0)

    # Collect per-marker average times across all frames
    marker_all_times = defaultdict(list)
    for f, mt, ft in frame_data:
        if mt and mt.samples:
            for s in mt.samples:
                marker_all_times[s.marker_name].append(s.duration_ns / 1_000_000.0)

    marker_means = {name: statistics.mean(times) for name, times in marker_all_times.items()}

    # Identify stutter frames
    stutter_frames = []
    for f, mt, ft in frame_data:
        if ft < stutter_threshold:
            continue
        deviation = ft / median_time if median_time > 0 else 0

        top_markers = []
        spike_contributors = []

        if mt and mt.samples:
            hotspots = get_deep_hotspots(mt.samples, min_time_ms=1.0)
            top_markers = sorted(hotspots, key=lambda x: x[1], reverse=True)[:20]

            # Find spike contributors
            for s in mt.samples:
                time_ms = s.duration_ns / 1_000_000.0
                avg = marker_means.get(s.marker_name, 0)
                if avg > 0.1 and time_ms > avg * 2.0 and time_ms > 1.0:
                    delta = time_ms - avg
                    spike_contributors.append((s.marker_name, time_ms, avg, delta))

            spike_contributors.sort(key=lambda x: x[3], reverse=True)
            spike_contributors = spike_contributors[:15]

        stutter_frames.append({
            "frame_index": f.frame_index,
            "frame_time_ms": ft,
            "deviation": deviation,
            "top_markers": top_markers,
            "spike_contributors": spike_contributors,
            "frame": f,
            "main_thread": mt,
        })

    stutter_frames.sort(key=lambda x: x["frame_time_ms"], reverse=True)

    # === Build Report ===
    L = []
    L.append("=" * 80)
    L.append("  UNITY PROFILER 卡顿帧分析报告")
    L.append("=" * 80)
    L.append("")

    L.append("[帧时分布统计]")
    L.append(f"  总帧数:    {len(times_only)}")
    L.append(f"  平均:      {avg_time:.2f} ms  ({1000/avg_time:.1f} FPS)")
    L.append(f"  中位数:    {median_time:.2f} ms  ({1000/median_time:.1f} FPS)")
    L.append(f"  标准差:    {stdev_time:.2f} ms")
    L.append(f"  P90:       {p90:.2f} ms  ({1000/p90:.1f} FPS)")
    L.append(f"  P95:       {p95:.2f} ms  ({1000/p95:.1f} FPS)")
    L.append(f"  P99:       {p99:.2f} ms  ({1000/p99:.1f} FPS)")
    L.append(f"  最小:      {min(times_only):.2f} ms")
    L.append(f"  最大:      {max(times_only):.2f} ms")
    L.append("")

    # Histogram
    L.append("[帧时直方图]")
    buckets = [
        (0, 16.67, "< 16.7ms (60+ FPS)"),
        (16.67, 33.33, "16.7-33.3ms (30-60 FPS)"),
        (33.33, 50.0, "33.3-50ms (20-30 FPS)"),
        (50.0, 66.67, "50-66.7ms (15-20 FPS)"),
        (66.67, 100.0, "66.7-100ms (10-15 FPS)"),
        (100.0, 200.0, "100-200ms (5-10 FPS)"),
        (200.0, 500.0, "200-500ms (2-5 FPS)"),
        (500.0, 99999.0, "> 500ms (< 2 FPS)"),
    ]
    for lo, hi, label in buckets:
        count = sum(1 for t in times_only if lo <= t < hi)
        pct = 100 * count / len(times_only)
        bar = "#" * int(pct / 2)
        L.append(f"  {label:30s} {count:5d} ({pct:5.1f}%) {bar}")
    L.append("")

    # Stutter summary
    mild = [s for s in stutter_frames if s["frame_time_ms"] < severe_threshold]
    severe = [s for s in stutter_frames if s["frame_time_ms"] >= severe_threshold]
    L.append(f"[卡顿检测]")
    L.append(f"  轻微卡顿阈值:    {stutter_threshold:.1f} ms (1.5x 中位数)")
    L.append(f"  严重卡顿阈值:    {severe_threshold:.1f} ms (3x 中位数)")
    L.append(f"  卡顿帧总数:      {len(stutter_frames)} / {len(times_only)}  ({100*len(stutter_frames)/len(times_only):.1f}%)")
    L.append(f"  轻微卡顿:        {len(mild)}")
    L.append(f"  严重卡顿:        {len(severe)}")
    L.append("")

    # Frame stability
    L.append("[帧时稳定性]")
    jitters = [abs(times_only[i] - times_only[i-1]) for i in range(1, len(times_only))]
    if jitters:
        avg_jitter = statistics.mean(jitters)
        max_jitter = max(jitters)
        cv = stdev_time / avg_time * 100 if avg_time > 0 else 0
        L.append(f"  帧间抖动(平均): {avg_jitter:.2f} ms")
        L.append(f"  帧间抖动(最大): {max_jitter:.2f} ms")
        L.append(f"  变异系数(CV):    {cv:.1f}%")
        if cv > 30:
            L.append(f"  → 帧时非常不稳定 (CV > 30%)")
        elif cv > 15:
            L.append(f"  → 帧时不稳定 (CV > 15%)")
        else:
            L.append(f"  → 帧时相对稳定")
    L.append("")

    # Consecutive stutters
    L.append("[连续卡顿检测]")
    consecutive_runs = []
    current_run = []
    for f, mt, ft in frame_data:
        if ft >= stutter_threshold:
            current_run.append((f.frame_index, ft))
        else:
            if len(current_run) >= 2:
                consecutive_runs.append(current_run)
            current_run = []
    if len(current_run) >= 2:
        consecutive_runs.append(current_run)

    if consecutive_runs:
        L.append(f"  发现 {len(consecutive_runs)} 段连续卡顿:")
        for run in sorted(consecutive_runs, key=lambda r: len(r), reverse=True)[:10]:
            avg_run = statistics.mean([ft for _, ft in run])
            L.append(f"    帧 {run[0][0]}-{run[-1][0]}: 连续 {len(run)} 帧, "
                     f"平均 {avg_run:.1f}ms, 范围 {min(ft for _,ft in run):.1f}-{max(ft for _,ft in run):.1f}ms")
    else:
        L.append("  未发现连续卡顿。")
    L.append("")

    # === Detailed per-stutter analysis ===
    L.append("=" * 80)
    L.append("  最严重的 15 个卡顿帧详细分析")
    L.append("=" * 80)

    for sf in stutter_frames[:15]:
        L.append("")
        severity = "严重" if sf["frame_time_ms"] >= severe_threshold else "轻微"
        L.append(f"{'─' * 70}")
        L.append(f"  [{severity}] 帧 {sf['frame_index']}: {sf['frame_time_ms']:.2f} ms "
                 f"({1000/sf['frame_time_ms']:.1f} FPS, {sf['deviation']:.1f}x 中位数)")
        L.append(f"{'─' * 70}")

        if sf["top_markers"]:
            L.append(f"  耗时最长的 Marker:")
            for name, time_ms, depth in sf["top_markers"][:12]:
                indent = "  " * min(depth, 3)
                L.append(f"    {indent}{name}: {time_ms:.3f} ms")

        if sf["spike_contributors"]:
            L.append(f"")
            L.append(f"  异常飙升项 (本帧 vs 平均):")
            for name, time_ms, avg, delta in sf["spike_contributors"][:10]:
                ratio = time_ms / avg if avg > 0 else 0
                L.append(f"    {name}:")
                L.append(f"      本帧: {time_ms:.3f} ms  |  平均: {avg:.3f} ms  |  "
                         f"增量: +{delta:.3f} ms  ({ratio:.1f}x)")

        # Call tree
        mt = sf["main_thread"]
        if mt and mt.samples:
            threshold = max(sf["frame_time_ms"] * 0.05, 1.0)
            tree = build_call_tree_string(mt.samples, max_depth=3, min_time_ms=threshold)
            if tree:
                L.append(f"")
                L.append(f"  调用树 (>{threshold:.1f}ms, 深度≤3):")
                for line in tree.split("\n"):
                    L.append(f"    {line}")

    # === Pattern Analysis ===
    L.append("")
    L.append("=" * 80)
    L.append("  卡顿模式分析")
    L.append("=" * 80)
    L.append("")

    # Common spike contributors
    spike_frequency = defaultdict(lambda: {"count": 0, "total_delta": 0.0, "max_delta": 0.0, "max_time": 0.0})
    for sf in stutter_frames:
        for name, time_ms, avg, delta in sf["spike_contributors"]:
            entry = spike_frequency[name]
            entry["count"] += 1
            entry["total_delta"] += delta
            entry["max_delta"] = max(entry["max_delta"], delta)
            entry["max_time"] = max(entry["max_time"], time_ms)

    if spike_frequency:
        L.append("[最常见的卡顿原因]")
        L.append(f"  (在卡顿帧中高于平均值的 Marker)")
        L.append("")
        L.append(f"  {'Marker':<60s} {'次数':>5s} {'总增量':>10s} {'最大增量':>10s} {'最大耗时':>10s}")
        L.append(f"  {'─'*60} {'─'*5} {'─'*10} {'─'*10} {'─'*10}")
        sorted_spikes = sorted(spike_frequency.items(), key=lambda x: x[1]["total_delta"], reverse=True)
        for name, info in sorted_spikes[:25]:
            L.append(f"  {name:<60s} {info['count']:>5d} {info['total_delta']:>9.1f}ms "
                     f"{info['max_delta']:>9.1f}ms {info['max_time']:>9.1f}ms")
    L.append("")

    # Categorize stutter causes
    L.append("[卡顿分类汇总]")
    categories = {
        "脚本/Lua": ["GameLuaSystem", "LuaTailUpdater", "[lua]", "GameEntry", "BehaviourUpdate",
                     "EventManager.executeLuaEvent", "ScriptRunBehaviour"],
        "渲染": ["Render", "SRPBatcher", "DrawBuffersBatchMode", "RenderLoop", "Gbuffer",
                "CSM Pass", "Camera.Render", "DoRenderLoop", "FinishFrameRendering"],
        "UI": ["Canvas", "UGUI", "EventSystem", "UIEvents", "CanvasUpdate", "PlayerUpdateCanvases"],
        "物理": ["Physics.", "PhysicsFixedUpdate", "Physics.Simulate"],
        "动画": ["Animator", "Animation.", "Director.PrepareFrame", "Director.ProcessFrame",
                "MeshSkinning", "DirectorUpdate"],
        "加载/IO": ["Loading", "AsyncRead", "Preloading", "ResourceSystem", "Jnfs.LoadAsset"],
        "GC": ["GC.Collect", "GarbageCollect"],
        "GPU同步": ["Gfx.Wait", "WaitForGfxCommands", "WaitForPresent"],
        "Job等待": ["WaitForJobGroupID", "JobHandle.Complete", "Semaphore.WaitForSignal"],
        "Profiler": ["Profiler.Flush", "ProfilerEndFrame"],
    }

    category_impact = defaultdict(lambda: {"frames": 0, "total_delta": 0.0})
    for sf in stutter_frames:
        frame_categories = set()
        for name, time_ms, avg, delta in sf["spike_contributors"]:
            for cat, keywords in categories.items():
                if any(kw in name for kw in keywords):
                    if cat not in frame_categories:
                        frame_categories.add(cat)
                    category_impact[cat]["total_delta"] += delta
        for cat in frame_categories:
            category_impact[cat]["frames"] += 1

    if category_impact:
        sorted_cats = sorted(category_impact.items(), key=lambda x: x[1]["total_delta"], reverse=True)
        for cat, info in sorted_cats:
            pct = 100 * info["frames"] / len(stutter_frames) if stutter_frames else 0
            L.append(f"  {cat:<15s}: {info['frames']:>4d} 个卡顿帧 ({pct:5.1f}%), "
                     f"总飙升量: {info['total_delta']:.1f}ms")
    L.append("")

    # Periodicity
    L.append("[卡顿周期性检测]")
    if len(stutter_frames) >= 3:
        stutter_sorted = sorted(stutter_frames, key=lambda x: x["frame_index"])
        intervals = [stutter_sorted[i]["frame_index"] - stutter_sorted[i-1]["frame_index"]
                     for i in range(1, len(stutter_sorted))]
        if intervals and len(intervals) > 1:
            avg_interval = statistics.mean(intervals)
            interval_stdev = statistics.stdev(intervals)
            cv_interval = interval_stdev / avg_interval * 100 if avg_interval > 0 else 999
            L.append(f"  卡顿间隔(平均):     {avg_interval:.1f} 帧")
            L.append(f"  卡顿间隔(标准差):   {interval_stdev:.1f} 帧")
            if cv_interval < 30:
                L.append(f"  → 检测到周期性卡顿 (CV={cv_interval:.0f}%)")
                L.append(f"    可能是定时操作引起 (如 GC、资源加载、定时器回调)")
            else:
                L.append(f"  → 无明显周期性 (CV={cv_interval:.0f}%)")
    L.append("")

    # === Frame time over time (sparkline-style) ===
    L.append("[帧时趋势 (每行代表约20帧)]")
    chunk_size = 20
    for i in range(0, len(times_only), chunk_size):
        chunk = times_only[i:i+chunk_size]
        avg_chunk = statistics.mean(chunk)
        max_chunk = max(chunk)
        stutter_count = sum(1 for t in chunk if t >= stutter_threshold)

        # Visual bar
        bar_len = min(int(avg_chunk / 2), 60)
        bar = "█" * bar_len
        if max_chunk >= severe_threshold:
            marker = " !! SEVERE"
        elif stutter_count > 0:
            marker = f" ! x{stutter_count}"
        else:
            marker = ""

        L.append(f"  帧{i:>4d}-{min(i+chunk_size-1, len(times_only)-1):>4d}: "
                 f"avg={avg_chunk:>6.1f}ms max={max_chunk:>7.1f}ms {bar}{marker}")
    L.append("")

    # === Recommendations ===
    L.append("=" * 80)
    L.append("  卡顿专项优化建议")
    L.append("=" * 80)
    L.append("")

    recommendations = []

    # Check for GPU sync stutters
    for key in ["Gfx.WaitForGfxCommandsFromMainThread", "Gfx.WaitForPresentOnGfxThread"]:
        info = spike_frequency.get(key, {})
        if info.get("count", 0) > 0:
            recommendations.append((
                "HIGH", "GPU/渲染线程同步卡顿",
                f"{key} 在 {info['count']} 个卡顿帧中飙升，最高 {info['max_time']:.1f}ms。"
                f"\n    主线程被渲染线程阻塞，说明 DrawCall 太多或 GPU 过载。",
                "减少 DrawCall（合批、LOD）、降低阴影分辨率、减少透明物体。"
            ))
            break

    # Scripting spikes
    for key in ["Game.Management.GameLuaSystem.OnUpdate",
                "Game.dll!Game::GameEntry.Update() [Invoke]",
                "Update.ScriptRunBehaviourUpdate"]:
        info = spike_frequency.get(key, {})
        if info.get("count", 0) >= 3:
            recommendations.append((
                "HIGH", "脚本/Lua 逻辑尖刺",
                f"{key} 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。",
                "排查 Lua 中 O(n²) 循环、大量字符串操作、频繁跨语言调用。\n    大型计算做分帧处理。"
            ))
            break

    # EventSystem
    for key in spike_frequency:
        if "EventSystem" in key:
            info = spike_frequency[key]
            if info.get("count", 0) >= 2 and info["max_time"] > 3:
                recommendations.append((
                    "MEDIUM", "UI EventSystem Raycast 卡顿",
                    f"EventSystem 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。",
                    "限制 Physics Raycaster Event Mask、减少 Raycaster 数量、关闭不可交互 UI 的 Raycast Target。"
                ))
                break

    # Rendering
    for key in ["PostLateUpdate.FinishFrameRendering"]:
        info = spike_frequency.get(key, {})
        if info.get("count", 0) >= 2:
            recommendations.append((
                "HIGH", "渲染管线帧时尖刺",
                f"FinishFrameRendering 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。",
                "检查运行时 Shader 编译、新材质首次渲染、分辨率动态变化。"
            ))
            break

    # Canvas
    for key in ["PostLateUpdate.PlayerUpdateCanvases"]:
        info = spike_frequency.get(key, {})
        if info.get("count", 0) >= 2:
            recommendations.append((
                "MEDIUM", "Canvas 重建卡顿",
                f"PlayerUpdateCanvases 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。",
                "隔离动态 UI 到独立 Canvas、减少 SetAllDirty、避免每帧修改 Text/Image。"
            ))

    # Physics
    for key in ["FixedUpdate.PhysicsFixedUpdate"]:
        info = spike_frequency.get(key, {})
        if info.get("count", 0) >= 2:
            recommendations.append((
                "MEDIUM", "物理模拟卡顿",
                f"PhysicsFixedUpdate 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。"
                f"\n    低帧率触发多次 FixedUpdate 追赶。",
                "设置 Time.maximumDeltaTime 限制追赶次数、减少活跃碰撞体。"
            ))

    # Profiler
    for key in ["Profiler.FlushMemoryCounters", "PostLateUpdate.ProfilerEndFrame"]:
        info = spike_frequency.get(key, {})
        if info.get("count", 0) > 0:
            recommendations.append((
                "INFO", "Profiler 开销",
                f"Profiler 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。"
                f"\n    这是 Profiler 连接时的额外开销，真机非 Profile 模式不存在。",
                "注意此开销可能掩盖/放大其他卡顿。分析时需扣除 Profiler 开销。"
            ))
            break

    # Loading
    for key in spike_frequency:
        if any(kw in key for kw in ["ResourceSystem", "LoadAsset", "Loading.Update", "Preloading"]):
            info = spike_frequency[key]
            if info.get("count", 0) >= 2:
                recommendations.append((
                    "MEDIUM", "资源加载卡顿",
                    f"{key} 在 {info['count']} 个卡顿帧飙升，最高 {info['max_time']:.1f}ms。",
                    "确保异步加载、限制每帧加载量、预加载常用资源。"
                ))
                break

    for sev, title, detail, fix in recommendations:
        L.append(f"  [{sev}] {title}")
        L.append(f"    问题: {detail}")
        L.append(f"    建议: {fix}")
        L.append("")

    report = "\n".join(L)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport saved to: {output_file}")

    print(report)


if __name__ == "__main__":
    data_file = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Admin\Downloads\8gen1街区挂机.data"
    output_file = data_file + ".stutter_analysis.txt"
    analyze_stutter_frames(data_file, output_file)
