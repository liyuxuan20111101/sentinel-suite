# 发布与维护手册（本文件不进仓库，发布后可留在本地或删除）

## 第一步：上传前 checklist

1. **改文件夹名**：现在叫「desktop-pet GitHub版本」，内容已与桌宠无关。建议改成
   `ai-tool-suite`（下面命令以此为准；改成别的名字就全局替换）。
2. **删除/保留本地件**：`docs/_README_TEMPLATE.md` 是给你看的写作指南——按它改完
   README 后把它删掉或移出仓库。
3. **跑一次全量测试**：`python tests/run_tests.py` + `python tests/test_web.py`，绿了再传。
4. **GitHub 账号**：没有就去 github.com 注册；本机 git 已装（git 2.55）。

## 第二步：建仓库并推送

浏览器：github.com → 右上 + → New repository →
名字 `ai-tool-suite`，Public，**不要**勾选任何初始化选项（README/license 都不要，
本地已有）→ Create。

然后本地（Git Bash）：

```bash
cd "C:/Users/andy/Desktop"
mv "desktop-pet GitHub版本" ai-tool-suite
cd ai-tool-suite
git init -b main
git add -A
git -c user.name="你的GitHub用户名" -c user.email="你的邮箱" commit -m "v0.2.0: five tools + web UI"
git remote add origin https://github.com/<你的用户名>/ai-tool-suite.git
git push -u origin main
```

首次 push 会弹 GitHub 登录：浏览器授权即可（HTTPS 方式不需要提前配 token；
如果走命令行登录，GitHub 已不再收密码，用 Settings → Developer settings →
Personal access tokens（classic）勾 `repo` 生成一个，密码位填 token）。

推送后到仓库页确认：README 渲染正常、Actions 里 CI 跑绿（约 1 分钟）。

## 第三步：发布 v0.2.0 Release

```bash
git tag -a v0.2.0 -m "五个工具 + Web 前端"
git push origin v0.2.0
```

GitHub 仓库页 → Releases → Draft a new release → 选 tag v0.2.0 →
标题 `v0.2.0`，正文把 CHANGELOG.md 的对应段落贴进去 → Publish。
Release 页是 CHANGELOG 的展示窗口，两者内容保持同步。

## 上传之后：发布动作（让有人看）

- **About 栏**：仓库页右上 ⚙ → description 填一句话（"五个没人做但都该存在的
  AI 验证/诊断工具：行为等价验证 / 包幻觉门禁 / 轨迹重放 / RL 诊断 / RCA 基准"），
  topics 加 `llm` `supply-chain-security` `reward-hacking` `agent` `benchmark`。
- **首发渠道**：V2EX（分享创造节点）、HN（Show HN）、Reddit r/LocalLLaMA 或
  r/MachineLearning、即刻/微博。文案用 README 的"行业缺什么 + 我补什么"，别贴功能清单。
- **种子库先行**：自己往 `hallucinated_seeds.txt` 核实并填入 3-5 个实测幻觉包名——
  空种子库发布观感差，有几行真数据就不一样了。
- **README 顶部补一张前端截图**（docs/_README_TEMPLATE.md 第 2 条）。

## 维护节奏（低成本可持续）

| 频率 | 做什么 |
|---|---|
| 有人提 Issue | 48 小时内回一句（哪怕只是"收到，下周看"）。回应速度比修复速度更决定项目口碑 |
| 有人提 PR | CI 绿 + 符合 CONTRIBUTING 红线就合；种子库 PR 核对 404 后快合 |
| 每月一次 | 跑全量测试确认 CI 没坏；看一眼 PyPI 参照集是否有失效包名 |
| 每次合并 | CHANGELOG.md 加一行；攒到一批就打下一个 tag（0.2.1 → 0.3.0） |
| 出现安全相关 bug | 修完直接 patch 版本 + Release，不攒 |

原则：**小步、真实、不画饼**。路线图上的项（语义评分、MCP 门禁、LLM 输入生成）
在被问起之前不必赶工——这个仓库的说服力来自"定义可审计"，不是功能数量。

## 何时拆仓库

如果某个工具（最可能是 DiffVerifier 或 SlopFirewall）单独火了、要接 CI 官方市场
（GitHub Marketplace），再把它拆成独立仓库——本仓库保留归档。单仓多工具在早期
维护成本最低。
