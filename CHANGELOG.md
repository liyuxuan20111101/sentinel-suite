# Changelog

> Repository name: **sentinel-suite** (发布名；早期开发文件夹为 ai-tool-suite，内容一致).

本仓库遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号用 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.4.0] - 2026-10-24

### Added
- 交互菜单：在真终端里不带参数运行 `sentinel.py`（或 Windows 双击 `sentinel.bat`）直接选工具，选中即用自带示例跑一遍并给出上手提示；管道/脚本环境下仍输出纯文本帮助。
- 命令糖：`diff 文件.py`（.bak 对比 + 自动用例一条命令）、`doctor 日志.jsonl`（免 analyze 子命令）、`slop scan`（缺省扫描当前目录）、`replay 轨迹` （免 replay 子命令）。
- `ops case-001` 只给案例时展示案情（incident.json）与上手提示。
- `--version`；macOS/Linux 一键 shim `./sentinel`；Windows 双击 `start_web.bat` 直接开 Web 控制台。
- tests/test_entry.py：入口冒烟测试（命令糖/帮助/自带案例解析/demo 全流程），并入 CI。

## [0.3.1] - 2026-10-24

### Added
- README 首页截图（Web 前端实际检出行为差异的界面）。

### Fixed
- Web 前端 DiffVerifier：相对路径文件在沙箱子进程里找不到——服务端现按工作目录解析为绝对路径（与 CLI 同一处问题）。

## [0.3.0] - 2026-10-23

### Added
- `sentinel.py` 统一入口：`diff / slop / replay / doctor / ops / web` 一个命令进所有工具；`sentinel.bat` 提供同样的 Windows 入口。
- `sentinel.py demo`：用自带示例依次跑通五个工具的一分钟演示。
- `examples/`：五个工具各自的可运行示例（含故意埋了行为差异、幻觉包名、轨迹分歧、reward hacking 指纹的样本）。
- OpsBench 便捷化：`sentinel.py ops --list` 列出自带案例；案例编号（如 `case-001`）自动解析到 `opsbench/cases/`；RCA 结论可直接传文本。

### Fixed
- DiffVerifier：`--old/--new/--path` 传相对路径时，子进程在临时目录里执行会找不到文件——入口现统一解析为绝对路径。

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
