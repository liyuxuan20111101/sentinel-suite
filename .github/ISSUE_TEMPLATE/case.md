---
name: RCA 案例
about: 向 OpsBench 提交新的根因分析案例
labels: opsbench
---
<!-- 案例用合成数据；真实事故请脱敏到看不出原公司/系统 -->

**故障模式**（一句话）：

**干扰项设计**（必填——没有干扰项的案例只会奖励关键词堆砌）：

**附件**：按 `opsbench/cases/case-001` 的结构给 incident.json + ground_truth.json + answer.example.md

**自测**：answer.example.md 过 PASS、干扰答案过 FAIL：
- [ ] 已用 `python opsbench/score.py` 自测
