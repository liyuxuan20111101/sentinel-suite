#!/usr/bin/env python3
"""sentinel.py 统一入口的冒烟测试：命令糖、版本、帮助、自带案例解析。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "sentinel.py"

passed = failed = 0


def run(args, timeout=60):
    return subprocess.run([sys.executable, str(ENTRY), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, cwd=str(ROOT))


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail[:300]}")


r = run(["--version"])
check("--version", r.returncode == 0 and "sentinel-suite" in r.stdout, r.stdout + r.stderr)

r = run([])
check("无参数（管道）输出帮助", r.returncode == 0 and "demo" in r.stdout, r.stdout + r.stderr)

r = run(["doctor", "examples/posttrain/episodes.jsonl"])
check("doctor 免 analyze 子命令：报出指纹",
      r.returncode == 1 and "F1" in r.stdout, r.stdout + r.stderr)

r = run(["slop", "scan", "examples/slop"])
check("slop scan 目录：抓到幻觉包名",
      r.returncode == 1 and "reqests" in r.stdout, r.stdout + r.stderr)

r = run(["ops", "--list"])
check("ops --list 列出案例",
      r.returncode == 0 and "case-001" in r.stdout and "case-002" in r.stdout,
      r.stdout + r.stderr)

r = run(["ops", "case-001"])
check("ops 只给案例：展示案情与提示",
      r.returncode == 0 and "incident.json" in r.stdout, r.stdout + r.stderr)

r = run(["replay", "examples/replay/trace-good.jsonl", "--tools", "examples/replay/tools.py"])
check("replay 免子命令：干净轨迹 0 分歧",
      r.returncode == 0 and "一致" in r.stdout, r.stdout + r.stderr)

r = run(["diff", "examples/diff/new_price.py"])
check("diff 单文件糖：无 .bak 时给出清晰指引",
      r.returncode == 2 and ".bak" in r.stdout, r.stdout + r.stderr)

r = run(["diff", "--old", "examples/diff/old_price.py",
         "--new", "examples/diff/new_price.py", "--auto"], timeout=120)
check("diff --auto：抓到行为反例",
      r.returncode == 1 and "行为不同" in r.stdout, r.stdout + r.stderr)

r = run(["demo"], timeout=300)
check("demo 全流程跑通", r.returncode == 0 and "演示结束" in r.stdout, r.stdout + r.stderr)

print(f"\n通过 {passed}/{passed + failed}")
sys.exit(1 if failed else 0)
