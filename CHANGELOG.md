# Changelog

本仓库遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号用 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-10-01

### Added
- DiffVerifier：`--auto N` 签名感知自动用例（ast 解析，按参数名/注解生成边界值组合，覆盖全部模块级公开函数）。
- SlopFirewall：typosquat 检测（查无此包时与知名包参照集比对编辑距离 ≤2，提示拼写错误）；`scan <目录>` 递归扫描 requirements*.txt 与 pyproject.toml（[project] 与 poetry 段）。
- ReplayKit：`replay --repeat N` 不稳定步识别（重放间输出不一致的步单独归类，不误报为回归）；`compare a.jsonl b.jsonl` 双轨迹对比（首个分歧步：工具/参数/输出/长度）。
- PostTrain-Doctor：F5 奖励方差塌缩、F6 长度-奖励相关指纹；`--export` 高 reward 失败样本复查队列导出。
- OpsBench：case-002（数据库连接泄漏，干扰项=发布时间错位 + "回滚发布"禁现词）；评分前全角/大小写归一。
- Web 前端：DiffVerifier 自动用例开关、ReplayKit 重放次数输入。
- GitHub Actions CI（3.9/3.11/3.13 矩阵）、CONTRIBUTING.md、Issue 模板。

### Fixed
- DiffVerifier 自动用例列轮转缺陷（边界值凑不进同一用例）。
- SlopFirewall pyproject.toml 依赖解析不剥引号。

## [0.1.0] - 2026-10-01

### Added
- 五个工具的 v0：DiffVerifier（行为等价性验证 CLI）、SlopFirewall（包幻觉门禁 CLI + 种子库机制）、ReplayKit（JSONL 轨迹录制/重放/首个分歧定位）、PostTrain-Doctor（F1–F4 指纹分析器）、OpsBench（案例格式 + case-001 + 关键词评分器）。
- 本地 Web 前端（标准库 http.server + 单页仪表盘，只绑 127.0.0.1）。
- 测试套件 tests/run_tests.py。
