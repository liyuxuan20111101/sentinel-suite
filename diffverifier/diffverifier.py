#!/usr/bin/env python3
"""DiffVerifier — AI 补丁的行为等价性验证器。

不审风格，只回答一个问题：**这个改动在原有输入空间里会不会改变行为。**

立身之本：SWE-Proof 证明约 25% 的"测试通过"补丁仍可构造出反例。
所有人都在做"生成 review 意见"，没人做"证明行为没变"。

用法：
  # 对比改动前后（old 缺省取 <new>.bak，如 edit 工具自动备份）
  python diffverifier/diffverifier.py --path path/to/x.py --calls "calc(2, 3)|greet('hi')"

  # 显式给新旧两个文件
  python diffverifier/diffverifier.py --old old.py --new new.py --calls "calc(2, 3)"

  # 从 stdin 读 JSON 用例：[["calc", [2, 3]], ["greet", ["hi"]]]
  echo '[["calc",[2,3]]]' | python diffverifier/diffverifier.py --old a.py --new b.py --calls-json -

原理：把新旧两个版本在**相同输入**上各跑一遍，对比输出。异常也算一种输出——
一边抛一边不抛就是行为差异。参数只接受 ast.literal_eval 字面量（无 eval 注入面）；
对比在子进程里跑（默认 20s 超时），加载用手动 compile 彻底绕开 __pycache__
陈旧字节码（新旧实现同长同秒改写时 pyc 校验会误判缓存有效——这是实测踩过的坑）。

边界（如实告知）：最适合纯函数/自包含模块；模块级副作用（连网、开文件）两边都会发生。
退出码：0=抽查的输入上行为一致；1=发现行为差异；2=出错（加载失败/超时/用法错误）。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_S = 20.0
_CALL_RE = re.compile(r"^([A-Za-z_]\w*)\s*\((.*)\)$", re.S)
EXIT_SAME, EXIT_DIFF, EXIT_ERROR = 0, 1, 2

# 子进程里跑的对比器：加载 old/new 两个模块，逐用例执行并打印 JSON 行
_RUNNER = r'''
import json, sys, types

def _load(path, name):
    src = open(path, encoding="utf-8").read()
    code = compile(src, path, "exec")
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(code, mod.__dict__)
    return mod

cfg = json.loads(sys.argv[1])
for tag, key in (("old", "old"), ("new", "new")):
    try:
        globals()[tag] = _load(cfg[key], "dv_" + tag + "_module")
    except Exception as e:
        print(json.dumps({"fatal_" + tag: f"{e.__class__.__name__}: {e}"}, ensure_ascii=False))
        globals()[tag] = None

for fn, args in cfg["calls"]:
    row = {"fn": fn, "args": repr(args)}
    for tag in ("old", "new"):
        mod = globals()[tag]
        if mod is None:
            row[tag] = "<模块加载失败>"
            continue
        f = getattr(mod, fn, None)
        if f is None or not callable(f):
            row[tag] = "<没有这个函数>"
        else:
            try:
                row[tag] = repr(f(*args))
            except Exception as e:
                row[tag] = f"<异常 {e.__class__.__name__}: {e}>"
    print(json.dumps(row, ensure_ascii=False))
'''


def parse_calls(spec: str) -> list[tuple[str, list]]:
    """解析 calls 规格："fn(1, 'a')|fn(2)" → [("fn", [1, "a"]), ("fn", [2])]。"""
    calls: list[tuple[str, list]] = []
    for piece in (spec or "").split("|"):
        piece = piece.strip()
        if not piece:
            continue
        m = _CALL_RE.match(piece)
        if not m:
            raise ValueError(f"看不懂这个用例：{piece[:60]}（格式：函数名(参数)）")
        fn, arg_str = m.group(1), m.group(2).strip()
        try:
            args = ast.literal_eval(f"[{arg_str}]") if arg_str else []
        except (ValueError, SyntaxError, MemoryError, RecursionError) as exc:
            raise ValueError(f"{fn} 的参数不是字面量：{piece[:60]}（{exc.__class__.__name__}）")
        if len(calls) >= 12:
            break  # 防刷：一次最多 12 个用例
        calls.append((fn, args))
    if not calls:
        raise ValueError("没有解析到用例（格式：fn(参数)|fn2(参数)，参数用字面量）")
    return calls


# ---- 自动用例生成（v0.1）：按函数签名构造典型边界输入 ----
# 启发式、非穷尽：覆盖 零/空/负/超长/典型值 这类最容易暴露行为差异的形状，
# 不能证明等价——是"帮你想输入"的第一稿，欢迎在此基础上手工补充。

def _values_for_param(name: str, ann: str, has_default: bool) -> list:
    """按参数名/注解猜测典型值（保守字面量，避免调用即崩）。"""
    a = (ann or "").lower()
    text = name.lower()
    if "int" in a or any(k in text for k in ("count", "num", "n_", "idx", "index", "size", "len")):
        return [0, 1, -1, 1000000]
    if "float" in a or any(k in text for k in ("rate", "ratio", "price", "amount", "score")):
        return [0.0, 1.5, -2.5, 1e9]
    if "bool" in a:
        return [True, False]
    if "str" in a or any(k in text for k in ("name", "text", "msg", "path", "title", "word", "query")):
        return ["", "hello", "中文测试", "a" * 300]
    if "list" in a or "seq" in a:
        return [[], [1, 2, 3], ["a"] * 50]
    if "dict" in a or "map" in a:
        return [{}, {"k": 1}]
    return [0, 1, "", "x", []]


def public_functions(source: str) -> list[dict]:
    """ast 解析源码，返回模块级公开函数的签名信息。"""
    tree = ast.parse(source)
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        params = []
        args = node.args
        pos = args.posonlyargs + args.args
        defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
        for p, d in zip(pos, defaults):
            if p.arg in ("self", "cls"):
                continue
            ann = ""
            if isinstance(p.annotation, ast.Name):
                ann = p.annotation.id
            elif isinstance(p.annotation, ast.Constant):
                ann = str(p.annotation.value)
            params.append({"name": p.arg, "ann": ann,
                           "default": d is not None, "kind": "vararg" if p.arg == args.vararg else "pos"})
        out.append({"name": node.name, "params": params})
    return out


def suggest_inputs(source: str, fn_name: str, max_cases: int = 3) -> list[list]:
    """为一个函数生成 ≤max_cases 组字面量参数（跨参数组合，钳制数量）。"""
    fns = public_functions(source)
    fn = next((f for f in fns if f["name"] == fn_name), None)
    if fn is None:
        raise ValueError(f"源码里没有模块级公开函数 {fn_name}")
    params = [p for p in fn["params"] if p["kind"] == "pos"]
    if not params:
        return [[]]
    pools = [_values_for_param(p["name"], p["ann"], p["default"]) for p in params]
    # 组合按列错位轮转取 max_cases 组：每个参数的取值错开步进，扩大覆盖面
    cases = []
    for i in range(max_cases):
        cases.append([pool[(i + j) % len(pool)] for j, pool in enumerate(pools)])
    return cases


def auto_calls(source: str, only_fn: str | None = None, per_fn: int = 3) -> list[tuple[str, list]]:
    """为模块级公开函数（或指定函数）自动生成用例。"""
    fns = public_functions(source)
    if only_fn:
        fns = [f for f in fns if f["name"] == only_fn]
        if not fns:
            raise ValueError(f"源码里没有模块级公开函数 {only_fn}")
    calls: list[tuple[str, list]] = []
    for f in fns:
        for args in suggest_inputs(source, f["name"], per_fn):
            calls.append((f["name"], args))
            if len(calls) >= 12:
                return calls
    return calls


def run_diff(old_path: Path, new_path: Path, calls: list[tuple[str, list]],
             timeout: float = TIMEOUT_S) -> tuple[str, int]:
    """对比两个 .py 在相同输入下的输出。返回 (报告文本, 退出码)。"""
    host_py = sys.executable if not getattr(sys, "frozen", False) else (
        shutil.which("python") or shutil.which("py"))
    if host_py is None:
        return "diffverifier：找不到系统 Python", EXIT_ERROR
    tmp = Path(tempfile.mkdtemp(prefix="diffverifier-"))
    runner = tmp / "_runner.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    cfg = json.dumps({"old": str(old_path), "new": str(new_path),
                      "calls": [[fn, args] for fn, args in calls]}, ensure_ascii=False)
    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        proc = subprocess.run([host_py, str(runner), cfg], capture_output=True,
                              timeout=timeout, creationflags=creationflags,
                              cwd=str(tmp), check=False)
    except subprocess.TimeoutExpired:
        return f"diffverifier：超时（>{timeout:.0f}s）——两个版本里可能有阻塞调用", EXIT_ERROR
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out:
        err = proc.stderr.decode("utf-8", errors="replace")[-300:]
        return f"diffverifier：对比进程没有输出。{err}", EXIT_ERROR

    lines, n_diff, n_comp, fatal = [], 0, 0, ""
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if row.get("fatal_old"):
            fatal = f"旧版本加载失败：{row['fatal_old']}"
        if row.get("fatal_new"):
            fatal = f"新版本加载失败：{row['fatal_new']}"
        if "old" not in row:
            continue
        n_comp += 1
        brief = f"{row['fn']}{row['args']}"
        if row["old"] == row["new"]:
            lines.append(f"{brief}：一致 → {row['new'][:120]}")
        else:
            n_diff += 1
            lines.append(f"{brief}：行为不同！旧={row['old'][:120]} ≠ 新={row['new'][:120]}")
    if fatal:
        return f"diffverifier：{fatal}（无法对比，结果不可信）", EXIT_ERROR
    body = "\n".join(f"{i}. {t}" for i, t in enumerate(lines, 1))
    if n_diff:
        verdict = (f"结论：{n_comp} 个用例里 {n_diff} 个行为不同。\n"
                   "这些差异若不是这次改动的目的，改动有问题。")
        code = EXIT_DIFF
    else:
        verdict = f"结论：{n_comp} 个用例里 0 个行为不同（本次改动在抽查的输入上行为未变）。"
        code = EXIT_SAME
    return ("diffverifier —— 旧 vs 新，同一输入：\n" + body + "\n" + verdict, code)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI 补丁的行为等价性验证器")
    ap.add_argument("--old", help="旧版本 .py（缺省取 --path 的 .bak）")
    ap.add_argument("--new", help="新版本 .py")
    ap.add_argument("--path", help="改过的文件（--old 缺省时取它的 .bak）")
    ap.add_argument("--calls", help='用例："fn(1, \'a\')|fn(2)"（参数用字面量）')
    ap.add_argument("--calls-json", help='用例 JSON 文件；"-"=从 stdin 读 [["fn",[args]],…]')
    ap.add_argument("--auto", type=int, metavar="N", nargs="?", const=3,
                    help="按函数签名自动生成用例（每函数 N 个典型输入，缺省 3；"
                         "对全部模块级公开函数生效）")
    ap.add_argument("--timeout", type=float, default=TIMEOUT_S)
    a = ap.parse_args()

    try:
        if a.auto is not None:
            src_file = Path(a.new or a.path or "")
            if not src_file.exists():
                ap.error("--auto 需要能读到的目标文件（--path 或 --new）")
            calls = auto_calls(src_file.read_text("utf-8"), per_fn=max(1, a.auto))
        elif a.calls_json:
            raw = sys.stdin.read() if a.calls_json == "-" else Path(a.calls_json).read_text("utf-8")
            calls = [(str(fn), list(args)) for fn, args in json.loads(raw)]
            if not calls:
                raise ValueError("用例为空")
        elif a.calls:
            calls = parse_calls(a.calls)
        else:
            ap.error("需要 --calls 或 --calls-json")
            return EXIT_ERROR
    except ValueError as exc:
        print(f"diffverifier：{exc}")
        return EXIT_ERROR

    if a.old and a.new:
        old_p, new_p = Path(a.old), Path(a.new)
    elif a.path:
        new_p = Path(a.path)
        old_p = new_p.with_suffix(new_p.suffix + ".bak")
        if not old_p.exists():
            print(f"diffverifier：没有找到改动前备份 {old_p.name}。"
                  "diffverifier 对比的是上一次改动前后的行为（.bak 自动生成），"
                  "或用 --old/--new 显式指定两个文件。")
            return EXIT_ERROR
    else:
        print("diffverifier：需要 --path 或 --old/--new")
        return EXIT_ERROR
    if not new_p.exists() or not old_p.exists():
        print(f"diffverifier：文件不存在（old={old_p} new={new_p}）")
        return EXIT_ERROR
    # 子进程在临时目录里执行被测代码，必须传绝对路径
    old_p, new_p = old_p.resolve(), new_p.resolve()

    report, code = run_diff(old_p, new_p, calls, timeout=a.timeout)
    print(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
