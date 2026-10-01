#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五个工具的回归测试：python tests/run_tests.py（零依赖，直接跑）。"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "diffverifier"))
sys.path.insert(0, str(ROOT / "slopfirewall"))
sys.path.insert(0, str(ROOT / "replaykit"))
sys.path.insert(0, str(ROOT / "posttrain-doctor"))
sys.path.insert(0, str(ROOT / "opsbench"))

PASS, FAIL = "[PASS]", "[FAIL]"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{PASS if cond else FAIL} {name}" + (f"（{detail}）" if detail and not cond else ""))


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="toolkit-tests-"))

    # ---------- 1. DiffVerifier ----------
    import diffverifier as dv

    check("DV parse_calls", dv.parse_calls("calc(2, 3)|greet('hi')") ==
          [("calc", [2, 3]), ("greet", ["hi"])])
    try:
        dv.parse_calls("f(__import__('os'))")
        check("DV 拒绝非字面量", False)
    except ValueError:
        check("DV 拒绝非字面量", True)

    old_f = tmp / "calc_old.py"
    new_f = tmp / "calc_new.py"
    old_f.write_text("def calc(a, b):\n    return a + b\n", encoding="utf-8")
    new_f.write_text("def calc(a, b):\n    return a * b\n", encoding="utf-8")
    r, code = dv.run_diff(old_f, new_f, [("calc", [2, 3])])
    check("DV 抓到行为差异", code == dv.EXIT_DIFF and "行为不同" in r, r[:100])
    same_f = tmp / "calc_same.py"
    same_f.write_text("def calc(a, b):\n    return a + b  # 注释改动\n", encoding="utf-8")
    r2, code2 = dv.run_diff(old_f, same_f, [("calc", [2, 3]), ("calc", [0, 0])])
    check("DV 确认行为未变", code2 == dv.EXIT_SAME and "0 个行为不同" in r2, r2[:100])

    # CLI 端到端（.bak 约定）
    p = tmp / "x.py"
    p.write_text("def f():\n    return 1\n", encoding="utf-8")
    bak = p.with_suffix(".py.bak")
    bak.write_text("def f():\n    return 2\n", encoding="utf-8")
    r3 = run([sys.executable, str(ROOT / "diffverifier" / "diffverifier.py"),
              "--path", str(p), "--calls", "f()"])
    check("DV CLI 经 .bak 抓到差异", r3.returncode == 1 and "行为不同" in r3.stdout, r3.stdout[:100])

    # 自动用例生成（v0.1）：签名感知 + 全公开函数
    src = ("def calc(a, b):\n    return a + b\n\n\n"
           "def greet(name):\n    return 'hi ' + name\n\n\n"
           "def _private(x):\n    return x\n")
    fns = dv.public_functions(src)
    check("DV public_functions 解析签名",
          [f["name"] for f in fns] == ["calc", "greet"]
          and [pp["name"] for pp in fns[0]["params"]] == ["a", "b"])
    calls_auto = dv.auto_calls(src, per_fn=3)
    check("DV auto_calls 覆盖全部公开函数（跳过 _private）",
          {c[0] for c in calls_auto} == {"calc", "greet"} and len(calls_auto) >= 4,
          str(calls_auto)[:100])
    check("DV auto 输入含边界值（0/空串）",
          any(0 in args for _, args in calls_auto)
          and any("" in args for _, args in calls_auto), str(calls_auto)[:120])
    r_auto, code_auto = dv.run_diff(old_f, new_f, dv.auto_calls(old_f.read_text("utf-8")))
    check("DV auto 模式抓到差异", code_auto == dv.EXIT_DIFF and "行为不同" in r_auto, r_auto[:120])
    r4 = run([sys.executable, str(ROOT / "diffverifier" / "diffverifier.py"),
              "--path", str(p), "--auto"])
    check("DV CLI --auto 端到端", r4.returncode == 1 and "行为不同" in r4.stdout, r4.stdout[:120])

    # ---------- 2. SlopFirewall ----------
    import slopfirewall as sf

    targets = sf.parse_install_targets(
        'pip install requests>=2.0 flask[async] -r reqs.txt --index-url https://x\n'
        'python -m pip install numpy ./local pkg-with_underscore')
    check("SF 解析 pip install 目标",
          "requests" in targets and "flask" in targets and "numpy" in targets
          and "pkg-with-underscore" not in targets and "reqs.txt" not in targets,
          str(targets))
    seed_f = tmp / "seeds.txt"
    seed_f.write_text("# 注释\nfacny-colorlog\n\nleft_pad_zz\n", encoding="utf-8")
    seeds = sf.load_seeds(seed_f)
    check("SF 种子库加载", "facny-colorlog" in seeds and "left-pad-zz" in seeds)
    check("SF 种子命中（不发网络）", sf.check_one("facny-colorlog", seeds, None) == "seed")
    reqs = sf.extract_package_names("requests>=2.0\n# 注释\nflask\n-e .\n--index-url https://x\n")
    check("SF requirements.txt 解析", reqs == ["requests", "flask"], str(reqs))

    orig_status = sf._http_status
    try:
        sf._http_status = lambda url: 404
        report, code = sf.check_packages(["fake-pkg-zz"], seeds, None)
        check("SF 404 → 疑似幻觉", code == sf.EXIT_HALLUCINATION and "❌ fake-pkg-zz" in report,
              report[:100])
        report_t, _ = sf.check_packages(["requets"], seeds, None)
        check("SF typosquat 检测（requets→requests）",
              "拼写错误" in report_t and "requests" in report_t, report_t[:120])
        check("SF typosquat 不误报全新名", "拼写错误" not in report)
        sf._http_status = lambda url: 200
        report2, code2 = sf.check_packages(["requests"], seeds, None)
        check("SF 200 → 存在", code2 == sf.EXIT_OK and "✅ requests" in report2)
        sf._http_status = lambda url: None
        report3, code3 = sf.check_packages(["offline-pkg"], seeds, None)
        check("SF 断网 → 无法确认（不猜）", code3 == sf.EXIT_UNKNOWN and "❓" in report3)
    finally:
        sf._http_status = orig_status

    # 目录扫描（v0.1）：requirements*.txt + pyproject.toml
    proj = tmp / "proj"
    (proj / ".venv").mkdir(parents=True)
    (proj / "requirements.txt").write_text("requests==2.31.0\nflask\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[project]\ndependencies = ["httpx>=0.27", "pydantic"]\n\n'
        '[tool.poetry.dependencies]\npython = "^3.11"\nredis = "^5"\n', encoding="utf-8")
    (proj / ".venv" / "requirements.txt").write_text("should-be-skipped\n", encoding="utf-8")
    names_proj, scanned = sf.scan_project(proj)
    check("SF 目录扫描（含 pyproject/poetry）",
          {"requests", "flask", "httpx", "pydantic", "redis"} <= set(names_proj)
          and "should-be-skipped" not in names_proj
          and len(scanned) == 2, str(names_proj))
    r_dir = run([sys.executable, str(ROOT / "slopfirewall" / "slopfirewall.py"),
                 "scan", str(proj), "--no-cache"])
    check("SF CLI 目录扫描端到端", "requests" in r_dir.stdout and "扫描 2 个清单文件" in r_dir.stdout,
          r_dir.stdout[:120])

    # ---------- 3. ReplayKit ----------
    import replaykit as rk

    trace = tmp / "trace.jsonl"
    with rk.Recorder(trace) as rec:
        rec.next_step("search", {"q": "w"}, {"temp": 25})
        rec.next_step("calc", {"x": 2}, 4)
    r = rk.replay(trace, {"search": lambda a: {"temp": 25}, "calc": lambda a: 4})
    check("RK 重放一致", r["first_divergence"] is None and r["compared"] == 2)

    trace2 = tmp / "trace2.jsonl"
    with rk.Recorder(trace2) as rec:
        rec.next_step("a", {"n": 1}, 10)
        rec.next_step("b", {"n": 2}, 20)
        rec.next_step("c", {"n": 3}, 30)
    r2 = rk.replay(trace2, {"a": lambda a: 10, "b": lambda a: 999, "c": lambda a: 30})
    fd = r2["first_divergence"]
    check("RK 定位首个分歧步", fd is not None and fd["step"] == 1 and fd["replayed"] == 999,
          json.dumps(fd, ensure_ascii=False)[:100])
    r3 = rk.replay(trace2, {"a": lambda a: (_ for _ in ()).throw(ValueError("boom"))})
    check("RK 工具异常=分歧", r3["first_divergence"] is not None
          and r3["first_divergence"]["step"] == 0)
    r_cli = run([sys.executable, str(ROOT / "replaykit" / "replaykit.py"),
                 "replay", str(trace2), "--tools", str(_write_tools_module(tmp))])
    check("RK CLI 分歧退出码 1", r_cli.returncode == 1 and "第 **1 步**" in r_cli.stdout.replace("**", "**"),
          r_cli.stdout[:120])

    # 不稳定步识别（v0.1）：时间类工具每次输出都不同 → 归为不稳定而非分歧
    import itertools as _it
    counter = _it.count()
    trace3 = tmp / "trace3.jsonl"
    with rk.Recorder(trace3) as rec:
        rec.next_step("now", {}, 1759000000.0)   # 录制时的时钟值
        rec.next_step("calc", {"x": 2}, 4)
    r4 = rk.replay(trace3, {"now": lambda a: next(counter), "calc": lambda a: 4}, repeat=3)
    check("RK 不稳定步不算分歧", r4["first_divergence"] is None
          and len(r4["unstable"]) == 1 and r4["unstable"][0]["tool"] == "now",
          json.dumps(r4, ensure_ascii=False)[:150])
    r5 = rk.replay(trace3, {"now": lambda a: 1759000000.0, "calc": lambda a: 4}, repeat=3)
    check("RK 稳定工具 + repeat 不误报", r5["first_divergence"] is None and not r5["unstable"])

    # 双轨迹对比（v0.1）
    trace_a = tmp / "ta.jsonl"
    trace_b = tmp / "tb.jsonl"
    with rk.Recorder(trace_a) as rec:
        rec.next_step("search", {"q": "w"}, {"hits": [1, 2]})
        rec.next_step("calc", {"x": 2}, 4)
    with rk.Recorder(trace_b) as rec:
        rec.next_step("search", {"q": "weather"}, {"hits": [1, 2]})  # 第 0 步参数就分叉
        rec.next_step("calc", {"x": 2}, 4)
    rc = rk.compare(trace_a, trace_b)
    check("RK compare 定位首个分歧（args）", rc["first_divergence"] is not None
          and rc["first_divergence"]["step"] == 0 and rc["first_divergence"]["kind"] == "args",
          json.dumps(rc["first_divergence"], ensure_ascii=False)[:120])
    with rk.Recorder(trace_b) as rec:
        rec.next_step("search", {"q": "w"}, {"hits": [1, 2, 3]})  # 结果不同
        rec.next_step("calc", {"x": 2}, 4)
    rc2 = rk.compare(trace_a, trace_b)
    check("RK compare 定位结果分歧", rc2["first_divergence"]["kind"] == "result"
          and rc2["first_divergence"]["step"] == 0)
    identical = tmp / "same.jsonl"
    with rk.Recorder(identical) as rec:
        rec.next_step("search", {"q": "w"}, {"hits": [1]})
    rc3 = rk.compare(identical, identical)
    check("RK compare 完全一致", rc3["first_divergence"] is None)

    # ---------- 4. PostTrain-Doctor ----------
    import doctor as ptd

    eps = []
    for i in range(30):  # 前 20 步正常，后 10 步 reward 高但 success=false + 长度膨胀
        hacking = i >= 20
        eps.append({"step": i, "reward": 0.9 if hacking else 0.4,
                    "success": not hacking, "ref_reward": 0.35,
                    "length": 300 if i < 15 else 1200, "format_ok": not hacking})
    for i in range(5):  # 制造失败但没过高分线：reward 比 ref 明显高、success=false → 只进 F2 不进 F1
        eps.append({"step": 30 + i, "reward": 0.7, "success": False,
                    "ref_reward": 0.3, "length": 500, "format_ok": True})
    findings = ptd.analyze(eps)
    f1 = next(f for f in findings if f["id"] == "F1")
    f2 = next(f for f in findings if f["id"] == "F2")
    f3 = next(f for f in findings if f["id"] == "F3")
    f4 = next(f for f in findings if f["id"] == "F4")
    check("PTD F1 RHR 代理报警", f1["alarm"] and f1["value"] > 0.2)
    check("PTD F2 NRFR>RHR（制造失败）", f2["alarm"] and f2["value"] > f1["value"])
    check("PTD F3 长度膨胀报警", f3["alarm"] and f3["value"] > 1.5)
    check("PTD F4 格式逃逸报警", f4["alarm"])
    good = [{"step": i, "reward": 0.4, "success": True, "length": 100} for i in range(20)]
    check("PTD 正常数据不报警", not any(f["alarm"] for f in ptd.analyze(good)))

    # F5 方差塌缩（v0.1）：前段奖励有波动，后段锁死在同一值
    collapse = ([0.2, 0.5, 0.35, 0.6, 0.45, 0.3, 0.55, 0.4] * 2
                + [0.9] * 16)
    f5 = next(f for f in ptd.analyze([{"step": i, "reward": v} for i, v in enumerate(collapse)])
              if f["id"] == "F5")
    check("PTD F5 方差塌缩报警", f5["alarm"] and f5["value"] < 0.2, str(f5))
    healthy = ([0.3, 0.5, 0.4, 0.6, 0.35, 0.55] * 2
               + [0.8, 0.95, 0.7, 0.85, 0.9, 0.75] * 3)
    f5b = next(f for f in ptd.analyze([{"step": i, "reward": v} for i, v in enumerate(healthy)])
               if f["id"] == "F5")
    check("PTD F5 健康收敛不误报", not f5b["alarm"], str(f5b))

    # F6 长度-奖励相关（v0.1）：奖励几乎完全由长度决定
    import random as _random

    _random.seed(7)
    gaming = [{"step": i, "reward": min(1.0, 0.2 + L / 2000), "length": L}
              for i, L in enumerate(_random.randint(100, 2000) for _ in range(60))]
    f6 = next(f for f in ptd.analyze(gaming) if f["id"] == "F6")
    check("PTD F6 长度-奖励强相关报警", f6["alarm"], str(f6))
    flat = [{"step": i, "reward": _random.random(), "length": _random.randint(100, 2000)}
            for i in range(60)]
    f6b = next(f for f in ptd.analyze(flat) if f["id"] == "F6")
    check("PTD F6 无相关不报警", not f6b["alarm"], str(f6b))

    # 复查样本导出（v0.1）
    export_f = tmp / "review.jsonl"
    n = ptd.export_review(eps, 0.8, export_f)
    exported = [json.loads(ln) for ln in export_f.read_text("utf-8").splitlines()]
    check("PTD 复查导出（高 reward 失败样本）",
          n == 10 and len(exported) == 10
          and all(float(e["reward"]) >= 0.8 and not e["success"] for e in exported),
          f"n={n}")

    # ---------- 5. OpsBench ----------
    import score as ob

    case = ROOT / "opsbench" / "cases" / "case-001"
    r_good, c_good = ob.score_case(case, ROOT / "opsbench" / "cases" / "case-001" / "answer.example.md")
    check("OB 标准答案 PASS", c_good == ob.EXIT_PASS and "PASS" in r_good, r_good[:150])
    bad_answer = tmp / "bad.md"
    bad_answer.write_text("是 14:02 的发布引起的，建议马上回滚并给数据库扩容加机器。", encoding="utf-8")
    r_bad, c_bad = ob.score_case(case, bad_answer)
    check("OB 干扰答案 FAIL（根因错+禁现词）", c_bad == ob.EXIT_FAIL and "FAIL" in r_bad, r_bad[:150])

    # case-002（v0.1）：连接泄漏模式
    case2 = ROOT / "opsbench" / "cases" / "case-002"
    r2g, c2g = ob.score_case(case2, case2 / "answer.example.md")
    check("OB case-002 标准答案 PASS", c2g == ob.EXIT_PASS and "PASS" in r2g, r2g[:150])
    bad2 = tmp / "bad2.md"
    bad2.write_text("是周日发布引起的，建议马上回滚发布版本，并给数据库扩容提高 max_connections。", encoding="utf-8")
    r2b, c2b = ob.score_case(case2, bad2)
    check("OB case-002 干扰答案 FAIL（回滚禁现词+必答项未中）",
          c2b == ob.EXIT_FAIL and "回滚" in r2b and "一票否决" in r2b, r2b[:150])

    failed = [n for n, ok in results if not ok]
    print(f"\n{'全部通过' if not failed else '失败: ' + ', '.join(failed)}"
          f"（{len(results) - len(failed)}/{len(results)}）")
    return 1 if failed else 0


def _write_tools_module(tmp: Path) -> Path:
    """replaykit CLI 测试用的工具模块：b 的实现被改坏（20 → 999）。"""
    p = tmp / "mytools.py"
    p.write_text(
        "TOOLS = {\n"
        "    'a': lambda args: 10,\n"
        "    'b': lambda args: 999,   # 改坏了的实现\n"
        "    'c': lambda args: 30,\n"
        "}\n", encoding="utf-8")
    return p


if __name__ == "__main__":
    sys.exit(main())
