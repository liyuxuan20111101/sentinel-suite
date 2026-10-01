#!/usr/bin/env python3
"""AI Tool Suite 本地前端：标准库 HTTP 服务 + 单页仪表盘。

- 只绑定 127.0.0.1（工具会在本机读文件/执行被测代码，不要暴露到局域网）
- 零第三方依赖：http.server + 工具模块直接 import
- 启动：python web/server.py  [--port 8642] [--no-browser]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for d in ("diffverifier", "slopfirewall", "replaykit", "posttrain-doctor", "opsbench"):
    sys.path.insert(0, str(ROOT / d))

import diffverifier as dv            # noqa: E402
import slopfirewall as sf            # noqa: E402
import replaykit as rk               # noqa: E402
import doctor as ptd                 # noqa: E402
import score as ob                   # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8642


def _err(msg: str, code: int = dv.EXIT_ERROR) -> dict:
    return {"report": msg, "code": code}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def _send(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, p: Path, ctype: str) -> None:
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    # ---------- GET ----------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
        elif self.path == "/app.js":
            self._send_file(STATIC / "app.js", "text/javascript; charset=utf-8")
        elif self.path == "/style.css":
            self._send_file(STATIC / "style.css", "text/css; charset=utf-8")
        elif self.path == "/api/opsbench/cases":
            base = ROOT / "opsbench" / "cases"
            cases = []
            if base.exists():
                for d in sorted(base.iterdir()):
                    if d.is_dir() and (d / "ground_truth.json").exists():
                        cases.append(d.name)
            self._send({"cases": cases})
        elif self.path.startswith("/api/opsbench/example/"):
            case_id = self.path.rsplit("/", 1)[-1]
            f = ROOT / "opsbench" / "cases" / case_id / "answer.example.md"
            if case_id in ("", ".", "..") or not f.exists():
                return self._send({"error": "案例没有示例答案"}, 404)
            self._send({"answer": f.read_text("utf-8")})
        elif self.path == "/api/ping":
            self._send({"ok": True, "root": str(ROOT)})
        else:
            self._send({"error": "not found"}, 404)

    # ---------- POST ----------
    def do_POST(self):
        try:
            body = self._body()
        except ValueError:
            return self._send({"report": "请求体不是合法 JSON", "code": 2})
        try:
            if self.path == "/api/diffverifier":
                return self._send(self.api_diff(body))
            if self.path == "/api/slopfirewall":
                return self._send(self.api_slop(body))
            if self.path == "/api/replaykit":
                return self._send(self.api_replay(body))
            if self.path == "/api/posttrain":
                return self._send(self.api_posttrain(body))
            if self.path == "/api/opsbench":
                return self._send(self.api_opsbench(body))
            return self._send({"report": "未知接口", "code": 2})
        except Exception as exc:  # 工具内部异常 → 报告给前端，不打死服务
            return self._send({"report": f"服务端异常：{exc.__class__.__name__}: {exc}",
                               "code": 2})

    # ---------- 各工具 ----------
    def api_diff(self, b: dict) -> dict:
        try:
            if b.get("auto"):
                src_file = Path(b.get("new") or b.get("path") or "")
                if not src_file.exists():
                    return _err("自动用例需要能读到的目标文件（.bak 模式或显式 new）")
                calls = dv.auto_calls(src_file.read_text("utf-8"),
                                      per_fn=max(1, int(b.get("per_fn") or 3)))
            else:
                calls = dv.parse_calls((b.get("calls") or "").strip())
        except ValueError as exc:
            return _err(f"用例格式：{exc}")
        try:
            if b.get("old") and b.get("new"):
                old_p, new_p = Path(b["old"]), Path(b["new"])
            elif b.get("path"):
                new_p = Path(b["path"])
                old_p = new_p.with_suffix(new_p.suffix + ".bak")
                if not old_p.exists():
                    return _err(f"没有找到改动前备份 {old_p.name}（可用「显式新旧」模式给两个文件）")
            else:
                return _err("需要文件路径（.bak 模式）或显式的新旧两个文件")
        except OSError as exc:
            return _err(f"路径无效：{exc}")
        if not new_p.exists() or not old_p.exists():
            return _err(f"文件不存在（old={old_p} new={new_p}）")
        report, code = dv.run_diff(old_p, new_p, calls,
                                   timeout=float(b.get("timeout") or dv.TIMEOUT_S))
        return {"report": report, "code": code,
                "old": str(old_p), "new": str(new_p)}

    def api_slop(self, b: dict) -> dict:
        text = (b.get("text") or "").strip()
        if not text:
            return _err("粘贴包名列表 / requirements.txt / 含 pip install 的文本")
        names = sf.extract_package_names(text) if (
            sf._INSTALL_RE.search(text) or "\n" in text or "," in text
        ) else [x for x in text.split() if sf._NAME_RE.fullmatch(x)]
        if not names:
            return _err("没有解析到包名")
        seeds = sf.load_seeds() if b.get("use_seeds", True) else set()
        cache = None if b.get("no_cache") else sf._Cache(None)  # 前端默认不落盘，进程内缓存
        report, code = sf.check_packages(names, seeds, cache)
        return {"report": report, "code": code}

    def api_replay(self, b: dict) -> dict:
        trace = (b.get("trace_path") or "").strip()
        if not trace or not Path(trace).exists():
            return _err("轨迹文件不存在（先在 agent 里用 Recorder 生成 JSONL）")
        tools_path = (b.get("tools_path") or "").strip()
        if not tools_path:
            entries = rk.read_trace(trace)
            if not entries:
                return _err("轨迹为空或全部坏行")
            dist: dict[str, int] = {}
            for e in entries:
                dist[e["tool"]] = dist.get(e["tool"], 0) + 1
            return {"report": f"replaykit：{len(entries)} 步；工具分布："
                    + "、".join(f"{t}×{c}" for t, c in dist.items())
                    + "\n（填上工具实现 .py 的路径即可重放对比）", "code": 0}
        try:
            tools = rk.load_tools(tools_path)
        except Exception as exc:
            return _err(f"加载工具失败：{exc}")
        report = rk.replay(trace, tools, stop_on_first=not b.get("all"),
                           repeat=max(1, int(b.get("repeat") or 1)))
        return {"report": rk.format_report(report),
                "code": rk.EXIT_DIFF if report["first_divergence"] else rk.EXIT_SAME}

    def api_posttrain(self, b: dict) -> dict:
        text = (b.get("text") or "").strip()
        if not text:
            return _err("粘贴 episode JSONL（每行一条，含 reward 字段）")
        f = Path(tempfile.mkdtemp(prefix="ptd-web-")) / "episodes.jsonl"
        f.write_text(text + "\n", encoding="utf-8")
        episodes, bad = ptd.read_episodes(f)
        if not episodes:
            return _err("没有有效 episode（每行需为 JSON 且含 reward 字段）")
        findings = ptd.analyze(episodes, r_threshold=float(b.get("threshold") or ptd.DEFAULT_R_THRESHOLD))
        if b.get("quiet"):
            findings = [x for x in findings if x["alarm"]]
        report = ptd.format_report(episodes, bad, findings)
        code = ptd.EXIT_FINGERPRINT if any(x["alarm"] for x in findings) else ptd.EXIT_CLEAN
        return {"report": report, "code": code}

    def api_opsbench(self, b: dict) -> dict:
        case_id = (b.get("case") or "").strip()
        answer = (b.get("answer") or "").strip()
        if not case_id or "/" in case_id or "\\" in case_id or ".." in case_id:
            return _err("选择一个案例")
        case_dir = ROOT / "opsbench" / "cases" / case_id
        if not (case_dir / "ground_truth.json").exists():
            return _err(f"案例不存在：{case_id}")
        if not answer:
            return _err("粘贴被测 agent 的 RCA 结论")
        f = Path(tempfile.mkdtemp(prefix="opsbench-web-")) / "answer.md"
        f.write_text(answer, encoding="utf-8")
        report, code = ob.score_case(case_dir, f)
        return {"report": report, "code": code}


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Tool Suite 本地前端")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}"
    print(f"AI Tool Suite 前端：{url}（Ctrl+C 退出）")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
