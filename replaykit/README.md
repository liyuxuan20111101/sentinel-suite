# ReplayKit — Agent 可重放运行时（v0）

**60% 的 Agent 首次分歧发生在最前两步**，而行业普遍停在"日志层"——日志能看，不能跑。可重放性没有事实标准，ReplayKit 想补这一块。

## v0 是什么

一个零依赖的单文件库 + CLI，围绕一个唯一事实源：**JSONL 轨迹**（一行一步）。

```json
{"step": 0, "tool": "search", "args": {"q": "weather"}, "result": {"temp": 25}, "ts": 1769...}
{"step": 1, "tool": "calc", "args": {"expr": "25*1.1"}, "result": 27.5, "ts": 1769...}
```

三个动词：

- **record**：agent 每执行一步工具，把 (step, tool, args, result) 追加进轨迹；
- **inspect**：轨迹概览（步数、工具分布）；
- **replay**：把记录的输入重新喂给工具实现（当前版本或重构后的版本），逐步对比输出，**报告第一个分歧步**。

## 用法

```python
from replaykit import Recorder, replay

# 录制（在你的 agent 循环里加两行）
with Recorder.open("trace.jsonl") as rec:
    result = search(q="weather")
    rec.next_step("search", {"q": "weather"}, result)

# 重放（重构后/换模型后/修 bug 后）
report = replay("trace.jsonl", {"search": my_new_search})
print(report["first_divergence"])   # None=一致；否则含 step/args/recorded/replayed
```

```bash
python replaykit/replaykit.py inspect trace.jsonl
python replaykit/replaykit.py replay trace.jsonl --tools mytools.py   # mytools.py 暴露 TOOLS = {"search": fn, ...}
```

退出码可机读：`0` 重放一致 / `1` 发现分歧 / `2` 出错。

## 不稳定步与双轨迹对比（v0.1）

**时间/随机类工具天然不可重放**——`replay --repeat N` 把每步重放 N 次：
重放之间输出不一致的步归为「不稳定步」单独列出（不算回归），防止把时钟噪声当分歧。

```bash
python replaykit/replaykit.py replay trace.jsonl --tools mytools.py --repeat 3
```

**没有工具实现？直接对比同一 agent 的两次运行**：

```bash
python replaykit/replaykit.py compare run1.jsonl run2.jsonl
# 首次分歧：第 2 步（args）
#   两条轨迹第 2 步的输入参数不同 {……}
```

`compare` 逐步对齐两条轨迹，第一个不同处（工具选择 / 输入参数 / 输出 / 长度）即报——
换模型/换 prompt 之后跑两遍一比，行为漂移立刻现形。

## 设计立场

- **确定性重放**：不重放副作用（网络、时间、随机），只重放"输入 → 工具输出"的映射。想测新实现的行为差异，就把它注册为重放目标。
- **分歧即产品**：报告的第一行就是"第几步开始不一样"+ 该步的记录值/重放值。60% 的分歧在头两步——所以定位要按步，不要按"会话"。
- **坏行不假装**：轨迹里截断/损坏的行跳过并留行号，重放报告基于可信条目。

## 路线图

1. 与主流 agent 框架的钩子集成（一条 `with rk.trace():` 完成录制）
2. 轨迹签名与快照存储（重放含外部状态的步骤：环境快照 / mock 服务）
3. 分歧聚类：跨多次运行统计"哪些步天然不稳定"（时间类工具），避免假警报
