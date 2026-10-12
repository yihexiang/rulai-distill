"""independent_recheck — 组织级独立复评聚合器（P1#2 收口脚本）。

扫描 docs/independent-recheck/<card>/<reviewer>/review.json，产出
ORG-INDEPENDENCE-LEDGER.json / .md，标记哪些卡片已从「结构独立」升级为「组织独立」。

用法：
    python3 scripts/tdlib/independent_recheck.py [--root docs/independent-recheck] [--out-dir <dir>]

自包含：不依赖 tdlib 其它模块、不访问网络。协议见 references/independent-recheck-protocol.md。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


def _valid_review(data: dict) -> tuple[bool, str]:
    """返回 (是否有效, 原因)。有效 = 非编造 且 等级非 none。"""
    if data.get("fabrication_flagged"):
        return False, "fabrication_flagged=true"
    grade = data.get("fidelity_grade_reconfirmed")
    if grade in (None, "none"):
        return False, "grade=none"
    if data.get("reviewer_type") not in ("cross_model", "human"):
        return False, "reviewer_type 非法"
    return True, "ok"


def aggregate(root: Path) -> dict:
    root = root.resolve()
    cards: dict[str, dict] = {}
    problems: list[str] = []
    if not root.exists():
        return {"cards": {}, "problems": ["目录不存在: " + str(root)], "generated": str(date.today())}
    for card_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        card = card_dir.name
        reviews: list[dict] = []
        for rev_dir in sorted(p for p in card_dir.iterdir() if p.is_dir()):
            rf = rev_dir / "review.json"
            if not rf.exists():
                problems.append(f"[{card}/{rev_dir.name}] 缺 review.json")
                continue
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                problems.append(f"[{card}/{rev_dir.name}] JSON 解析失败: {e}")
                continue
            ok, why = _valid_review(data)
            reviews.append({
                "reviewer": rev_dir.name,
                "reviewer_type": data.get("reviewer_type"),
                "model_or_reviewer": data.get("model_or_reviewer"),
                "date": data.get("date"),
                "grade": data.get("fidelity_grade_reconfirmed"),
                "valid": ok,
                "why": why,
            })
        valid = [r for r in reviews if r["valid"]]
        cards[card] = {
            "org_independent": len(valid) >= 1,
            "valid_reviews": len(valid),
            "total_reviews": len(reviews),
            "reviewer_types": sorted({r["reviewer_type"] for r in valid if r["reviewer_type"]}),
            "reviews": reviews,
        }
    return {"cards": cards, "problems": problems, "generated": str(date.today())}


def to_markdown(ledger: dict) -> str:
    lines = ["# 组织级独立复评台账（ORG-INDEPENDENCE-LEDGER）\n"]
    lines.append(f"> 生成日期：{ledger['generated']}　协议：references/independent-recheck-protocol.md\n")
    lines.append("| 卡片 | 组织独立 | 有效复评 | 类型 |")
    lines.append("|---|---|---|---|")
    for card, info in ledger["cards"].items():
        org = "✅" if info["org_independent"] else "❌（结构独立）"
        types = "/".join(info["reviewer_types"]) or "—"
        lines.append(f"| {card} | {org} | {info['valid_reviews']}/{info['total_reviews']} | {types} |")
    if not ledger["cards"]:
        lines.append("| （暂无复评产物） | — | — | — |")
    if ledger["problems"]:
        lines.append("\n## 问题\n")
        for p in ledger["problems"]:
            lines.append(f"- {p}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="组织级独立复评聚合器")
    ap.add_argument("--root", default="docs/independent-recheck", help="复评产物根目录")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认与 root 同级生成 LEDGER）")
    args = ap.parse_args(argv)
    root = Path(args.root)
    ledger = aggregate(root)
    out_dir = Path(args.out_dir) if args.out_dir else root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ORG-INDEPENDENCE-LEDGER.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "ORG-INDEPENDENCE-LEDGER.md").write_text(to_markdown(ledger), encoding="utf-8")
    n_org = sum(1 for c in ledger["cards"].values() if c["org_independent"])
    print(f"已聚合 {len(ledger['cards'])} 张卡片；达成组织独立 {n_org} 张；问题 {len(ledger['problems'])} 条")
    print(f"台账：{out_dir / 'ORG-INDEPENDENCE-LEDGER.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
