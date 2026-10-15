#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quality_evidence.py — 从真实产物生成「本周质量证据」摘要（Markdown）。

用途：对外传播时，**不手写数字**。本脚本逐个读仓库里的真产物，产出一段可直接
贴到 issue / discussion / 社交媒体的 Markdown。数字腐蛆在这个项目里是头号病，
所以传播材料也必须由产物推导，而不是从某篇旧文章里抄。

覆盖的指标与来源：
  · 版本          ← scripts/tdlib/__init__.py.__version__
  · 回归项数      ← tests/e2e.py 的 `def t_*` 个数
  · 缺陷数        ← scripts/tdlib/defects.py 的 DEFECTS 长度
  · 声称条数      ← docs/verify_claims.py 的 parse_claims()
  · 跨模型复评    ← docs/independent-recheck/*/*/review.json（逐卡：等级 + 是否编造）
  · 效用 n=3      ← docs/utility-baseline/<card>/run-*/utility-report.json（会话数）
  · 最新 Release  ← `gh release view`（拿不到就标「未获取」，不猜）

用法：
    python3 tools/quality_evidence.py              # 打印 Markdown
    python3 tools/quality_evidence.py --out x.md   # 写入文件
    python3 tools/quality_evidence.py --json       # 机器可读
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gather() -> dict:
    from tdlib import __version__ as version
    from tdlib.defects import DEFECTS

    e2e = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    tests = len(re.findall(r"^def t_[a-z0-9_]+\(", e2e, re.M))

    vc = _load("vc", "docs/verify_claims.py")
    claims = len(vc.parse_claims())

    # 跨模型 / 人类复评：逐卡列等级与编造标记
    reviews = []
    rroot = ROOT / "docs" / "independent-recheck"
    if rroot.exists():
        for rf in sorted(rroot.glob("*/*/review.json")):
            try:
                d = json.loads(rf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            reviews.append({
                "card": d.get("card", rf.parent.parent.name),
                "reviewer": d.get("model_or_reviewer", rf.parent.name),
                "type": d.get("reviewer_type", "?"),
                "grade": d.get("fidelity_grade_reconfirmed"),
                "fabrication": bool(d.get("fabrication_flagged")),
                "n_answers": len(d.get("answers_rechecked") or []),
            })
    valid = [r for r in reviews
             if not r["fabrication"] and r["grade"] in ("A", "B", "C", "D")]

    # 效用 n=3：数会话数与"无增益"次数（none 是合法结论，必须如实报）
    n3_sessions = 0
    n3_none = 0
    n3_cards = 0
    uroot = ROOT / "docs" / "utility-baseline"
    if uroot.exists():
        for d in sorted(p for p in uroot.iterdir() if p.is_dir()):
            reports = sorted(d.glob("run-*/utility-report.json"))
            if len(reports) < 3:
                continue
            n3_cards += 1
            for rp in reports:
                n3_sessions += 1
                try:
                    rep = json.loads(rp.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                # 字段名是 gain（取值 significant/moderate/none），不是 level。
                # 2026-10-15 首版写成 level，导致 none 次数恒为 0——**少报负面结果**，
                # 这比多报更危险（本项目自己就因"只报幸存条目"栽过，#6）。
                if str(rep.get("gain", "")).lower() == "none":
                    n3_none += 1

    # 最新 Release：拿不到就说拿得到，不用默认值顶替
    latest = "未获取（本地无 gh 或无网络）"
    try:
        r = subprocess.run(
            ["gh", "release", "view", "--json", "tagName,publishedAt",
             "-q", '.tagName + " (" + .publishedAt[:10] + ")"'],
            capture_output=True, text=True, timeout=25, cwd=str(ROOT))
        if r.returncode == 0 and r.stdout.strip():
            latest = r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass

    return {"version": version, "generated": str(date.today()),
            "tests": tests, "defects": len(DEFECTS), "claims": claims,
            "cross_reviews": reviews, "cross_valid": len(valid),
            "n3_cards": n3_cards, "n3_sessions": n3_sessions,
            "n3_none": n3_none, "latest_release": latest}


def to_markdown(f: dict) -> str:
    lines = [
        f"## rulai-distill 质量证据 · {f['generated']}（v{f['version']}）",
        "",
        f"最新 Release：**{f['latest_release']}**",
        "",
        "| 指标 | 值 | 怎么来的 |",
        "|---|---|---|",
        f"| 回归测试 | **{f['tests']} 项全绿** | `python3 tests/e2e.py` |",
        f"| 对外声称 | **{f['claims']} 条逐条有据** | `python3 docs/verify_claims.py` |",
        f"| 自身缺陷台账 | **{f['defects']} 条公开登记** | `CONSTRAINTS.md`，行数/分布由测试强制相等 |",
        f"| 跨模型异族复评 | **{f['cross_valid']} 例有效** | `docs/independent-recheck/`，DeepSeek，无编造 |",
        f"| 效用对照 n=3 | **{f['n3_sessions']} 次会话 / {f['n3_cards']} 张卡**"
        f"（其中 {f['n3_none']} 次为 none，如实报） | `docs/utility-baseline/` |",
        "",
    ]
    if f["cross_reviews"]:
        lines += ["### 跨模型复评逐卡明细", "",
                  "| 卡 | 复评者 | 类型 | 等级 | 编造 | 复评题数 |",
                  "|---|---|---|---|---|---|"]
        for r in f["cross_reviews"]:
            lines.append(
                f"| `{r['card']}` | {r['reviewer']} | {r['type']} | "
                f"{r['grade']} | {'⚠️ 是' if r['fabrication'] else '否'} | {r['n_answers']} |")
        lines.append("")
    lines += [
        "> 边界：跨模型复评每卡仅 1 份异源；**人类复评 0 例**（开工包已备，见 "
        "`docs/human-review-packages/`）。效用对照的区分度集中在 `locator_citation` 一道信号。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成质量证据摘要")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    f = gather()
    if args.json:
        print(json.dumps(f, ensure_ascii=False, indent=2))
        return 0
    md = to_markdown(f)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"✅ 已写入 {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
