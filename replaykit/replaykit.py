#!/usr/bin/env python3
"""ReplayKit — Agent 可重放运行时（v0）。

动机：Agent 的首次分歧 60% 发生在最前两步，而行业普遍停在"日志层"——
日志能看，不能跑。可重放性的事实标准并不存在，ReplayKit 想补这一块：

- **录制**：把 agent 每一步的工具名/输入/输出写成 JSONL 轨迹（trace）；
- **重放**：同一轨迹喂回工具实现（或新版本实现），逐步对比输出；
- **分歧定位**：报告第一个分歧步——v0 的核心问题"第几步开始不一样"。

设计原则：
- 轨迹是**唯一事实源**：一行一个 JSON 对象 {"step", "tool", "args", "result", "ts"}；
- 重放是**确定性的**：不重放副作用，只重放"给定输入 → 工具输出"的映射；
- 零依赖，JSONL 可直接用 jq/grep 看。

用法（库）：
    from replaykit import Recorder, replay

    rec = Recorder.open("trace.jsonl")
    rec.record(0, "search", {"q": "weather"}, {"temp": 25})
    rec.close()

    report = replay("trace.jsonl", {"search": my_new_search})
    print(report["first_divergence"])   # None=完全一致；否则 {"step": 0, ...}

用法（CLI）：
    python replaykit/replaykit.py inspect trace.jsonl        # 轨迹概览
    python replaykit/replaykit.py replay trace.jsonl --tools mytools.py

退出码：0=重放一致；1=发现分歧；2=出错（工具缺失/文件坏）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

EXIT_SAME, EXIT_DIFF, EXIT_ERROR = 0, 1, 2


class Recorder:
    """把 agent 每一步的 (step, tool, args, result) 写成 JSONL 轨迹。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8")
        self._step = 0

    def record(self, step: int, tool: str, args: dict, result) -> None:
        self._f.write(json.dumps({
            "step": step, "tool": tool, "args": args,
            "result": result, "ts": time.time(),
        }, ensure_ascii=False) + "\n")
        self._step = max(self._step, step + 1)

    def next_step(self, tool: str, args: dict, result) -> None:
        """按顺序记录（自动 step 号）。"""
        self.record(self._step, tool, args, result)

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_trace(path: Path | str) -> list[dict]:
    """读 JSONL 轨迹；坏行跳过并保留行号供报告引用。"""
    entries = []
    for i, ln in enumerate(Path(path).read_text("utf-8").splitlines(), 1):
        ln = ln.strip()
        if not ln:
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            continue  # 坏行（截断的写入等）：跳过，不假装它是事实
        if "tool" in e and "args" in e:
            e["_line"] = i
            entries.append(e)
    return entries


def load_tools(path: Path | str) -> dict:
    """从 .py 文件加载工具表：模块顶层 TOOL name→callable，或返回一个 dict。"""
    spec = importlib.util.spec_from_file_location("replaykit_tools", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tools = getattr(mod, "TOOLS", None)
    if isinstance(tools, dict):
        return tools
    raise ValueError(f"{path} 没有暴露 TOOLS 字典（name → callable(args_dict)）")


def _canonical(v):
    """JSON 规范化比较：dict/list 递归，其它用 repr 兜底。"""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=repr)


def replay(trace_path: Path | str, tools: dict[str, callable],
           stop_on_first: bool = True, repeat: int = 1) -> dict:
    """重放轨迹：逐步用记录的 args 调 tools[tool]，与记录的 result 对比。

    repeat>1 时每个工具跑多遍：重放结果彼此不一致的步标记为「不稳定步」
    （时间/随机类工具天然如此），不再算分歧——防止把噪声当回归。
    返回 {"steps", "compared", "divergences", "unstable", "first_divergence"}。
    """
    entries = read_trace(trace_path)
    repeat = max(1, int(repeat))
    divs, unstable = [], []
    for e in entries:
        step, tool, args, expected = e["step"], e["tool"], e["args"], e.get("result")
        fn = tools.get(tool)
        if fn is None:
            actual, note = "<工具缺失>", f"重放环境没有工具 {tool}"
        else:
            try:
                actual, note = fn(args), ""
            except Exception as exc:
                actual, note = f"<异常 {exc.__class__.__name__}: {exc}>", ""
        same = _canonical(actual) == _canonical(expected)
        if same:
            continue
        if repeat > 1:
            # 多次重放：有任何一次对上记录值 → 步骤本身可复现（前次是噪声）；
            # 重放之间彼此不一致 → 天然不稳定步，单独归类。
            seen = {_canonical(actual)}
            stable_match = False
            for _ in range(repeat - 1):
                try:
                    seen.add(_canonical(fn(args)))
                except Exception as exc:
                    seen.add(f"<异常 {exc.__class__.__name__}: {exc}>")
            if _canonical(expected) in seen:
                stable_match = True
            if len(seen) > 1:
                unstable.append({"step": step, "line": e.get("_line"), "tool": tool,
                                 "note": f"{repeat} 次重放得到 {len(seen)} 种输出（天然不稳定）"})
                continue
            if stable_match:
                continue
        div = {"step": step, "line": e.get("_line"), "tool": tool,
               "args": args, "recorded": expected, "replayed": actual}
        if note:
            div["note"] = note
        divs.append(div)
        if stop_on_first:
            break
    compared = len(entries) - len(unstable) if not divs else len(divs) + len(unstable) + (
        0 if stop_on_first else 0)
    return {
        "steps": len(entries),
        "compared": compared,
        "divergences": divs,
        "unstable": unstable,
        "first_divergence": divs[0] if divs else None,
    }


def compare(trace_a: Path | str, trace_b: Path | str) -> dict:
    """对比两条轨迹（同一 agent 的两次运行）：逐步对齐 tool/args/result。

    第 i 步工具名不同 = 那一步就是首次行为分歧；工具相同但 args/result
    不同也计入。返回 {"steps", "first_divergence", "divergences"}。
    """
    ea, eb = read_trace(trace_a), read_trace(trace_b)
    divs = []
    for i in range(max(len(ea), len(eb))):
        a = ea[i] if i < len(ea) else None
        b = eb[i] if i < len(eb) else None
        if a is None or b is None:
            divs.append({"step": i, "kind": "length",
                         "note": f"轨迹长度不同（A={len(ea)} 步，B={len(eb)} 步），第 {i} 步只有一侧存在"})
            break
        if a["tool"] != b["tool"]:
            divs.append({"step": i, "kind": "tool", "tool_a": a["tool"], "tool_b": b["tool"],
                         "note": f"两条轨迹第 {i} 步选择了不同工具"})
            break
        if _canonical(a.get("args")) != _canonical(b.get("args")):
            divs.append({"step": i, "kind": "args", "tool": a["tool"],
                         "args_a": a.get("args"), "args_b": b.get("args"),
                         "note": f"第 {i} 步（{a['tool']}）的输入参数不同"})
            break
        if _canonical(a.get("result")) != _canonical(b.get("result")):
            divs.append({"step": i, "kind": "result", "tool": a["tool"],
                         "result_a": a.get("result"), "result_b": b.get("result"),
                         "note": f"第 {i} 步（{a['tool']}）在相同输入下输出不同"})
            break
    return {"steps": max(len(ea), len(eb)), "divergences": divs,
            "first_divergence": divs[0] if divs else None}


def format_compare(report: dict) -> str:
    head = f"replaykit：两条轨迹各 {report['steps']} 步。"
    fd = report["first_divergence"]
    if fd is None:
        return head + " 完全一致（两次运行行为相同）。"
    detail = json.dumps({k: v for k, v in fd.items() if k != "kind"},
                        ensure_ascii=False, default=repr)[:400]
    return head + f"\n首次分歧：第 {fd['step']} 步（{fd['kind']}）\n  {fd['note']}\n  {detail}"


def format_report(report: dict) -> str:
    head = f"replaykit：重放 {report['steps']} 步。"
    unstable = report.get("unstable") or []
    if unstable:
        head += (f" {len(unstable)} 个不稳定步（多次重放输出不一致，多为时间/随机类工具，已排除）："
                 + "、".join(f"第{u['step']}步({u['tool']})" for u in unstable[:5])
                 + ("…" if len(unstable) > 5 else ""))
    fd = report["first_divergence"]
    if fd is None:
        return head + " 全部一致（新实现在这条轨迹上行为未变）。"
    out = [head + f" 第 **{fd['step']} 步** 出现首次分歧（轨迹第 {fd.get('line')} 行）：",
           f"  工具：{fd['tool']}",
           f"  输入：{json.dumps(fd['args'], ensure_ascii=False)[:200]}",
           f"  记录值：{json.dumps(fd['recorded'], ensure_ascii=False)[:200]}",
           f"  重放值：{json.dumps(fd['replayed'], ensure_ascii=False)[:200]}"]
    if fd.get("note"):
        out.append(f"  备注：{fd['note']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent 可重放运行时（v0）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_i = sub.add_parser("inspect", help="轨迹概览：步数/工具分布/参数摘要")
    p_i.add_argument("trace")

    p_r = sub.add_parser("replay", help="重放轨迹并定位首个分歧")
    p_r.add_argument("trace")
    p_r.add_argument("--tools", required=True, help="工具实现 .py（需暴露 TOOLS 字典）")
    p_r.add_argument("--all", action="store_true", help="不停在首个分歧，全部对比")
    p_r.add_argument("--repeat", type=int, default=1, metavar="N",
                     help="每个工具重放 N 次：重放间输出不一致的步归为「不稳定步」，"
                          "防止把时间/随机类工具的噪声当回归（默认 1=不检测）")

    p_c = sub.add_parser("compare", help="对比同一 agent 的两条轨迹，定位首次行为分歧")
    p_c.add_argument("trace_a")
    p_c.add_argument("trace_b")

    a = ap.parse_args()

    if a.cmd == "compare":
        ra, rb = Path(a.trace_a), Path(a.trace_b)
        for p in (ra, rb):
            if not p.exists():
                print(f"replaykit：轨迹不存在 {p}")
                return EXIT_ERROR
        report = compare(ra, rb)
        print(format_compare(report))
        return EXIT_DIFF if report["first_divergence"] else EXIT_SAME

    trace = Path(a.trace)
    if not trace.exists():
        print(f"replaykit：轨迹不存在 {trace}")
        return EXIT_ERROR

    if a.cmd == "inspect":
        entries = read_trace(trace)
        if not entries:
            print("replaykit：轨迹为空或全部坏行")
            return EXIT_ERROR
        tools_seen: dict[str, int] = {}
        for e in entries:
            tools_seen[e["tool"]] = tools_seen.get(e["tool"], 0) + 1
        print(f"replaykit：{len(entries)} 步；工具分布："
              + "、".join(f"{t}×{c}" for t, c in tools_seen.items()))
        return EXIT_OK

    try:
        tools = load_tools(a.tools)
    except Exception as exc:
        print(f"replaykit：加载工具失败 {exc}")
        return EXIT_ERROR
    report = replay(trace, tools, stop_on_first=not a.all, repeat=a.repeat)
    print(format_report(report))
    return EXIT_DIFF if report["first_divergence"] else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
