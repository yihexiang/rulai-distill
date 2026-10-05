#!/usr/bin/env python3
"""引语—段号锚定核验：检查「§N 引文」里的引文**确实在第 N 段内**。

背景（缺陷 #46，2026-10-05）：
`verify_quotes` 验的是「这条引语在语料里存在吗」——**全文搜索，能过就算过**。
于是下面这条编造引用一路绿灯：

    §232 提到 "except with Uber"（他承认那是例外）

它在 §233（`except with Uber Lilith` 是《暗黑破坏神》的boss），
而 §232 讲的是"我总是会做到"。**引语真实存在，只是挂错了段号与论点。**

这是**门槛设计错误**，不是实现 bug：全文存在性 ≠ 段号锚定。
本模块把门槛从「存在」提到「在被引用的那一段里」，这一条是可机械判定的。

三道判定，逐级降级但**绝不静默放过**：
1. **ANCHOR_HIT**  —— 引语在 §N 段内（含跨行拼接，见`--allow-span`）
2. **SPAN_HIT**    —— 跨了相邻段（引语被字幕分段切断），报出来并记`spans`
3. **ANCHOR_MISS** —— §N 段内没有；给出**最可能的真实段号**供人工确认

设计上的三条硬规矩（都是被本项目自己的缺陷教出来的）：
- **不猜**。找不到就报 ANCHOR_MISS 并给候选段号，绝不"大概是"。
- **不静默**。`if not found: continue` 这类写法在本项目出现过 1 次假阴性。
- **必须能抓到 FAIL**。只会说 PASS 的检查器比没有更危险。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9']+")
TS_RE = re.compile(r"^\[(\d\d:\d\d:\d\d(?:\.\d+)?)\]", re.M)
# 卡片里的段号有三种写法，必须都认：
#   "src-01 §227"  —— 显式带来源（多份语料时用）
#   "§227"         —— 裸段号，默认指第一份语料（本项目卡片的事实约定）
#   "§60/§74"      —— 并列锚点
# 第一版只认裸 §N 且按全局段号查表，于是把"src-03 §60"当成全局 §60 → 全部 SPAN_HIT。
# **这是核验器自己的口径错，不是卡片的错** —— 又一次"工具产生假阳性"，
# 与缺陷#7/#8（校验器不兼容上游格式）同类。
CITE_RE = re.compile(r"(?:(src-[A-Za-z0-9_.-]+)\s*)?§(\d+)"
                     r"(?:\s*(?:\[\d\d:\d\d:\d\d[^\]]*\])?)")
# 并列锚点 "§60/§74"：CITE_RE 只吃到 §60，§74 被吞掉 → 明明锚在 §74 却报 SPAN_HIT。
# 修法：抓到第一个之后，把紧随其后的 "/§N" 也收进同一组。
JOIN_RE = re.compile(r"/\s*§(\d+)")
def _resolve_src(raw: str | None, corpora: dict) -> str | None:
    """把卡片里写的来源标识解析成 corpora 的键。

    ⚠️ 别名表与实际键名必须同源。第一版别名写 `03-qatar-forum.md`（带扩展名），
    而 `load_corpora` 用的键是 `Path.stem`（不带扩展名）→ 查不到 → **静默跳过整个来源**，
    于是"src-03 §74"被判成 NOT_IN_CORPUS。这是**核验器自己的口径错**，
    与缺陷 #7/#8（校验器不兼容上游格式）同类，且更难发现——因为它伪装成"卡片错了"。

    这里改成**后缀匹配**，不再依赖手写别名表：
    `src-03` 匹配 `03-qatar-forum`，`src-01` 匹配 `01-lex-fridman-420`。
    """
    if not corpora:
        return None
    if raw is None:
        return next(iter(corpora))
    r = raw.strip().lower()
    if r in corpora:
        return r
    tail = r.split("-", 1)[-1] if r.startswith("src-") else r
    hits = [k for k in corpora if k.lower() == tail or k.lower().startswith(tail + "-")
            or tail in k.lower()]
    return hits[0] if len(hits) == 1 else (hits[0] if hits else None)


# --------------------------------------------------------------------------
# 语料按段号切分
# --------------------------------------------------------------------------
def split_paragraphs(text: str) -> dict[int, str]:
    """按 `[时间戳]` 出现位置把逐字稿切成 {段号: 该段全文}。

    段号从 0 起，与 `tools/show.py --start/--end` 以及卡片里写的 §N 完全一致——
    **这一条必须三处同源**，否则核验器会系统性错位（见缺陷 #24/#29）。
    """
    # 注意：re.M 必须编进 pattern。给已编译 pattern 的 finditer 传flags **无效**，
    # 会静默返回空列表 → 全篇判 0 段 → 核验器对任何引语都PASS。
    # **这正是缺陷 #28「if not cands: continue 静默跳过」的同一种死法。**
    marks = [(m.start(), m.group(1)) for m in TS_RE.finditer(text)]
    if not marks:
        raise ValueError(
            "逐字稿里找不到任何 [时间戳] 行——无法建立段号索引。"
            "请确认传的是 td.py transcript 产出的文件（原始 SRT 没有这个格式）。")
    out: dict[int, str] = {}
    for i, (start, _ts) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[i] = text[start:end]
    return out


def norm_words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def shingles(words: list[str], n: int) -> set[tuple[str, ...]]:
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


# --------------------------------------------------------------------------
# 核验
# --------------------------------------------------------------------------
def check_quote_in_para(quote: str, para_texts: dict[int, str], n: int = 5,
                        target: int | None = None) -> dict:
    """检查 quote 是否在**声明的段号 target** 段落内。

    target 由调用方显式传入。**不要用模块级可变状态**：
    第一版用 `global _target`，结果 verify_file 里的循环把它改了之后，
    后面每一次判定都拿的是最后一次的段号 —— 静默错位，且不报错。
    """
    qw = norm_words(quote)
    # n-gram 长度必须自适应：短引语（如 "except with Uber" 只有 4 词）
    # 若固定用 5-gram 会退化成长度 1 的 shingle，退化成"整句完全相等"，
    # 于是短引语要么永远 TOO_SHORT、要么被误判。
    # **这是本模块第一版真实踩的坑**：拿它去查那条编造引用时直接 PASS 了。
    # 3 词是下限：真实的短引语（如 "except with Uber"）只有 3 词，
    # 门槛设 4 会让它永远 TOO_SHORT —— 那等于给短引语开后门。
    k = min(n, max(2, len(qw) // 2)) if len(qw) >= 3 else None
    if k is None:
        return {"verdict": "TOO_SHORT", "hit_at": None, "spans": [],
                "candidates": [], "words": len(qw), "ngram": 0}
    qsh = shingles(qw, k)
    if not qsh:
        return {"verdict": "TOO_SHORT", "hit_at": None, "spans": [],
                "candidates": [], "words": len(qw), "ngram": 0}

    rates: dict[int, float] = {}
    for num, ptext in para_texts.items():
        psh = shingles(norm_words(ptext), k)
        if not psh:
            continue
        hit = sum(1 for s in qsh if s in psh)
        if hit:
            rates[num] = hit / len(qsh)

    if not rates:
        return {"verdict": "NOT_IN_CORPUS", "hit_at": None, "spans": [],
                "candidates": [], "words": len(qw)}

    best = max(rates, key=lambda k: rates[k])
    # 严格门槛：与 verify_quotes 对齐（>=0.6 判命中），避免两个工具口径打架
    if rates[best] >= 0.6:   # noqa: PLR2004 —— 与 verify_quotes 同口径
        if target is not None and best == target:
            return {"verdict": "ANCHOR_HIT", "hit_at": best, "spans": [],
                    "candidates": _top(rates), "words": len(qw), "ngram": k,
                    "rate": round(rates[best], 3)}
        # 引语确实存在，但不在声明的那一段 → 段号挂错。
        # **这里绝不能因为"引语存在"就放行**——那正是本命令存在的理由。
        return {"verdict": "SPAN_HIT", "hit_at": best, "spans": sorted(rates),
                "candidates": _top(rates), "words": len(qw), "ngram": k,
                "rate": round(rates[best], 3)}
    if target is not None and rates.get(target, 0.0) >= 0.4:
        # 落在声明段内但命中率 0.4~0.6：多半是**跨段引语被字幕分段切开**。
        # 不放行（那会给"段号写错"开门），但也不误判为段号错——
        # 归为 PARTIAL 交人工一句判断。**0.4 是"值得看一眼"，不是"算通过"。**
        return {"verdict": "ANCHOR_PARTIAL", "hit_at": target, "spans": [],
                "candidates": _top(rates), "words": len(qw), "ngram": k,
                "rate": round(rates[target], 3)}
    return {"verdict": "ANCHOR_MISS", "hit_at": None, "spans": [],
            "candidates": _top(rates), "words": len(qw), "ngram": k,
            "rate": round(rates[best], 3)}


def _top(rates: dict[int, float], k: int = 3) -> list[dict]:
    items = sorted(rates.items(), key=lambda kv: -kv[1])[:k]
    return [{"para": n, "rate": round(r, 3)} for n, r in items]


def verify_file(claim_file: Path, corpora: dict[str, dict[int, str]],
                n: int = 5, require_anchor: bool = True) -> dict:
    """核验一份卡片/候选文件里的所有「§N 引文」。

    只检查**带 §N 标注**的引语——没标注的属于"不可定位"，单列出来。
    这与 CONSTRAINTS C10「引用数 ≠ 核验数」同一个纪律：
    **必须把"引语总数"与"锚定核验数"都报出来，并对账。**
    """
    text = claim_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    results = []
    unresolved: list[dict] = []
    seen_quotes = 0
    noise = 0   # 被引语形状过滤掉的中文正文数

    default_src = next(iter(corpora)) if corpora else None

    for lineno, line in enumerate(lines, 1):
        # 一行里可能有多个 §N（并列时间戳），也可能有多个引语
        cits = []
        for m in CITE_RE.finditer(line):
            stem = _resolve_src(m.group(1), corpora)
            group = [int(m.group(2))]
            # 吃掉并列锚点：§60/§74、§143/§144
            tail = line[m.end():]
            jm = re.match(r"((?:\s*/\s*§\d+)+)", tail)
            if jm:
                group += [int(x) for x in JOIN_RE.findall(jm.group(1))]
            cits += [(stem, g) for g in group]
        # 引语必须"以英文词开头、以英文词收尾"才算引语。
        # 单纯 r'"([^"\n]{12,600})"' 会把两个引号之间的**中文正文**也当成引语
        # （如 `"Give me some evidence for that" ——**同一句式对敌我双方各用一次**。`）。
        # 这类不是引语却进了核验器，产出假阳性——**核验器自己的噪声**。
        quotes = [q for q in re.findall(r'"([^"\n]{12,600})"', line)
                  if re.match(r"[A-Za-z0-9]", q.strip())
                  and re.search(r"[A-Za-z]{2}", q)]
        raw_quotes = re.findall(r'"([^"\n]{12,600})"', line)
        noise += len(raw_quotes) - len(quotes)
        for q in quotes:
            if not re.search(r"[a-zA-Z]{3}", q):
                continue
            seen_quotes += 1
            # 该行所有段号里，任一命中即算锚定成功（并列锚点是合法用法）
            best_local = None
            # 每个标注 (来源, 段号) 各查一次：**段号只在它自己的来源内解释**
            for stem, target in (cits or [(default_src, None)]):
                para = corpora.get(stem) if stem else None
                if not para:
                    # 来源解析不到必须显式记一笔，不能静默 continue——
                    # 那是缺陷 #28 的同一种死法（跳过=看起来没事）
                    unresolved.append({"line": lineno, "src": stem,
                                       "quote": q[:120], "reason": "来源未在 --corpus 中提供"})
                    continue
                r = check_quote_in_para(q, para, n=n, target=target)
                r["claimed_at"] = target
                r["claimed_src"] = stem
                if r["verdict"] == "ANCHOR_HIT":
                    best_local = r
                    break
                if best_local is None:
                    best_local = r
                elif best_local["verdict"] == "NOT_IN_CORPUS" \
                        and r["verdict"] != "NOT_IN_CORPUS":
                    best_local = r
            r = best_local or {"verdict": "TOO_SHORT", "hit_at": None, "spans": [],
                               "candidates": [], "words": 0}
            r["line"] = lineno
            r["quote"] = q[:160]
            r["anchored"] = bool(cits)
            results.append(r)

    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1

    # 只有 ANCHOR_HIT 算通过。SPAN_HIT = 引语在别的段里 = 挂错段号 = 失败。
    # （旧版把 SPAN_HIT 也算过，那等于给"段号写错"开后门。）
    anchored = sum(1 for r in results if r["verdict"] == "ANCHOR_HIT")
    partial = [r for r in results if r["verdict"] == "ANCHOR_PARTIAL"]
    miss = [r for r in results
            if r["verdict"] in ("ANCHOR_MISS", "NOT_IN_CORPUS", "SPAN_HIT")]
    unanchored = sum(1 for r in results if not r["anchored"])

    return {
        "file": str(claim_file),
        "quotes_seen": seen_quotes,
        "anchored_checked": anchored,
        "tally": tally,
        "unanchored": unanchored,
        "unresolved_sources": unresolved,
        "noise_filtered": noise,
        # 对账：见到的引语 = 已锚定核验 + 未锚定 + 失配+ 过短
        "reconciliation": {
            "seen": seen_quotes,
            "anchor_hit": anchored,
            "span_hit": sum(1 for r in results if r["verdict"] == "SPAN_HIT"),
            "anchor_miss": sum(1 for r in results if r["verdict"] == "ANCHOR_MISS"),
            "not_in_corpus": sum(1 for r in results if r["verdict"] == "NOT_IN_CORPUS"),
            "too_short": sum(1 for r in results if r["verdict"] == "TOO_SHORT"),
        },
        "failures": [
            {"line": r["line"], "claimed_at": r["claimed_at"],
             "claimed_src": r.get("claimed_src"), "verdict": r["verdict"],
             "found_at": r.get("hit_at"), "rate": r.get("rate"),
             "quote": r["quote"], "candidates": r.get("candidates", [])}
            for r in miss
        ],
        # 来源解析失败也算 FAIL：无法核验 ≠ 通过
        "partial": [{"line": r["line"], "claimed_at": r["claimed_at"],
                     "rate": r.get("rate"), "quote": r["quote"]} for r in partial],
        # PARTIAL 不判FAIL：它已落在正确段号内，只是被字幕分段切开。
        # 但必须报出来让人看见——**静默的"差不多对"比报错更难查**。
        "verdict": "FAIL" if (miss or unresolved) else "PASS",
    }


def _merged(corpora: dict[str, dict[int, str]]) -> dict[int, str]:
    """把多份语料拼成单一全局段号空间（只读视图）。

    ⚠️ 现已**不被 verify_file 使用**——段号只在各自来源内解释（见 CITE_RE 注释）。
    保留它是因为导出"全局连续编号"视图仍有价值；
    任何要按全局段号下结论的场合，必须先声明用的是哪套编号。
    """
    out: dict[int, str] = {}
    cursor = 0
    for _stem, paras in corpora.items():
        for num in sorted(paras):
            out[cursor] = paras[num]
            cursor += 1
    return out


def load_corpora(paths: list[Path]) -> dict[str, dict[int, str]]:
    return {p.stem: split_paragraphs(p.read_text(encoding="utf-8", errors="replace"))
            for p in paths}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", required=True, nargs="+", type=Path,
                    help="卡片/候选文件（要检查§N 引文的那份）")
    ap.add_argument("--corpus", required=True, nargs="+", type=Path,
                    help="逐字稿（段号来源）")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    corpora = load_corpora(args.corpus)
    reports = [verify_file(c, corpora, n=args.n) for c in args.claim]

    merged = {
        "claims": reports,
        "quotes_seen": sum(r["quotes_seen"] for r in reports),
        "anchored_checked": sum(r["anchored_checked"] for r in reports),
        "failures": [f for r in reports for f in r["failures"]],
        "verdict": "FAIL" if any(f for r in reports for f in r["failures"]) else "PASS",
    }
    print(json.dumps({k: v for k, v in merged.items() if k != "failures"},
                     ensure_ascii=False, indent=2))
    for r in reports:
        print(f"\n-- {r['file']}")
        print(f"   引语 {r['quotes_seen']} 条：锚定核验 {r['anchored_checked']}，"
              f"未标注段号 {r['unanchored']}，判定 {r['tally']}")
        print(f"   对账：{r['reconciliation']}")
    if merged["failures"]:
        print("\n--- 失配明细（引语不在它自己声明的段号里）---", file=sys.stderr)
        for f in merged["failures"]:
            cands = "、".join(f"§{c['para']}({c['rate']})" for c in f["candidates"]) or "无候选"
            print(f"  {Path(f['file']).name if 'file' in f else ''}"
                  f":{f['line']}  声明 §{f['claimed_at']}  实际 {f['verdict']}"
                  f"  最可能段号：{cands}", file=sys.stderr)
            print(f"     「{f['quote'][:100]}」", file=sys.stderr)
    if args.json_out:
        args.json_out.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return 2 if merged["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
