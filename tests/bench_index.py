#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_index.py — TD lexindex vs 仓颉 build_index 的检索质量对照（同一语料、同一查询集）。

设计要点（避免"看起来在赢"的假对比）：
  * 直接查两边的 sqlite，**不用各自的 CLI 打印**（CLI 只打印块内前 N 字，命中可能在截断之外，
    肉眼对比会得出错误结论——本次评测第一版就犯了这个错）。
  * 用**可核查的真值**：某块文本是否包含查询词（大小写不敏感）。据此算 precision / recall。
  * 分别计算两种语义：
      AND 语义（TD 默认）：块必须包含查询的全部词
      OR  语义（仓颉实现）：块包含查询的任一词即命中
  * 报告命中数、真值数、真阳性/假阳性。

用法：python3 bench_index.py <td.sqlite> <cangjie.sqlite> <td_chunks.jsonl> <cangjie_chunks.jsonl>
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from tdlib.chunking import _cjk_bigrams  # noqa: E402

QUERIES = [
    "first principles",
    "exponentially",
    "production",
    "Mars",
    "manufacturing",
    "starlink",
    "algorithm",
    "cost",
    "AI",
    "engineering",
]


def load_chunks_side(chunks_jsonl: Path) -> list[dict]:
    """按**各自**的分块产物取真值文本。

    关键：第一版基准用自己切的 gt-XXXX 块 ID 去比对两边的索引，
    ID 根本对不上 → tp 恒为 0，两边都显示 0 分。**这是基准脚本的缺陷，不是索引的缺陷。**
    修正：真值必须用该索引自己 chunks 文件里的 chunk_id 与 text。
    """
    out = []
    for line in chunks_jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            c = json.loads(line)
            out.append({"chunk_id": c["chunk_id"], "text": c.get("text", "")})
    return out


def truth_sets(chunks: list[dict], q: str) -> tuple[set[str], set[str]]:
    ql = q.lower()
    words = [w for w in re.findall(r"[A-Za-z0-9]+", ql) if len(w) > 1]
    if not words:
        return set(), set()
    and_set, or_set = set(), set()
    for c in chunks:
        t = c["text"].lower()
        if all(w in t for w in words):
            and_set.add(c["chunk_id"])
        if any(w in t for w in words):
            or_set.add(c["chunk_id"])
    return and_set, or_set


def query_td(db: Path, q: str, limit: int = 50) -> set[str]:
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute("SELECT chunk_id FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                           (_cjk_bigrams(q), limit)).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


def query_cangjie(db: Path, q: str, limit: int = 50) -> set[str]:
    con = sqlite3.connect(str(db))
    try:
        terms = " OR ".join(f'"{t}"' for t in _cjk_bigrams(q).split())
        rows = con.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (terms, limit)).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


def score(hits: set[str], truth: set[str], universe: int) -> dict:
    tp = len(hits & truth)
    fp = len(hits - truth)
    fn = len(truth - hits)
    return {
        "hits": len(hits), "tp": tp, "fp": fp, "fn": fn,
        "precision": round(tp / len(hits), 3) if hits else 0.0,
        "recall": round(tp / len(truth), 3) if truth else 1.0,
        "f1": round(2 * tp / (2 * tp + fp + fn), 3) if (tp or fp or fn) else 0.0,
    }


def main() -> int:
    K = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    td_db, cj_db = Path(sys.argv[1]), Path(sys.argv[2])
    td_chunks = load_chunks_side(Path(sys.argv[3]))
    cj_chunks = load_chunks_side(Path(sys.argv[4]))
    print(f"真值块数：TD {len(td_chunks)} / 仓颉 {len(cj_chunks)}（各按自身分块）\n")
    rows = []
    for q in QUERIES:
        and_truth, _ = truth_sets(td_chunks, q)          # TD 用 AND 语义
        _, or_truth = truth_sets(cj_chunks, q)            # 仓颉用 OR 语义
        # 关键：limit 必须远小于真值规模，否则 recall 被 limit 人为封顶，指标失去意义。
        # 第一版用 limit=50 而真值有 100~3000 块 → 双方 recall 都被压在 0.08 以下，
        # 那是度量设计缺陷，不是索引缺陷。改用 precision@K（排序质量的标准指标）。
        td = query_td(td_db, q, limit=K)
        cj = query_cangjie(cj_db, q, limit=K)
        # 各自按自己的语义对齐真值：TD=AND，仓颉=OR
        s_td = score(td, and_truth, len(td_chunks))
        s_cj = score(cj, or_truth, len(cj_chunks))
        rows.append((q, len(and_truth), s_td, len(or_truth), s_cj))
        print(f"【{q}】真值(AND)={len(and_truth)}  真值(OR)={len(or_truth)}  K={K}")
        print(f"   TD     hits={s_td['hits']:>3} tp={s_td['tp']:>3} fp={s_td['fp']:>3} "
              f"P={s_td['precision']} R={s_td['recall']} F1={s_td['f1']}")
        print(f"   仓颉    hits={s_cj['hits']:>3} tp={s_cj['tp']:>3} fp={s_cj['fp']:>3} "
              f"P={s_cj['precision']} R={s_cj['recall']} F1={s_cj['f1']}")
    print("\n=== 汇总（宏平均） ===")
    for name, idx_p, idx_r, idx_f in (("TD", 2, 2, 2), ("仓颉", 4, 4, 4)):
        p = sum(r[idx_p]["precision"] for r in rows) / len(rows)
        rc = sum(r[idx_p]["recall"] for r in rows) / len(rows)
        f1 = sum(r[idx_p]["f1"] for r in rows) / len(rows)
        print(f"  {name:<5} precision={p:.3f}  recall={rc:.3f}  F1={f1:.3f}")
    print("""
读法说明：
  * TD 用 AND 语义（全部词都命中才算），仓颉用 OR 语义（任一词命中即算）——
    这是两者**设计选择不同**，不是谁对谁错；真值也按各自语义分别计算，才是对齐的。
  * precision 低说明混进无关块；recall 低说明漏掉真命中。
  * 双方都是各自语义下的 F1，不要跨语义比较绝对值。
  * recall 在真值规模 >> K 时必然很低，这是度量设计的必然结果，不是索引差；
    真正可比的是 precision@K（Top-K 里有多少是真命中）。""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
