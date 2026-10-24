# PyPI 发布指南（维护者用）

`pip install sentinel-suite` 的发包流程。构建已全部本地验证过（wheel 装进干净
venv 后 `ops` / `web` / `demo` / `--version` 全部通过），你只需要做账号和上传两步。

## 一次性准备（只需做一次）

1. 注册 [pypi.org](https://pypi.org) 账号（建议同时注册 [test.pypi.org](https://test.pypi.org) 演练用）。
2. 账号设置里开 Two-factor，然后生成一个 **API token**（Account settings → API tokens，
   scope 先选 Entire account，之后可收紧到项目）。
3. 本机配置 token（只需一次；把 `pypi-` 开头的完整 token 填进去）：
   ```
   [pypi]
   username = __token__
   password = pypi-xxxxxxxx
   ```
   保存到 `~/.pypirc`（Windows 就是 `C:\Users\<你>\.pypirc`）。
   **不要**把 token 提交进 git。

## 每次发布

```bash
# 1) 版本号：确认 sentinel.py 里的 VERSION 已更新、CHANGELOG 有对应条目

# 2) 拼装 + 构建（产物在 build_pypi/dist/）
python scripts/build_pypi.py
cd build_pypi && python -m build --outdir dist

# 3) 上传（先演练后正式；twine 需 pip install twine）
python -m twine upload --repository testpypi dist/*   # 演练
python -m twine upload dist/*                          # 正式

# 4) 验证
pip index versions sentinel-suite        # 或网页看 pypi.org/project/sentinel-suite
pip install sentinel-suite && sentinel-suite --version
```

## 注意

- **名字先占**：`sentinel-suite` 这个包名如被占用，看 `build_pypi/pyproject.toml` 里的
  name 改成 `sentinel-suite-tools` 之类，同步改 [project.scripts] 的命令名。
- PyPI 同版本号**不可重传**：上传失败重试前必须升版本号（哪怕是 0.4.0 → 0.4.0a1）。
- 每次发版记得同时打 git tag、发 GitHub Release（流程见 docs/_PUBLISH_GUIDE 的历史
  版本或 CHANGELOG 里的惯例）。
- 首次正式上传后，给项目配 Trusted Publisher（PyPI 项目设置 → Publishing），
  以后可以从 GitHub Actions 自动发包，token 都不用存。
