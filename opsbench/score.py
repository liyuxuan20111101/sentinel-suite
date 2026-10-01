#!/usr/bin/env python3
"""OpsBench — AIOps 的 SWE-bench（根因分析基准，v0 评分器）。

背景：RCA agent 端到端完美准确率仅 3.9%–12.5%，而厂商宣称"MTTR 降 40–58%"
——中间缺一把**中立的尺子**。这是公共品，无人有商业动机做。

案例结构（opsbench/cases/<case-id>/）：
  incident.json     症状/告警/日志/指标时间线（喂给被测 agent 的全部输入）
  ground_truth.json 根因 + 评分量表（每项含权重、必中关键词组、禁现词）
  answer.md         被测 agent 的 RCA 结论（文本）

评分（v0 关键词匹配，诚实标注局限）：
  - 每个量表项：答案命中 any_of 之一 → 得该项权重；命中 forbid → 该项记 0
  - required 项未命中 → 整案 FAIL（哪怕总分够）
  - 总分 ≥ pass_threshold 且 required 全中 → PASS
  v0 的关键词匹配会漏掉同义表述——语义评分（LLM judge + 人工校准）在路线图上。

用法：
  python opsbench/score.py cases/case-001 answer.md
退出码：0=PASS；1=FAIL；2=出错。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_PASS, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


def _hit(text: str, groups: list[list[str]]) -> bool:
    """任一关键词组的任一变体出现即算命中（组内是同义/多语言变体）。"""
    return any(kw.lower() in text for group in groups for kw in group)


def _normalize(text: str) -> str:
    """大小写 + 常见全角/变体归一（v0.1：全角空格/逗号/冒号 → 半角，全角字母数字 → 半角）。"""
    table = str.maketrans({
        "，": ",", "：": ":", "；": ";", "（": "(", "）": ")", "　": " ",
        "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
        "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    })
    return text.translate(table).lower()


def score_case(case_dir: Path, answer_path: Path) -> tuple[str, int]:
    gt_path = Path(case_dir) / "ground_truth.json"
    if not gt_path.exists():
        return f"opsbench：案例缺 ground_truth.json（{gt_path}）", EXIT_ERROR
    try:
        gt = json.loads(gt_path.read_text("utf-8"))
        answer = _normalize(Path(answer_path).read_text("utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        return f"opsbench：读取失败 {exc}", EXIT_ERROR

    items = gt.get("items", [])
    if not items:
        return "opsbench：量表为空", EXIT_ERROR
    total = sum(float(it.get("weight", 0)) for it in items) or 1.0

    lines, score, required_missed = [], 0.0, []
    for it in items:
        w = float(it.get("weight", 0))
        forbidden = _hit(answer, it.get("forbid", []))
        if it.get("any_of"):
            matched = _hit(answer, it["any_of"])
        else:
            matched = True  # 只含 forbid 的项：答案没踩禁现词就算过
        if matched and not forbidden:
            score += w
            lines.append(f"  ✓ [{w:.2f}] {it.get('label', it.get('id', ''))}")
        else:
            miss = "（命中禁现词）" if forbidden else ""
            lines.append(f"  ✗ [ 0  ] {it.get('label', it.get('id', ''))}{miss}")
            if it.get("required"):
                required_missed.append(it.get("id", "?"))

    ratio = score / total
    passed = ratio >= float(gt.get("pass_threshold", 1.0)) and not required_missed
    verdict = "PASS" if passed else "FAIL"
    out = [f"opsbench {gt.get('case', case_dir.name)}：{verdict}（得分 {ratio:.0%}，"
           f"门槛 {float(gt.get('pass_threshold', 1.0)):.0%}）"]
    out += lines
    if required_missed:
        out.append(f"  必答项未命中：{'、'.join(required_missed)} → 一票否决")
    return "\n".join(out), (EXIT_PASS if passed else EXIT_FAIL)


def main() -> int:
    ap = argparse.ArgumentParser(description="OpsBench RCA 评分器（v0）")
    ap.add_argument("case", help="案例目录（含 ground_truth.json）")
    ap.add_argument("answer", help="被测 agent 的 RCA 结论（文本）")
    a = ap.parse_args()
    report, code = score_case(Path(a.case), Path(a.answer))
    print(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
