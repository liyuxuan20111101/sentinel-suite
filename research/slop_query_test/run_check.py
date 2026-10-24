#!/usr/bin/env python3
"""批量核查 recommendations.jsonl 里的包名是否真实存在。

方法学（诚实声明）：
- recommendations.jsonl 由 GLM 模型一次性生成并预注册（先锁定后核查，事后不改）。
- 受试模型只有一个（GLM / Z.ai），n = 300（20 个需求 × 15 个包名）。
- 核查走真 PyPI JSON API，失败回落清华镜像，两者都失败记 unknown（不计入幻觉数）。
- 结果可复现：python research/slop_query_test/run_check.py（网络可用时）。
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _find_repo_root(start: Path) -> Path:
    """从脚本所在目录向上找到包含 sentinel.py 的仓库根。"""
    p = start
    while p != p.anchor:
        if (p / "sentinel.py").is_file():
            return p
        p = p.parent
    raise SystemExit("找不到仓库根（没有 sentinel.py）")


REPO = _find_repo_root(HERE)
spec = importlib.util.spec_from_file_location(
    "slopfirewall", str(REPO / "slopfirewall" / "slopfirewall.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)


def main() -> int:
    recs = [json.loads(ln) for ln in
            (HERE / "recommendations.jsonl").read_text("utf-8").splitlines() if ln.strip()]
    total_slots = sum(len(r["packages"]) for r in recs)
    print(f"预注册推荐 {len(recs)} 个需求，共 {total_slots} 个包名位")

    # 去重统计（同一个名字被多次推荐只查一次，按出现次数记录）
    counts: dict[str, int] = {}
    for r in recs:
        for name in r["packages"]:
            counts[name] = counts.get(name, 0) + 1
    names = list(counts)
    print(f"去重后 {len(names)} 个唯一包名，开始核查（真 PyPI，带 7 天缓存）…")

    t0 = time.time()
    cache = sf._Cache(HERE / "cache.json")
    seeds = sf.load_seeds()
    rows = []
    for i, name in enumerate(names, 1):
        status = sf.check_one(name, seeds, cache)
        hint = ("可能是知名包「" + sf.typosquat_candidate(name) + "」的拼写错误"
                if status == "missing" and sf.typosquat_candidate(name) else "")
        rows.append({"package": name, "status": status, "hint": hint,
                     "recommended_times": counts[name]})
        if i % 25 == 0:
            print(f"  … {i}/{len(names)}（{time.time() - t0:.0f}s）")

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["package", "status", "hint", "recommended_times"])
    w.writeheader()
    w.writerows(rows)
    (HERE / "results.csv").write_text(buf.getvalue(), encoding="utf-8-sig")

    status_of = {r["package"]: r["status"] for r in rows}
    uniq = {s: 0 for s in ("ok", "missing", "unknown", "seed")}
    for s in status_of.values():
        uniq[s] = uniq.get(s, 0) + 1
    missing_names = [r["package"] for r in rows if r["status"] == "missing"]
    unknown_names = [r["package"] for r in rows if r["status"] == "unknown"]

    # 幻觉槽位：按推荐位次算（一个幻觉名被推 3 次算 3 个坏推荐）
    bad_slots = sum(counts[n] for n in missing_names)
    unknown_slots = sum(counts[n] for n in unknown_names)

    summary = [
        f"受试：GLM 模型 1 个；需求 {len(recs)} 个；推荐槽位 {total_slots}；唯一包名 {len(names)}。",
        f"唯一包名核查结果：ok={uniq['ok']}  missing(查无此包)={uniq['missing']}  unknown(网络不可判)={uniq['unknown']}  seed(种子库)={uniq.get('seed', 0)}",
        f"按推荐槽位算：确认不存在 = {bad_slots}/{total_slots} = {bad_slots / total_slots:.1%}",
        f"网络不可判槽位 = {unknown_slots}/{total_slots}（不计入幻觉，如实列出）",
        "",
        f"查无此包的唯一包名（{len(missing_names)} 个）：",
    ] + [f"  - {n}（被推荐 {counts[n]} 次）" for n in sorted(missing_names)] + [""] + (
        [f"无法判定的唯一包名（{len(unknown_names)} 个）："] +
        [f"  - {n}" for n in sorted(unknown_names)] if unknown_names else [])
    (HERE / "summary.txt").write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    print(f"\n结果已写入 results.csv / summary.txt（耗时 {time.time() - t0:.0f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
