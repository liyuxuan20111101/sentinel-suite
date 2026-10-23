# examples/ — 每个工具的可运行示例 / Runnable examples for every tool

用 `python sentinel.py demo` 一次跑完全部；也可以单独跑下面任意一条。
Run all at once with `python sentinel.py demo`, or run any single command below.

| 目录 | 工具 | 单独运行 |
|---|---|---|
| `diff/` | DiffVerifier | `python sentinel.py diff --old examples/diff/old_price.py --new examples/diff/new_price.py --auto` |
| `slop/` | SlopFirewall | `python sentinel.py slop scan examples/slop/requirements.txt` |
| `replay/` | ReplayKit | `python sentinel.py replay replay examples/replay/trace-good.jsonl --tools examples/replay/tools.py` |
| `posttrain/` | PostTrain-Doctor | `python sentinel.py doctor analyze examples/posttrain/episodes.jsonl` |
| （OpsBench 自带案例） | OpsBench | `python sentinel.py ops case-001 <answer 文件或一段文本>` |

说明 / Notes:

- `diff/`：`new_price.py` 是 AI「顺手」加了负价抹零的版本——`--auto` 会用边界输入构造出反例。
  `new_price.py` adds a "defensive" zero-clamp for non-positive prices; `--auto` builds a counterexample from boundary inputs.
- `replay/`：`trace-good.jsonl` 重放应全部一致；`trace-broken.jsonl` 第 2 步记录结果与工具实际输出不符，用来演示分歧定位。
  `trace-good.jsonl` replays clean; `trace-broken.jsonl` has one step whose recorded result no longer matches the tool.
- `posttrain/`：60 条合成 episode，故意带 F1/F3/F4/F5/F6 指纹（高分但没做成、长度膨胀、方差塌缩、奖励跟随长度）。
  60 synthetic episodes carrying deliberate F1/F3/F4/F5/F6 fingerprints.
- `slop/`：第三个包名是故意拼错的（真实查询 PyPI，离线时会标「无法确认」）。
  The third package name is intentionally misspelled (queries PyPI live; offline it reports "unknown").
