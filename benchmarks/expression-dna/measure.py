#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmarks/expression-dna/measure.py — 表达 DNA 六维的**量化证据行**（路线图 B4）。

**为什么要有这个脚本**：`extractors/persona-extractor.md` 的表达 DNA 六维此前是
**定性概括**——「他说话很直接」这类结论写进卡里，既不可证伪也不可复算，
最后退化成"凭印象打分"。路线图 B4 要求：把**抽样统计**作为六维的证据行。

本脚本只做一件事：把六维里**能数的**数出来，把**数不了的**（幽默类型）明确标为
「不可机械判定，须人工给样本」。不假装全能量化。

## 六维里哪些能数、怎么数

| 维度 | 是否可机械 | 指标 |
|---|---|---|
| 句式偏好 | ✅ | 平均句长（字/句）、句长标准差、最长/最短 |
| 词汇特征 | ✅ | Top-N 高频实词（停用词表过滤） |
| 节奏感 | ✅ | 转折词频次（每千字）、并列/清单密度 |
| 确定性 | ✅ | 绝对语气词 vs 存疑语气词（每千字），给出**确定性比值** |
| 引用习惯 | ✅ | 引经典标记频次（书名号内容 Top-N）、第一人称自称频次 |
| 幽默方式 | ❌ | 机械判不了类型——**只给候选样本句，类型留给人工判** |

## 三条不能省的诚实

1. **统计对象必须钉死是谁的话。** 语录体语料里门人的提问、史传里史官的叙事，
   都不是本人的表达。用 `--speaker-only`（只取含指定标记的段落）隔离；
   不隔离时必须在输出里写 `speaker_filter: none（含他人文字，不可归因于本人）`。
   ——这条不做，整个统计就是拿别人的话给本人画像。
2. **样本量 < 阈值时报「样本不足」，不给数。** 阈值默认 3000 字；
   低于它，句长与词频的置信度太低，报了就是假精确。
3. **统计的是这个文本，不是这个人。** 译本、整理本、辑录本都会改变句式；
   输出里必须带 `edition_note` 的转述，读者才能判断能不能归因给本人。

## 用法

    python3 benchmarks/expression-dna/measure.py --corpus corpus/anchored/src-10-chuanxilu.md
    python3 benchmarks/expression-dna/measure.py --corpus <file> --speaker-only 先生曰 --json-out out.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

MIN_CHARS = 3000          # 低于此字数报「样本不足」，不给数

# 句读切分：中文句末标点
SENT_SPLIT = re.compile(r"[。！？；!?;]+")
# 停用词（只做最低限度过滤，避免"过滤"本身变成主观裁剪）
STOP = set("之乎者也矣焉哉其此彼是我你他吾爾予為與以於則而乃故蓋夫且若如所"
           "不無未有非勿毋豈何誰孰安焉曷胡得能可宜當須應將欲願敢").union(
    {"曰", "云", "先生", "愛", "問", "答", "一", "二", "三", "十", "又", "今", "時",
     "者", "也", "矣", "焉", "耳", "爾", "然", "後", "前", "中", "上", "下", "大", "小"})
# 转折词
TURN = ["然", "然而", "但", "顧", "雖然", "雖", "抑", "第", "但恐", "唯", "獨"]
# 绝对语气（确定性高）
CERTAIN = ["必", "定", "斷然", "決", "自然", "固是", "只是", "便是", "即是", "自是",
           "無疑", "決然", "斷斷", "本是", "原是"]
# 存疑语气（确定性低）
HEDGE = ["恐", "或", "庶幾", "未必", "恐未", "亦未", "竊", "姑", "且", "庶", "殆",
         "大抵", "大段", "約", "似"]
# 第一人称自称
SELF_REF = ["某", "吾", "我", "予", "僕", "愚"]
# 引经典标记：书名号内容
BOOK = re.compile(r"《([^》]{1,12})》")


def load_segments(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    parts = re.split(r"^【第([0-9]+)段】$", raw, flags=re.M)
    segs = []
    for i in range(1, len(parts), 2):
        body = parts[i + 1].strip()
        # 丢掉语料元信息段（含 source_id:）
        if "source_id:" in body:
            continue
        segs.append(body)
    return segs


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) > 1]


def measure(paths: list[Path], speaker: str | None, top: int) -> dict:
    segs: list[str] = []
    for p in paths:
        segs.extend(load_segments(p))
    if speaker:
        kept = [s for s in segs if speaker in s]
    else:
        kept = segs
    text = "\n".join(kept)
    n_chars = len(re.sub(r"\s", "", text))

    out: dict = {
        "corpus": [str(p) for p in paths],
        "speaker_filter": speaker or None,
        "segments_used": len(kept),
        "segments_total": len(segs),
        "chars": n_chars,
        "min_chars": MIN_CHARS,
    }
    if n_chars < MIN_CHARS:
        out["status"] = "insufficient_sample"
        out["note"] = (f"样本 {n_chars} < 阈值 {MIN_CHARS}，句长与词频置信度不足；"
                       f"**按纪律不给数**，不以此冒充精确。")
        return out
    out["status"] = "ok"

    sents = sentences(text)
    lens = [len(re.sub(r"\s", "", s)) for s in sents]
    mean = sum(lens) / len(lens)
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    out["sentence"] = {
        "count": len(sents),
        "mean_chars": round(mean, 1),
        "stdev_chars": round(var ** 0.5, 1),
        "min_chars": min(lens),
        "max_chars": max(lens),
    }

    # 词汇：二元切分（中文无空格，用 2-gram 近似实词；单字大多被 STOP 吃掉）
    bigrams = Counter()
    for s in sents:
        clean = re.sub(r"[^\u4e00-\u9fff]", "", s)
        for i in range(len(clean) - 1):
            g = clean[i:i + 2]
            if not (set(g) & STOP):
                bigrams[g] += 1
    out["top_bigrams"] = [{"w": w, "n": n} for w, n in bigrams.most_common(top)]

    per_k = 1000.0 / n_chars
    out["rhythm"] = {
        "turn_per_1k": round(sum(text.count(t) for t in TURN) * per_k, 2),
        "transition_words": {t: text.count(t) for t in TURN if text.count(t) > 0},
    }
    cer = sum(text.count(t) for t in CERTAIN)
    hed = sum(text.count(t) for t in HEDGE)
    out["certainty"] = {
        "certain_per_1k": round(cer * per_k, 2),
        "hedge_per_1k": round(hed * per_k, 2),
        "ratio": round(cer / hed, 2) if hed else None,
        "note": "ratio = 绝对语气词 / 存疑语气词；>3 判「很明显」型，<1 判「我不确定」型",
    }
    out["citation"] = {
        "books": [{"name": b, "n": n} for b, n in Counter(BOOK.findall(text)).most_common(8)],
        "self_ref_per_1k": round(sum(text.count(s) for s in SELF_REF) * per_k, 2),
    }
    # 幽默：机械判不了类型，只给候选样本
    cands = [s for s in sents if any(k in s for k in ["笑", "戲", "嘲", "謔", "何異", "何以異"])]
    out["humor"] = {
        "machine_judgable": False,
        "note": "幽默**类型**（讽刺/自嘲/荒诞/冷幽默）机械判不了——只给候选样本句，类型由人工判定并给样本",
        "candidate_samples": cands[:5],
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="表达 DNA 六维量化证据行")
    ap.add_argument("--corpus", required=True, nargs="+")
    ap.add_argument("--speaker-only", default=None,
                    help="只统计含该标记的段落（如 先生曰）——隔离他人文字")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--merge", action="store_true",
                    help="多份语料**合并为一份**统计（一个人有多份一手语料时用，"
                         "单份不足阈值时不得靠拆开来回避）")
    a = ap.parse_args()

    paths = [Path(p) for p in a.corpus]
    results = ([measure(paths, a.speaker_only, a.top)] if a.merge
               else [measure([p], a.speaker_only, a.top) for p in paths])
    payload = {"schema": "rulai-distill/expression-dna@1",
               "speaker_filter": a.speaker_only, "results": results}
    txt = json.dumps(payload, ensure_ascii=False, indent=2)
    if a.json_out:
        Path(a.json_out).write_text(txt + "\n", encoding="utf-8")
        print(f"✅ 已写出 {a.json_out}")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
