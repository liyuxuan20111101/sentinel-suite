#!/usr/bin/env python3
"""SlopFirewall — 包幻觉 / MCP 供应链门禁。

AI 会自信地生成**不存在的包名**；攻击者抢注这些名字后就是现成的投毒位。
研究报道包幻觉率约 19.7%，且 43% 稳定复现——而 IDE 与 CI 完全不设防。
本工具在包名落进 `pip install` 之前核一遍：

  python slopfirewall/slopfirewall.py check requests facny-colorlog
  python slopfirewall/slopfirewall.py scan requirements.txt      # 或任意含 pip install 的文件
  python slopfirewall/slopfirewall.py check --seed seeds.txt pkg-a pkg-b

判定：
  ✅ PyPI 存在（200）
  ❌ 查无此包（404）→ 疑似包幻觉，别装
  ⛔ 命中种子库（已知幻觉包名）→ 直接拦，不发网络请求
  ❓ 两路核实都失败 → "无法确认"，如实标注，不猜（装前人工查）

核实顺序：PyPI JSON API → 清华镜像 simple 索引（DNS 不佳的环境反而更稳）。
结果缓存（默认 7 天）写 ~/.cache/slopfirewall/cache.json；--no-cache 关闭。
退出码：0=全部存在；1=发现疑似幻觉；2=有无法确认项；3=用法错误。
零第三方依赖（urllib），Python 3.9+。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

CACHE_TTL_S = 7 * 24 * 3600
HTTP_TIMEOUT_S = 6.0
UA = "slopfirewall/0.1 (+supply-chain hygiene)"

EXIT_OK, EXIT_HALLUCINATION, EXIT_UNKNOWN, EXIT_USAGE = 0, 1, 2, 3

# 种子库：已知会被模型幻觉出来的包名（一行一个，# 注释）。
# 这是**机制演示**——把你在自己的生成流量里实测收集到的幻觉包名追加进来，
# 命中种子库的包直接拦，省掉网络核实。
SEED_FILE = Path(__file__).with_name("hallucinated_seeds.txt")

_INSTALL_RE = re.compile(
    r"(?:\bpip3?\b|\bpython3?\s+-m\s+pip\b)\s+install\s+([^\n#;|]+)", flags=re.I)
_VALUE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url",
                "--extra-index-url", "-f", "--find-links", "-t", "--target",
                "--src", "--prefix", "--platform", "--root", "-b", "--build",
                "--config-settings"}
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _normalize(name: str) -> str:
    """PEP 503 规范化，做缓存/种子键。"""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


# 高频真实包名（typosquat 检测的参照集；全部为长期存在的知名包）。
# 用途：候选包名在 PyPI 查无此包时，若与其中某个名字编辑距离 ≤2，
# 大概率是"把真包名拼错了"——按错名装到的就是抢注包。
POPULAR_PACKAGES = frozenset("""
requests urllib3 certifi setuptools pip wheel numpy pandas matplotlib scipy
django flask fastapi uvicorn pydantic httpx aiohttp starlette pytest black mypy
pylint boto3 tensorflow torch torchvision torchaudio transformers scikit-learn
opencv-python pillow sqlalchemy celery redis click rich tqdm pyyaml
beautifulsoup4 lxml openai anthropic google-auth cryptography paramiko psutil
gunicorn uv six python-dateutil pytz jinja2 markupsafe werkzeug typing-extensions
packaging attrs orjson ujson sqlmodel alembic pymongo elasticsearch grpcio
protobuf conda virtualenv tox coverage hypothesis faker seaborn plotly bokeh
notebook jupyterlab ipython xgboost lightgbm nltk spacy python-dotenv
playwright selenium dash streamlit gradio apscheduler schedule
""".split())


def _levenshtein(a: str, b: str, cap: int = 2) -> int:
    """编辑距离（早退：超过 cap 返回 cap+1）。"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def typosquat_candidate(name: str) -> str | None:
    """找与 name（PEP503 归一后）编辑距离 ≤2 的知名包名。返回建议名或 None。"""
    key = _normalize(name)
    best, best_d = None, 3
    for pop in POPULAR_PACKAGES:
        d = _levenshtein(key, _normalize(pop), cap=2)
        if d < best_d and d >= 1:  # d==0 说明同名（在 POPULAR 里），不算 typo
            best, best_d = pop, d
    return best


def load_seeds(path: Path | None = None) -> set[str]:
    """读种子库（# 注释、空行跳过），返回规范化包名集合。"""
    p = path or SEED_FILE
    if not p.exists():
        return set()
    out = set()
    for ln in p.read_text("utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln and _NAME_RE.fullmatch(ln):
            out.add(_normalize(ln))
    return out


def parse_install_targets(text: str) -> list[str]:
    """解析文本里的 pip install 目标包名（剥版本/extras，剔 flag、URL、本地路径）。"""
    names: list[str] = []
    for m in _INSTALL_RE.finditer(text or ""):
        skip_next = False
        for tok in m.group(1).split():
            if skip_next:
                skip_next = False
                continue
            t = tok.strip().strip("\"'")
            if not t:
                continue
            if t.startswith("-"):
                if t.lower() in _VALUE_FLAGS:
                    skip_next = True
                continue
            if "://" in t or t.endswith(("/", "\\")) or t.startswith(".") or ":" in t:
                continue
            name = re.split(r"[=<>!~;\s\[]", t, maxsplit=1)[0]
            if _NAME_RE.fullmatch(name) and name not in names:
                names.append(name)
    return names


class _Cache:
    def __init__(self, path: Path | None, ttl: float = CACHE_TTL_S) -> None:
        self.path = path
        self.ttl = ttl
        self.data: dict[str, tuple[str, float]] = {}
        if path and path.exists():
            try:
                self.data = {k: tuple(v) for k, v in
                             json.loads(path.read_text("utf-8")).items()}
            except Exception:
                self.data = {}

    def get(self, key: str) -> str | None:
        hit = self.data.get(key)
        if hit and time.time() - hit[1] < self.ttl:
            return hit[0]
        return None

    def put(self, key: str, verdict: str) -> None:
        if not self.path:
            return
        self.data[key] = (verdict, time.time())
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({k: list(v) for k, v in self.data.items()}), encoding="utf-8")
        except OSError:
            pass


def _http_status(url: str) -> int | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def check_one(name: str, seeds: set[str], cache: _Cache | None) -> str:
    """核单个包名 → "seed" | "ok" | "missing" | "unknown"。"""
    key = _normalize(name)
    if key in seeds:
        return "seed"
    if cache:
        hit = cache.get(key)
        if hit:
            return hit
    verdict = "unknown"
    for url in (f"https://pypi.org/pypi/{key}/json",
                f"https://pypi.tuna.tsinghua.edu.cn/simple/{key}/"):
        st = _http_status(url)
        if st == 200:
            verdict = "ok"
            break
        if st == 404:
            verdict = "missing"
            break
    if verdict in ("ok", "missing") and cache:
        cache.put(key, verdict)
    return verdict


def parse_requirements(text: str) -> list[str]:
    """解析 requirements.txt 格式：非注释/非空/非 flag 的行都视为包名（剥引号）。"""
    names: list[str] = []
    for ln in (text or "").splitlines():
        ln = ln.split("#", 1)[0].strip().strip("\"' ")
        if not ln or ln.startswith("-") or "://" in ln or ln.startswith("."):
            continue
        name = re.split(r"[=<>!~;\s\[]", ln, maxsplit=1)[0]
        if _NAME_RE.fullmatch(name) and name not in names:
            names.append(name)
    return names


def extract_package_names(text: str) -> list[str]:
    """任意文本 → 包名：优先找 pip install 语句，找不到则按 requirements 格式解析。"""
    targets = parse_install_targets(text)
    return targets if targets else parse_requirements(text)


def check_packages(names: list[str], seeds: set[str] | None = None,
                   cache: _Cache | None = None) -> tuple[str, int]:
    """核查包名列表，返回 (报告, 退出码)。"""
    if not names:
        return "slopfirewall：没有解析到包名", EXIT_USAGE
    seeds = seeds or set()
    lines, n_ok, n_bad, n_unknown = [], 0, 0, 0
    for n in names[:16]:
        v = check_one(n, seeds, cache)
        if v == "seed":
            n_bad += 1
            lines.append(f"⛔ {n} — 命中已知幻觉包名种子库，禁止安装")
        elif v == "ok":
            n_ok += 1
            lines.append(f"✅ {n} — PyPI 存在")
        elif v == "missing":
            n_bad += 1
            typo = typosquat_candidate(n)
            hint = (f"——可能是知名包「{typo}」的拼写错误（typosquat 风险），请核对拼写"
                    if typo else "很可能是包幻觉，不要安装（这类名字常被攻击者抢注）")
            lines.append(f"❌ {n} — PyPI 查无此包：{hint}")
        else:
            n_unknown += 1
            lines.append(f"❓ {n} — 网络核实失败，无法确认。装前人工查："
                         f"https://pypi.org/project/{n}")
    code = EXIT_HALLUCINATION if n_bad else (EXIT_UNKNOWN if n_unknown else EXIT_OK)
    tail = (f"\n⚠ {n_bad} 个疑似幻觉包名——别装，先确认正确包名。" if n_bad
            else f"\n⚠ {n_unknown} 个未能核实——网络恢复后重查或人工确认。" if n_unknown
            else f"\n全部 {n_ok} 个确认存在。")
    return "slopfirewall 核查结果：\n" + "\n".join(lines) + tail, code


def scan_project(root: Path) -> tuple[list[str], list[str]]:
    """扫一个项目目录：requirements*.txt、pyproject.toml（dependencies/poetry）。

    返回 (去重包名, 已扫描的文件相对路径列表)。
    """
    names: list[str] = []
    scanned: list[str] = []
    skip = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist", "build"}
    for p in sorted(root.rglob("*")):
        if any(part in skip for part in p.parts):
            continue
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        try:
            if p.name.startswith("requirements") and p.suffix == ".txt":
                text = p.read_text("utf-8", errors="replace")
                found = parse_requirements(text) + parse_install_targets(text)
            elif p.name == "pyproject.toml":
                text = p.read_text("utf-8", errors="replace")
                found = []
                # [project] dependencies = [ "pkg>=1", ... ]
                for m in re.finditer(r'dependencies\s*=\s*\[(.*?)\]', text, re.S):
                    found += parse_requirements(m.group(1).replace(",", "\n"))
                # [tool.poetry.dependencies] 段下的 name = "^ver"
                sec = re.search(r"\[tool\.poetry\.dependencies\](.*?)(?:\n\[|\Z)", text, re.S)
                if sec:
                    for ln in sec.group(1).splitlines():
                        m = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*=", ln.strip())
                        if m and m.group(1).lower() != "python":
                            found.append(m.group(1))
            else:
                continue
        except OSError:
            continue
        scanned.append(rel)
        for n in found:
            if n not in names:
                names.append(n)
    return names, scanned


def main() -> int:
    ap = argparse.ArgumentParser(description="包幻觉 / MCP 供应链门禁")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="核查包名（空格分隔，或一段含 pip install 的文本）")
    p_check.add_argument("names", nargs="+")
    p_check.add_argument("--seed", help="种子库文件（缺省用内置 hallucinated_seeds.txt）")
    p_check.add_argument("--cache", help="缓存文件路径（缺省 ~/.cache/slopfirewall/cache.json）")
    p_check.add_argument("--no-cache", action="store_true")

    p_scan = sub.add_parser("scan", help="扫描文件或目录（requirements*/pyproject.toml）并核查")
    p_scan.add_argument("file", nargs="?", default=".", help="文件 / 目录 / -（stdin）；缺省扫描当前目录")
    p_scan.add_argument("--seed")
    p_scan.add_argument("--cache")
    p_scan.add_argument("--no-cache", action="store_true")

    a = ap.parse_args()
    seeds = load_seeds(Path(a.seed) if getattr(a, "seed", None) else None)

    scanned_note = ""
    if a.cmd == "check":
        raw = " ".join(a.names)
        if _INSTALL_RE.search(raw) or "\n" in raw:
            names = parse_install_targets(raw)
        else:
            names = [x for x in raw.split() if _NAME_RE.fullmatch(x)]
    else:
        if a.file == "-":
            names = extract_package_names(sys.stdin.read())
        elif Path(a.file).is_dir():
            names, files = scan_project(Path(a.file))
            scanned_note = f"（扫描 {len(files)} 个清单文件：{'、'.join(files[:6])}{'…' if len(files) > 6 else ''}）"
        else:
            names = extract_package_names(Path(a.file).read_text("utf-8"))
    if not names:
        print("slopfirewall：没有解析到包名" + scanned_note)
        return EXIT_USAGE

    cache = None
    if not a.no_cache:
        cp = Path(a.cache) if getattr(a, "cache", None) else (
            Path.home() / ".cache" / "slopfirewall" / "cache.json")
        cache = _Cache(cp)
    report, code = check_packages(names, seeds, cache)
    print((scanned_note + "\n" if scanned_note else "") + report)
    return code


if __name__ == "__main__":
    sys.exit(main())
