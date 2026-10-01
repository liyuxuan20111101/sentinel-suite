# DiffVerifier — AI 补丁的行为等价性验证器

不审风格，只回答一个问题：**这个改动在原有输入空间里会不会改变行为。**

**立身之本**：[SWE-Proof](https://arxiv.org/abs/2509.24162) 证明约 25% 的"测试通过"补丁仍可构造出反例。所有人都在做"生成 review 意见"，没人做"证明行为没变"。

## 这是什么

一个零依赖的单文件 CLI。给定一个改动的**旧实现**与**新实现**，以及若干个来自原有输入空间的输入，它在两边各跑一遍并对比输出：

- 输出一致 → 这次改动在抽查的输入上行为未变（等价性 witnesses）；
- 输出不同 → 拿到一个**反例**：具体输入 + 旧行为 + 新行为；
- 一边抛异常一边不抛，也算行为差异。

退出码可机读：`0` 一致 / `1` 发现差异 / `2` 出错——可直接挂进 CI 或 pre-commit。

## 用法

```bash
# 改动前后（old 缺省取 <file>.bak，适配各类 edit 工具的自动备份）
python diffverifier/diffverifier.py --path src/calc.py --calls "calc(2, 3)|calc(0, 0)|greet('hi')"

# 显式给新旧两个文件
python diffverifier/diffverifier.py --old old.py --new new.py --calls "calc(2, 3)"

# 用例走 JSON（适合程序化生成输入；从 stdin 读）
echo '[["calc", [2, 3]], ["greet", ["hi"]]]' | python diffverifier/diffverifier.py --old a.py --new b.py --calls-json -
```

输出示例：

```
diffverifier —— 旧 vs 新，同一输入：
1. calc[2, 3]：行为不同！旧=5 ≠ 新=6
2. calc[0, 0]：一致 → 0
结论：2 个用例里 1 个行为不同。
这些差异若不是这次改动的目的，改动有问题。
```

## 自动用例（v0.1）

懒得想输入？`--auto N` 按函数签名生成典型边界输入（0/空串/负数/超长/中文……），
覆盖模块全部公开函数，跳过 `_` 私有函数：

```bash
python diffverifier/diffverifier.py --path src/calc.py --auto
python diffverifier/diffverifier.py --path src/calc.py --auto 5   # 每函数 5 组
```

启发式、非穷尽：它猜不出你的业务语义，但最容易出行为差异的输入形状（零、空、负、极值）
会先被扫一遍。前端同样有此开关。

## 设计边界（如实告知）

- 只能对比你给的两个版本；适配"上一次改动"时依赖 `.bak` 备份。
- 最适合**纯函数 / 自包含模块**。模块级副作用（连网、写文件）两边都会发生。
- 参数只接受 `ast.literal_eval` 字面量（数字/字符串/元组/列表），不是 `eval`，没有代码注入面；被对比的代码本身是你仓库里的代码，请像对待 `pytest` 一样对待它。
- 新旧实现"同长度、同秒改写"时，`__pycache__` 的 mtime+size 校验会误判缓存有效 → 本工具用手动 `compile` 彻底绕开字节码缓存（实测踩过的坑）。
- v0 的输入来自人（或你接的 LLM）。输入生成自动化是路线图的下一站。

## 手工 ground truth

同仓库的手工版 benchmark（12 个真实 AI 生成 PR 的反例构造）见：
[diffverifier-benchmark](../../../../benchmark/diffverifier-benchmark)（随本仓库一起发布的独立目录/仓库）。

## 路线图

1. 输入生成自动化：LLM 提议输入 + 差分执行闭环
2. 函数级 diff 定位（只跑改动的调用闭包）
3. CI 集成：PR 上自动对比 `git diff` 前后行为
