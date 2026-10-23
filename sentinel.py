#!/usr/bin/env python3
"""sentinel-suite 统一入口（零依赖，Python 3.9+）。

用法:
  python sentinel.py demo              一分钟跑通全部五个工具（用自带示例）
  python sentinel.py web [--port N]    启动本地 Web 控制台（默认 127.0.0.1:8642）
  python sentinel.py diff --help       DiffVerifier  改动行为等价性验证
  python sentinel.py slop --help       SlopFirewall  包幻觉 / 供应链门禁
  python sentinel.py replay --help     ReplayKit     Agent 轨迹重放对比
  python sentinel.py doctor --help     PostTrain-Doctor  reward hacking 指纹
  python sentinel.py ops --help        OpsBench      RCA 结论评分

ops 子命令额外支持: `ops --list` 列出自带案例；case 参数可直接写 `case-001`
这样的案例编号（自动解析到 opsbench/cases/）；answer 可以是文件路径，也可以
直接给一段文本。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXIT_USAGE = 3

# 子命令 → (模块文件, 提示语)。模块 main() 自己解析 sys.argv，
# 所以转发前把 argv[0] 改成 "sentinel.py <cmd>"，--help 里显示得体。
TOOLS = {
    "diff":   ("diffverifier/diffverifier.py", "AI 补丁行为等价性验证"),
    "slop":   ("slopfirewall/slopfirewall.py", "包幻觉 / 供应链门禁"),
    "replay": ("replaykit/replaykit.py", "Agent 轨迹重放对比"),
    "doctor": ("posttrain-doctor/doctor.py", "RL 后训练 reward hacking 指纹"),
    "ops":    ("opsbench/score.py", "OpsBench RCA 评分"),
}

BUNDLED_CASES = ROOT / "opsbench" / "cases"


def _load(rel: str):
    """按路径加载工具模块（posttrain-doctor 目录名带连字符，无法常规 import）。"""
    path = ROOT / rel
    name = "sentinel_" + path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dispatch(cmd: str, rest: list[str]) -> int:
    rel, _ = TOOLS[cmd]
    if cmd == "ops":
        rest = _prep_ops(rest)
    if cmd == "replay" and rest and rest[0] not in ("inspect", "replay", "compare",
                                                    "-h", "--help"):
        # 便捷：`sentinel.py replay <trace> --tools …` 自动补 replay 子命令
        rest = ["replay"] + rest
    sys.argv[0] = f"sentinel.py {cmd}"
    sys.argv[1:] = rest
    return _load(rel).main()


def _prep_ops(args: list[str]) -> list[str]:
    """ops 增强：--list 列自带案例；case-XXX 解析到内置目录；文本答案落临时文件。"""
    if args and args[0] in ("--list", "list"):
        if not BUNDLED_CASES.is_dir():
            return args
        print("自带案例（opsbench/cases/）：")
        for d in sorted(BUNDLED_CASES.iterdir()):
            if (d / "ground_truth.json").exists():
                print(f"  {d.name}")
        print("用法：sentinel.py ops case-001 <answer 文件或一段文本>")
        raise SystemExit(0)
    args = list(args)
    if len(args) >= 1:
        case = Path(args[0])
        if not case.exists() and not case.is_absolute():
            cand = BUNDLED_CASES / args[0]
            if (cand / "ground_truth.json").exists():
                args[0] = str(cand)
    if len(args) >= 2:
        ans = Path(args[1])
        if not ans.exists():
            tmp = Path(tempfile.gettempdir()) / "sentinel_ops_answer.md"
            tmp.write_text(args[1], encoding="utf-8")
            args[1] = str(tmp)
    return args


def _run_demo_step(title: str, argv: list[str]) -> None:
    print(f"\n{'=' * 62}\n[{title}]\n$ python sentinel.py {' '.join(argv)}\n{'-' * 62}",
          flush=True)
    proc = subprocess.run([sys.executable, str(ROOT / "sentinel.py"), *argv])
    if proc.returncode not in (0,):
        print(f"（该工具退出码 {proc.returncode}：0=一致/干净，1=发现差异/指纹/不通过，见上方报告）")


def _demo() -> int:
    """用 examples/ 里的自带示例依次演示五个工具。"""
    print("sentinel-suite 五分钟演示：全部示例在 examples/ 下，可直接改着玩。\n"
          "说明：DiffVerifier / doctor / ops 故意演示「发现问题」，退出码非 0 是预期。")

    _run_demo_step("1/5 DiffVerifier：AI 改过的定价函数，行为等价吗？",
                   ["diff", "--old", "examples/diff/old_price.py",
                    "--new", "examples/diff/new_price.py", "--auto"])

    _run_demo_step("2/5 SlopFirewall：requirements.txt 里有拼错的包名吗？",
                   ["slop", "scan", "examples/slop/requirements.txt"])

    _run_demo_step("3/5 ReplayKit：先重放一条「无分歧」的轨迹",
                   ["replay", "replay", "examples/replay/trace-good.jsonl",
                    "--tools", "examples/replay/tools.py"])

    _run_demo_step("3b/5 ReplayKit：再重放一条「结果对不上」的轨迹",
                   ["replay", "replay", "examples/replay/trace-broken.jsonl",
                    "--tools", "examples/replay/tools.py"])

    _run_demo_step("4/5 PostTrain-Doctor：这份 RL 训练日志有 reward hacking 吗？",
                   ["doctor", "analyze", "examples/posttrain/episodes.jsonl"])

    _run_demo_step("5/5 OpsBench：给示例 RCA 结论打分（案例 case-001）",
                   ["ops", "case-001", str(BUNDLED_CASES / "case-001" / "answer.example.md")])

    print(f"\n{'=' * 62}\n演示结束。下一步：python sentinel.py web 打开本地控制台；"
          f"各工具用法见 python sentinel.py <diff|slop|replay|doctor|ops> --help")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "demo":
        return _demo()
    if cmd == "web":
        sys.argv[0] = "sentinel.py web"
        sys.argv[1:] = rest
        return _load("web/server.py").main()
    if cmd in TOOLS:
        return _dispatch(cmd, rest)
    print(f"未知子命令：{cmd}\n")
    print(__doc__.strip())
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
