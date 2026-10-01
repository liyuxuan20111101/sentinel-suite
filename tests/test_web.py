#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web 前端 API 冒烟：起 server.py（随机端口），打每个接口各一次。"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{'[PASS]' if cond else '[FAIL]'} {name}" + (f"（{detail}）" if detail and not cond else ""))


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="webtest-"))
    old_f = tmp / "calc_old.py"
    new_f = tmp / "calc_new.py"
    old_f.write_text("def calc(a, b):\n    return a + b\n", encoding="utf-8")
    new_f.write_text("def calc(a, b):\n    return a * b\n", encoding="utf-8")

    proc = subprocess.Popen([sys.executable, str(ROOT / "web" / "server.py"),
                             "--port", str(PORT), "--no-browser"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(20):
            try:
                urllib.request.urlopen(BASE + "/api/ping", timeout=2)
                break
            except Exception:
                time.sleep(0.3)
        else:
            print("[FAIL] 服务没有起来")
            return 1

        check("静态页可访问", b"AI Tool Suite" in urllib.request.urlopen(BASE + "/", timeout=5).read())

        r = post("/api/diffverifier", {"old": str(old_f), "new": str(new_f), "calls": "calc(2, 3)"})
        check("diffverifier 接口抓到差异", r["code"] == 1 and "行为不同" in r["report"], r["report"][:80])

        r = post("/api/diffverifier", {"old": str(old_f), "new": str(new_f), "auto": True})
        check("diffverifier 自动用例接口", r["code"] == 1 and "行为不同" in r["report"], r["report"][:80])

        r = post("/api/slopfirewall", {"text": "requests\nfake-pkg-zz", "no_cache": True})
        check("slopfirewall 接口三态判定", r["code"] == 1 and "❌ fake-pkg-zz" in r["report"]
              and "✅ requests" in r["report"], r["report"][:100])

        trace = tmp / "trace.jsonl"
        trace.write_text(json.dumps({"step": 0, "tool": "f", "args": {}, "result": 1}) + "\n", encoding="utf-8")
        tools = tmp / "tools.py"
        tools.write_text("TOOLS = {'f': lambda a: 1}\n", encoding="utf-8")
        r = post("/api/replaykit", {"trace_path": str(trace), "tools_path": str(tools)})
        check("replaykit 接口重放一致", r["code"] == 0 and "全部一致" in r["report"], r["report"][:80])

        eps = "\n".join(json.dumps({"step": i, "reward": 0.9 if i >= 5 else 0.4,
                                    "success": i < 5, "ref_reward": 0.3, "length": 100})
                        for i in range(10))
        r = post("/api/posttrain", {"text": eps})
        check("posttrain 接口检出指纹", r["code"] == 1 and "F1" in r["report"], r["report"][:100])

        cases = urllib.request.urlopen(BASE + "/api/opsbench/cases", timeout=5)
        case_id = json.loads(cases.read().decode("utf-8"))["cases"][0]
        answer = (ROOT / "opsbench" / "cases" / case_id / "answer.example.md").read_text("utf-8")
        r = post("/api/opsbench", {"case": case_id, "answer": answer})
        check("opsbench 接口评分 PASS", r["code"] == 0 and "PASS" in r["report"], r["report"][:100])

        r = post("/api/diffverifier", {"calls": "f("})
        check("非法用例返回错误报告", r["code"] == 2 and "用例格式" in r["report"], str(r))
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    failed = [n for n, ok in results if not ok]
    print(f"\n{'全部通过' if not failed else '失败: ' + ', '.join(failed)}"
          f"（{len(results) - len(failed)}/{len(results)}）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
