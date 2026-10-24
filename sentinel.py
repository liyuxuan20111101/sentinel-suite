#!/usr/bin/env python3
"""sentinel-suite 统一入口（零依赖，Python 3.9+）。

最快上手:
  python sentinel.py            交互菜单（在终端里直接选）
  python sentinel.py demo       一分钟跑通全部五个工具（用自带示例）
  python sentinel.py web        启动本地 Web 控制台（自动开浏览器）

命令糖（比直接调各工具更短）:
  python sentinel.py diff 改过的文件.py     .bak 对比 + 自动边界用例
  python sentinel.py slop scan             扫描当前目录（requirements*/pyproject）
  python sentinel.py slop scan 目录        扫描指定目录
  python sentinel.py doctor 轨迹.jsonl     等价于 doctor analyze
  python sentinel.py ops --list            列出自带 RCA 案例
  python sentinel.py ops case-001 答案     答案可以是文件路径或一段文本

完整用法:
  python sentinel.py <diff|slop|replay|doctor|ops> --help
  python sentinel.py --version
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXIT_USAGE = 3
VERSION = "0.4.0"

# 子命令 → 模块文件。各工具 main() 自己解析 sys.argv，
# 转发前把 argv[0] 改成 "sentinel.py <cmd>"，--help 里显示得体。
TOOLS = {
    "diff":   "diffverifier/diffverifier.py",
    "slop":   "slopfirewall/slopfirewall.py",
    "replay": "replaykit/replaykit.py",
    "doctor": "posttrain-doctor/doctor.py",
    "ops":    "opsbench/score.py",
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
    rel = TOOLS[cmd]
    if cmd == "ops":
        rest = _prep_ops(rest)
    if cmd == "replay" and rest and rest[0] not in ("inspect", "replay", "compare",
                                                    "-h", "--help"):
        # 便捷：`sentinel.py replay <trace> --tools …` 自动补 replay 子命令
        rest = ["replay"] + rest
    if cmd == "doctor" and rest and rest[0] not in ("analyze", "-h", "--help") \
            and not str(rest[0]).startswith("-"):
        # 便捷：`sentinel.py doctor <log>` 等价于 doctor analyze <log>
        rest = ["analyze"] + rest
    if cmd == "diff" and rest and not str(rest[0]).startswith("-"):
        # 便捷：`sentinel.py diff 文件.py` = .bak 对比 + 自动边界用例
        rest = ["--path", rest[0], "--auto", *rest[1:]]
    sys.argv[0] = f"sentinel.py {cmd}"
    sys.argv[1:] = rest
    return _load(rel).main()


def _prep_ops(args: list[str]) -> list[str]:
    """ops 增强：--list 列自带案例；case-XXX 解析到内置目录；文本答案落临时文件；
    只给案例不给答案时展示案情与上手提示。"""
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
    if len(args) == 1 and (BUNDLED_CASES / Path(args[0]).name).is_dir():
        case_dir = BUNDLED_CASES / Path(args[0]).name
        incident = case_dir / "incident.json"
        if incident.exists():
            print(f"—— {case_dir.name} 案情（incident.json）——")
            print(incident.read_text("utf-8").strip())
        print(f"\n把你的 RCA 结论作为第二个参数传入：\n"
              f"  python sentinel.py ops {Path(args[0]).name} \"根因是……处置是……\"\n"
              f"参考答案：{case_dir / 'answer.example.md'}")
        raise SystemExit(0)
    if len(args) >= 2:
        ans = Path(args[1])
        if not ans.exists():
            tmp = Path(tempfile.gettempdir()) / "sentinel_ops_answer.md"
            tmp.write_text(args[1], encoding="utf-8")
            args[1] = str(tmp)
    return args


def _run_cli(argv: list[str]) -> None:
    print("\n" + "=" * 62)
    print("运行子命令：" + " ".join(argv))
    print("-" * 62, flush=True)
    # 参数列表形式调用，不经 shell 解析
    proc = subprocess.run([sys.executable, str(ROOT / "sentinel.py"), *argv],
                          shell=False)
    if proc.returncode != 0:
        print(f"（该工具退出码 {proc.returncode}：0=一致/干净，1=发现问题，2=无法判定）")


_DEMO_STEPS = [
    ("1/5 DiffVerifier：AI 改过的定价函数，行为等价吗？",
     ["diff", "--old", "examples/diff/old_price.py",
      "--new", "examples/diff/new_price.py", "--auto"]),
    ("2/5 SlopFirewall：requirements.txt 里有拼错的包名吗？",
     ["slop", "scan", "examples/slop/requirements.txt"]),
    ("3/5 ReplayKit：先重放一条「无分歧」的轨迹",
     ["replay", "replay", "examples/replay/trace-good.jsonl",
      "--tools", "examples/replay/tools.py"]),
    ("3b/5 ReplayKit：再重放一条「结果对不上」的轨迹",
     ["replay", "replay", "examples/replay/trace-broken.jsonl",
      "--tools", "examples/replay/tools.py"]),
    ("4/5 PostTrain-Doctor：这份 RL 训练日志有 reward hacking 吗？",
     ["doctor", "examples/posttrain/episodes.jsonl"]),
    ("5/5 OpsBench：给示例 RCA 结论打分（案例 case-001）",
     ["ops", "case-001", str(BUNDLED_CASES / "case-001" / "answer.example.md")]),
]


def _demo() -> int:
    """用 examples/ 里的自带示例依次演示五个工具。"""
    print("sentinel-suite 一分钟演示：全部示例在 examples/ 下，可直接改着玩。\n"
          "说明：DiffVerifier / doctor / ops 故意演示「发现问题」，退出码非 0 是预期。")
    for title, argv in _DEMO_STEPS:
        print(f"\n[{title}]", flush=True)
        _run_cli(argv)
    print("\n" + "=" * 62)
    print("演示结束。下一步：python sentinel.py web 打开本地控制台；"
          "各工具用法见 python sentinel.py <diff|slop|replay|doctor|ops> --help")
    return 0


_MENU_CMD = {"3": ("diff", 0), "4": ("slop", 1), "5": ("replay", 2),
             "6": ("doctor", 4), "7": ("ops", 5)}


def _menu() -> int:
    """交互菜单：无参数且在真终端里运行时出现。"""
    while True:
        print(f"""
╔══════════════════════════════════════════════════════╗
║  sentinel-suite  v{VERSION}  —  五个验证/诊断工具          ║
╚══════════════════════════════════════════════════════╝
  1) 一分钟演示五个工具（第一次用选这个）
  2) 启动 Web 控制台（图形界面）
  3) DiffVerifier     验证改动有没有偷偷改行为
  4) SlopFirewall     检查包名是否真实存在
  5) ReplayKit        重放 Agent 轨迹找分歧
  6) PostTrain-Doctor 检查 RL 是否在骗 reward
  7) OpsBench         给 RCA 根因分析打分
  q) 退出""")
        try:
            choice = input("选择> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("q", "quit", "exit"):
            return 0
        if choice == "1":
            _demo()
        elif choice == "2":
            return _dispatch_web([])
        elif choice in _MENU_CMD:
            cmd, idx = _MENU_CMD[choice]
            title, argv = _DEMO_STEPS[idx]
            print(f"\n[{title}]", flush=True)
            _run_cli(argv)
            print(f"\n用它处理自己的数据：python sentinel.py {cmd} --help")
        else:
            print("无效选择，请输入 1-7 或 q")


def _dispatch_web(rest: list[str]) -> int:
    sys.argv[0] = "sentinel.py web"
    sys.argv[1:] = rest
    return _load("web/server.py").main()


def _help() -> None:
    print(__doc__.strip())


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-V", "--version", "version"):
        print(f"sentinel-suite {VERSION}")
        return 0
    if not argv or argv[0] in ("-h", "--help", "help"):
        # 真终端里无参数 → 交互菜单；管道/脚本里 → 纯文本帮助
        if not argv:
            try:
                if sys.stdin.isatty() and sys.stdout.isatty():
                    return _menu()
            except Exception:
                pass
        _help()
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "demo":
        return _demo()
    if cmd == "web":
        return _dispatch_web(rest)
    if cmd in TOOLS:
        return _dispatch(cmd, rest)
    print(f"未知子命令：{cmd}\n")
    _help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
