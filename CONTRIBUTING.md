# 贡献指南

欢迎。这个仓库的每个工具都守同一条铁律：**诚实高于功能**——宁可标"无法确认"，不输出看起来精确的猜测。提 PR 前请先读这条。

## 环境

零第三方依赖，Python 3.9+。不需要装任何东西。

```bash
python tests/run_tests.py     # 工具回归
python tests/test_web.py      # Web API 冒烟（会起真实服务，含真网 PyPI 核查）
```

## 什么贡献最被需要（按优先级）

1. **SlopFirewall 种子库**：你在自己的生成流量里实测到的幻觉包名。要求：确认 https://pypi.org/project/<name>/ 返回 404，然后一行一个追加进 `slopfirewall/hallucinated_seeds.txt`。这比任何代码 PR 都有价值。
2. **OpsBench 案例**：按 `opsbench/cases/case-001` 的结构（incident.json + ground_truth.json + answer.example.md）。要求：必须写清干扰项设计——一个测试不出干扰项的案例只会奖励关键词堆砌。
3. **指纹/启发式**：给 PostTrain-Doctor 加新指纹，或改进 DiffVerifier 的输入生成。要求：定义写在代码注释里、报警线有依据、配"该报的报了 + 不该报的没报"两条测试。
4. 代码与文档修复。

## 红线（会被拒的 PR）

- 给启发式/关键词匹配披上"精确指标"的外衣。
- 往种子库塞未经核实的包名（错误的种子会把真实包拦下来，比漏拦更糟）。
- 引入运行时第三方依赖——本仓库目前零依赖是刻意的设计。

## 提交流程

1. Fork → 分支 → 改动 → 跑上面两条测试命令。
2. PR 描述写清：改了哪个工具、动机、测试怎么过的。
3. CI 绿了再等 review。CHANGELOG.md 里加一行你的变更。
