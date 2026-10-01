# SlopFirewall — 包幻觉 / MCP 供应链门禁

## 🇬🇧 English

**SlopFirewall** verifies that a package name actually exists on PyPI *before* it lands in a `pip install`. Package-hallucination rates reach 19.7% and are stable across runs (see ["We Have a Package for You!"](https://arxiv.org/abs/2503.23008)); unregistered hallucinated names are ready-made typosquat poisoning slots, and neither IDEs nor CI check them.

**What it does**: verdicts per name — ✅ exists / ❌ missing (likely hallucination, don't install) / ⛔ seed-list hit (known-bad, blocked offline) / ❓ network down → *unverifiable, honestly reported, never guessed*. Typosquat detection suggests the real package when a candidate is within edit distance 2 of a well-known one. `scan` parses requirements files, pip-install snippets, or walks whole project directories. Zero dependencies, Python 3.9+.

```bash
python slopfirewall/slopfirewall.py check requests facny-colorlog
python slopfirewall/slopfirewall.py scan requirements.txt
python slopfirewall/slopfirewall.py scan /path/to/project
```

> 中文说明在下方 ↓

---
**包幻觉率 19.7%，43% 稳定复现**（详见 ["We Have a Package for You!"](https://arxiv.org/abs/2503.23008) 一类研究），多模型共享的幻觉包名里有一批尚未被注册——这是现成的投毒位。而 IDE 与 CI 完全不设防。

SlopFirewall 在包名落进 `pip install` 之前核一遍。零第三方依赖，Python 3.9+。

## 用法

```bash
# 核查包名
python slopfirewall/slopfirewall.py check requests facny-colorlog

# 扫描 requirements.txt / 脚本 / CI 配置里的 pip install 目标
python slopfirewall/slopfirewall.py scan requirements.txt
git diff | python slopfirewall/slopfirewall.py scan -      # CI 里只查新增内容

# 带种子库（命中直接拦，不发网络请求）
python slopfirewall/slopfirewall.py check --seed my_seeds.txt pkg-a pkg-b
```

## 判定与退出码

| 标记 | 含义 | 退出码贡献 |
|---|---|---|
| ✅ | PyPI 存在 | 0 |
| ❌ | PyPI 查无此包 → 疑似包幻觉 | 1 |
| ⛔ | 命中种子库（已知幻觉包名） | 1 |
| ❓ | 两路核实都失败 → **无法确认，不猜** | 2 |

核实顺序：PyPI JSON API → 清华镜像 simple 索引（DNS 不佳的环境反而更稳）。结果缓存 7 天（`--no-cache` 关闭）。

## 关于种子库

研究提到多模型共享的 53 个幻觉包名尚未被注册——但我们**刻意不预填**未经自己核实的名单：错误的种子会把真实包拦下来，比漏拦更毁信任。`hallucinated_seeds.txt` 是机制：把你实测收集到的幻觉包名追加进去（欢迎 PR），命中即拦、离线可判。

## typosquat 检测（v0.1）

查无此包的候选名若与某个知名包编辑距离 ≤2，报告会直接指出"可能是 `requests` 的拼写错误"
——拼错真包名装到的就是抢注包。参照集内置于 `POPULAR_PACKAGES`（纯包名列表，可审可扩）。

## 项目扫描（v0.1）

```bash
python slopfirewall/slopfirewall.py scan /path/to/project
```

递归扫描 `requirements*.txt` 与 `pyproject.toml`（含 `[project] dependencies` 与
`[tool.poetry.dependencies]` 段，python 自身排除），自动跳过 `.venv/node_modules/.git` 等。
CI 一行接入：对 PR diff 的依赖清单跑 `scan -`，退出码非零即拦。

## MCP 供应链（路线图）

包幻觉是供应链投毒的入口之一；MCP 工具目录是另一个同类入口（工具名幻觉 / 恶意 server 描述注入）。v0 先守住 pip 这条最粗的血管，MCP 注册表核验在路线图上：

1. MCP server 清单校验（名称/来源/签名）
2. CI Action：PR diff 里新增的依赖逐个过门禁
3. IDE 插件：编辑器内 inline 警告
