#!/usr/bin/env python3
"""语料重叠检测：确认两批素材之间的重复度（用于"换素材重蒸馏"前的零重叠证明）。

确定性操作，无模型参与。做两件事：
1. 8-gram 词级shingle 的包含率（新语料里有多少 n-gram 出现在旧语料里）
2. 逐句包含检查（新语料整句是否在旧语料出现，忽略大小写与标点）

用法:
  td.py overlap --new <新语料.md> --old <旧语料.md> [--n 8] [--json-out r.json]
退出码 0 = 无实质重叠；2 = 检出重叠

为什么要它：2026-10-04 用 17,144 条推文蒸馏过一次，2026-10-05 换访谈素材重蒸时，
"素材不重复"这句话如果只靠记忆判断就无法证伪。这个脚本把它变成可复现的数字。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def shingles(words: list[str], n: int) -> set[tuple[str, ...]]:
    if len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def sentences(text: str) -> list[str]:
    rough = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    out = []
    for s in rough:
        w = normalize(s)
        if len(w) >= 8:
            out.append(" ".join(w))
    return out


def compute(new_path, old_path, n: int = 8) -> dict:
    """核心：返回重叠报告（纯函数，无 I/O 副作用，测试可直接调）。"""
    new_text = Path(new_path).read_text(encoding="utf-8", errors="replace")
    old_text = Path(old_path).read_text(encoding="utf-8", errors="replace")
    new_words = normalize(new_text)
    old_words = normalize(old_text)
    new_sh = shingles(new_words, n)
    old_sh = shingles(old_words, n)
    shared = new_sh & old_sh
    contain = len(shared) / len(new_sh) if new_sh else 0.0
    new_sents = sentences(new_text)
    old_norm = " \n ".join(normalize(old_text))
    old_sent_set = set(sentences(old_text))
    dup_sents = [s for s in new_sents if s in old_sent_set]
    contained = [s for s in new_sents if s in old_norm]
    # 阈值：包含率 >0.5% 或出现整句重复即判为素材重复
    verdict = "FAIL" if (contain > 0.005 or dup_sents) else "PASS"
    return {
        "new_file": str(new_path),
        "old_file": str(old_path),
        "ngram_n": n,
        "new_words": len(new_words),
        "old_words": len(old_words),
        "new_shingles": len(new_sh),
        "shared_shingles": len(shared),
        "containment": round(contain, 6),
        "new_sentences": len(new_sents),
        "exact_duplicate_sentences": len(dup_sents),
        "substring_contained_sentences": len(contained),
        "overlap_verdict": verdict,
        "examples": (dup_sents + contained)[:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    new_text = args.new.read_text(encoding="utf-8", errors="replace")
    old_text = args.old.read_text(encoding="utf-8", errors="replace")

    new_words = normalize(new_text)
    old_words = normalize(old_text)
    new_sh = shingles(new_words, args.n)
    old_sh = shingles(old_words, args.n)

    shared = new_sh & old_sh
    contain = len(shared) / len(new_sh) if new_sh else 0.0

    new_sents = sentences(new_text)
    old_norm = " \n ".join(normalize(old_text))
    old_sent_set = set(sentences(old_text))
    dup_sents = [s for s in new_sents if s in old_sent_set]
    contained = [s for s in new_sents if s in old_norm]

    report = {
        "new_file": str(args.new),
        "old_file": str(args.old),
        "ngram_n": args.n,
        "new_words": len(new_words),
        "old_words": len(old_words),
        "new_shingles": len(new_sh),
        "shared_shingles": len(shared),
        "containment": round(contain, 6),
        "new_sentences": len(new_sents),
        "exact_duplicate_sentences": len(dup_sents),
        "substring_contained_sentences": len(contained),
        "examples": (dup_sents + contained)[:5],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 阈值：8-gram 包含率 >0.5% 或出现整句重复即判为素材重复
    if contain > 0.005 or dup_sents:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
