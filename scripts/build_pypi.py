#!/usr/bin/env python3
"""从仓库单一源拼装 sentinel_suite PyPI 包并构建 wheel/sdist。

布局（构建产物，不进 git）：
  build_pypi/
    pyproject.toml          ← 本脚本生成（版本号取自 sentinel.py 的 VERSION）
    sentinel_suite/
      __init__.py           ← 生成
      cli.py                ← sentinel.py，仅把 demo 子进程指向自身
      diffverifier.py / slopfirewall.py / hallucinated_seeds.txt
      replaykit.py / doctor.py / score.py
      opsbench/cases/**     ← 包数据
      web/server.py         ← 仅替换五个工具的 import 块为同包加载
      web/static/**

用法：python scripts/build_pypi.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _find_repo_root(start: Path) -> Path:
    p = start
    while p != p.anchor:
        if (p / "sentinel.py").is_file():
            return p
        p = p.parent
    raise SystemExit("找不到仓库根（没有 sentinel.py）")


REPO = _find_repo_root(HERE)
OUT = REPO / "build_pypi"
PKG = OUT / "sentinel_suite"


def _read(rel: str) -> str:
    return (REPO / rel).read_text("utf-8")


def _write(rel: str, text: str) -> None:
    target = PKG / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _must_replace(src: str, old: str, new: str, tag: str) -> str:
    if old not in src:
        raise SystemExit(f"补丁失败：源码里找不到[{tag}]锚点——仓库结构变了，请同步修改本脚本")
    return src.replace(old, new)


def assemble() -> str:
    if OUT.exists():
        shutil.rmtree(OUT)
    PKG.mkdir(parents=True)

    version = re.search(r'^VERSION = "([^"]+)"', _read("sentinel.py"), re.M).group(1)

    _write("__init__.py",
           f'"""sentinel-suite：五个验证/诊断 AI 生成产物的零依赖 CLI 工具。"""\n'
           f'__version__ = "{version}"\n')

    # cli.py：demo 的子进程改为直接调用包内 cli.py
    cli = _must_replace(
        _read("sentinel.py"),
        '[sys.executable, str(ROOT / "sentinel.py"), *argv]',
        '[sys.executable, str(Path(__file__).resolve()), *argv]',
        "demo 子进程入口")
    _write("cli.py", cli)

    for rel in ("diffverifier/diffverifier.py", "slopfirewall/slopfirewall.py",
                "slopfirewall/hallucinated_seeds.txt", "replaykit/replaykit.py",
                "posttrain-doctor/doctor.py", "opsbench/score.py"):
        _write(rel, _read(rel))

    shutil.copytree(REPO / "opsbench" / "cases", PKG / "opsbench" / "cases")
    shutil.copytree(REPO / "web" / "static", PKG / "web" / "static")

    # web/server.py：ROOT 语义不变（parents[1] 正好指向包根）；只换五个工具的 import 方式
    server = _read("web/server.py")
    server = _must_replace(
        server,
        'for d in ("diffverifier", "slopfirewall", "replaykit", "posttrain-doctor", "opsbench"):\n'
        '    sys.path.insert(0, str(ROOT / d))\n',
        "",
        "sys.path 注入块")
    server = _must_replace(
        server,
        'import diffverifier as dv            # noqa: E402\n'
        'import slopfirewall as sf            # noqa: E402\n'
        'import replaykit as rk               # noqa: E402\n'
        'import doctor as ptd                 # noqa: E402\n'
        'import score as ob                   # noqa: E402\n',
        'def _sibling(mod_name: str, file: str):\n'
        '    _spec = importlib.util.spec_from_file_location(\n'
        '        mod_name, str(Path(__file__).resolve().parent / file))\n'
        '    _mod = importlib.util.module_from_spec(_spec)\n'
        '    _spec.loader.exec_module(_mod)\n'
        '    return _mod\n'
        '\n'
        'dv = _sibling("sentinel_suite_dv", "../diffverifier/diffverifier.py")\n'
        'sf = _sibling("sentinel_suite_sf", "../slopfirewall/slopfirewall.py")\n'
        'rk = _sibling("sentinel_suite_rk", "../replaykit/replaykit.py")\n'
        'ptd = _sibling("sentinel_suite_ptd", "../posttrain-doctor/doctor.py")\n'
        'ob = _sibling("sentinel_suite_ob", "../opsbench/score.py")\n',
        "五个工具 import 块")
    server = _must_replace(
        server,
        "import argparse\nimport json\nimport sys",
        "import argparse\nimport importlib.util\nimport json\nimport sys",
        "importlib.util 导入")
    _write("web/server.py", server)

    _write_pyproject(version)
    return version


def _write_pyproject(version: str) -> None:
    (OUT / "pyproject.toml").write_text(f'''
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "sentinel-suite"
version = "{version}"
description = "Five zero-dependency CLI tools that gatekeep AI-generated work: patch behavior verification, package-hallucination firewall, agent trace replay, reward-hacking fingerprints, RCA benchmark."
readme = "README.md"
requires-python = ">=3.9"
license = {{text = "MIT"}}
keywords = ["ai-safety", "llm", "verification", "benchmark", "reward-hacking", "supply-chain"]
classifiers = [
  "Development Status :: 4 - Beta",
  "Environment :: Console",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.9",
  "Programming Language :: Python :: 3.13",
  "Topic :: Software Development :: Quality Assurance",
  "Topic :: Security",
]

[project.scripts]
sentinel-suite = "sentinel_suite.cli:main"

[project.urls]
Homepage = "https://github.com/liyuxuan20111101/sentinel-suite"
Changelog = "https://github.com/liyuxuan20111101/sentinel-suite/blob/main/CHANGELOG.md"

[tool.setuptools]
packages = ["sentinel_suite", "sentinel_suite.web"]

[tool.setuptools.package-data]
sentinel_suite = [
  "diffverifier/*.py",
  "slopfirewall/*.py",
  "slopfirewall/hallucinated_seeds.txt",
  "replaykit/*.py",
  "posttrain-doctor/*.py",
  "opsbench/*.py",
  "opsbench/cases/**/*",
]
"sentinel_suite.web" = ["static/*"]
'''.strip() + "\n", encoding="utf-8")


def main() -> int:
    version = assemble()
    shutil.copy(REPO / "README.md", OUT / "README.md")
    print(f"拼装完成 sentinel_suite v{version} → {OUT}")
    print("下一步构建：")
    print(f"  cd {OUT}")
    print("  python -m build --outdir dist")
    print("产物在 build_pypi/dist/（先 pip install build）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
