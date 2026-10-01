# OpsBench — AIOps 的 SWE-bench（根因分析基准）

## 🇬🇧 English

**OpsBench** is a neutral benchmark for root-cause-analysis (RCA) agents. End-to-end perfect accuracy sits at 3.9%–12.5% while vendors claim "MTTR −40–58%" — the missing piece is a neutral ruler. This is a public good; nobody has a commercial incentive to build it, so it should be open.

**What it does**: a case format (`incident.json` = symptoms/alerts/logs/metrics fed to the agent; `ground_truth.json` = root cause + weighted rubric with synonym groups, forbidden-answer patterns, and veto items) plus a zero-dependency scorer. Each case embeds deliberately designed distractors — cases without distractors only reward keyword stuffing. v0.1 ships two cases: Redis eviction storm, and a database connection leak.

```bash
python opsbench/score.py opsbench/cases/case-001 opsbench/cases/case-001/answer.example.md
# PASS（得分 100%，门槛 80%）
```

> 中文说明在下方 ↓

---
**RCA agent 端到端完美准确率仅 3.9%–12.5%，而厂商宣称"MTTR 降 40–58%"**——中间缺一把**中立的尺子**。这是公共品，无人有商业动机做，所以它该是个开放基准。

## v0 是什么

- **案例格式**：`cases/<id>/incident.json`（症状/告警/日志/指标时间线，即喂给被测 agent 的全部输入）+ `ground_truth.json`（根因 + 评分量表）。
- **评分器**（`score.py`，零依赖）：对 agent 的 RCA 文本按量表打分。量表项有权重、必中关键词组（组内是同义/多语言变体）、禁现词（防"无脑扩容"式错误答案）；必答项一票否决。
- **case-001**：一个合成但真实感的示例——Redis 满内存淘汰热 key → 缓存击穿 → DB 连接池打满，故意埋了两个干扰项（一次无辜的发布、作为结果而非原因的 DB 慢查询）。`answer.example.md` 是演示用标准答案。

现有案例：

| 案例 | 故障模式 | 干扰项设计 |
|---|---|---|
| `case-001` | Redis 满内存淘汰热 key → 缓存击穿 → DB 连接池打满 | 一次无辜的发布；作为结果而非原因的 DB 慢查询 |
| `case-002` | 新查询代码连接泄漏（idle in transaction）→ 连接池耗尽 | 发布时间与故障时间错位（流量才是触发器）；"数据库慢"错觉；诱导"回滚发布"的禁现词 |

```bash
python opsbench/score.py opsbench/cases/case-001 opsbench/cases/case-001/answer.example.md
# PASS（得分 100%，门槛 80%）
```

v0.1 评分前对答案做大小写/全角归一，减少无谓的匹配失败。

退出码：`0` PASS / `1` FAIL / `2` 出错——CI 可直接用。

## 诚实的局限（v0）

关键词匹配会漏掉同义表述，也可能被堆砌关键词骗过。v0 的定位是**把尺子立起来**：案例格式、量表结构、一票否决的评分语义先标准化；语义评分（LLM judge + 人工校准集公开）是下一步，且校准集本身要接受社区审计——否则尺子自己就成了厂商话术。

## 路线图

1. 案例扩充（目标：分服务/分故障类型的多案例集，全部合成数据、附干扰项设计说明）
2. 语义评分层：LLM judge 按量表打分 + 公开校准集，与关键词层双轨对照
3. 排行榜协议：统一输入上下文窗口、统一工具权限、报告"完美准确率"而不是 MTTR 百分比
