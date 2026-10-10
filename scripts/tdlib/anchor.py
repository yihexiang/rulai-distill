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
2. **SPAN_HIT**    —— 引语存在但**不在它声明的那一段**（段号挂错 / 字幕分段），报出来并记`spans`
3. **ANCHOR_MISS** —— 段内没有；给出**最可能的真实段号**供人工确认

另有一类**不计入失败**：**UNANCHORED** —— 引语没有 §N 标注（不可定位）。
它不判失败（与 verify-quotes / lint-quotes 的"无出处即跳过"同口径），但如实计数、如实列出，
绝不静默——**"没有段号"和"段号写错"是两件事，混在一起会让好卡片被误判**（复审 #1）。

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
# 书类语料用 【第N段】 / 【第N条】 作段号标记（复审 #1：anchor 此前只认 [时间戳]，
# 书类语料会直接 ValueError）。两类标记都支持后，anchor 原生覆盖书/视频/人物三类素材。
BOOK_RE = re.compile(r"【第(\d+)[段条]】")
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
# 篇-章号（如 一之三、四之十六）：《論語》等经典的细粒度定位体例（缺陷 #71）。
# 卡片与语料都用"独占一行"的标签（如 `一之三` 单独成行），两个标签之间即一段。
# **不做汉数字换算**——标签按不透明字符串处理（只做映射，不解析成数字），
# 既避免换算错误，也让同一套机制能推广到《史記》「卷X·传Y」等别的编号体例。
VERSE_LABEL_LINE_RE = re.compile(
    r"^\s*([一二三四五六七八九十百]+之[一二三四五六七八九十百]+)\s*$", re.M)
VLABEL_RE = re.compile(
    r"(?:(src-[A-Za-z0-9_.-]+)\s*)?([一二三四五六七八九十百]+之[一二三四五六七八九十百]+)"
    r"(?![\u4e00-\u9fff])")  # 负向前瞻：避免把"一之三十五"当成"一之三"+尾随数字
VERSE_KEY_BASE = 1_000_000  # 与 ts(0..N) / 书类(显式N) 的键空间无碰撞


def _verse_locator(text: str) -> tuple[str | None, str] | None:
    """从一行里找篇-章号定位（卡片侧三种形状）。返回 (来源前缀, 标签) 或 None。

    形状（其余一律不算，防正文误报）：
      (a) 块引用行首：`> 一之三 「…」`（本次論語卡的形状）；
      (b) 出处行：行首 `——` 后紧跟标签；
      (c) 同行紧邻引号：`一之三「…」` 且标签前一字符不是汉字（负向后顾）。
    """
    m = VLABEL_RE.search(text)
    if not m:
        return None
    prefix, label = m.group(1), m.group(2)
    after = text[m.end():]
    prev = text[m.start() - 1] if m.start() > 0 else ""
    prev_not_cjk = not (prev and CJK_CHAR_RE.match(prev))
    is_quoted = bool(re.match(r"\s*[「“\"]", after))
    is_outro = bool(re.match(r"^\s*>?\s*——", text))  # 出处行：`—— 篇-章号` 或块内 `> —— 篇-章号`
    if (prev_not_cjk and is_quoted) or is_outro:
        return (prefix, label)
    return None


def _verse_outro(text: str) -> tuple[str | None, str] | None:
    """只认**出处行**形状 `—— 篇-章号`（或 `> —— 篇-章号`）。

    与 `_verse_locator` 不同：不认"行首/同行紧邻引号的标签"。向后看取段号时**只能**用出处行，
    否则会把"下一行自带标签的引语"误当成当前无标注引语的段号（#71 回归：混编卡里
    `> 「學而時習之…」` 无标注，却被错误继承下一行 `> 一之三 「…」` 的段号）。
    出处行才代表"上一条引语的段号信号"。
    """
    if not re.match(r"^\s*>?\s*——", text):
        return None
    vm = VLABEL_RE.search(text)
    if not vm:
        return None
    return (vm.group(1), vm.group(2))


class Corpus(dict):
    """`{int: str}` 的子类：**现有"当 dict 用"的代码零改动**，只额外挂定位索引。

    - verses: 标签 → 段键（如 "一之三" → 1_000_002）
    - labels: 段键 → 标签（仅展示用）
    - verses_duplicated: 重复出现的标签（首个生效，其余报出但不覆盖）
    """

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.verses: dict[str, int] = {}
        self.labels: dict[int, str] = {}
        self.verses_duplicated: list[str] = []


def index_corpus(text: str) -> Corpus:
    """把语料建段索引，支持三类标记（ts / 【第N段】 / 篇-章号），**向后兼容**。

    - 有篇-章号标签（独占一行）→ 以标签为段边界切细粒度段；
      **若语料同时带【第N段】/时间戳**（如维基文库《論語》：5 个【第N段】wrapper 各含数十个篇-章号），
      那些是**粗粒度 wrapper**，内含所有篇-章号——若一并建索引，细粒度引语会"同时命中 wrapper 段"
      而被误判 SPAN_HIT。故篇-章号存在时**丢弃粗粒度段，只留细粒度**（#71 的判定正确性优先）。
    - 无篇-章号但有 ts/book 标记 → 沿用 split_paragraphs 的既有段号。
    - 三类标记全无 → 抛 ValueError（错误信息同步三类标记）。
    """
    out = Corpus()
    try:
        base = split_paragraphs(text)
    except ValueError:
        base = {}
    verse_ms = list(VERSE_LABEL_LINE_RE.finditer(text))
    if verse_ms:
        for i, m in enumerate(verse_ms):
            label = m.group(1)
            start = m.start()
            end = verse_ms[i + 1].start() if i + 1 < len(verse_ms) else len(text)
            body = text[start:end].strip()
            key = VERSE_KEY_BASE + i
            if label in out.verses:
                out.verses_duplicated.append(label)
            out[key] = body
            out.verses[label] = key
            out.labels[key] = label
    elif base:
        for k, v in base.items():
            out[k] = v
    else:
        raise ValueError(
            "语料里找不到任何 [时间戳] / 【第N段】 / 篇-章号（如 一之三）标记——无法建立段号索引。"
            "书类语料请用 td.py corpus-anchor 规整成 【第N段】 形式，"
            "视频/播客请用 td.py transcript 产出 [时间戳] 逐字稿，"
            "经典篇-章号（如 一之三）语料请确保篇-章号独占一行。")
    return out


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
    """按段号标记把语料切成 {段号: 该段全文}。

    支持两类标记（复审 #1）：
      * `[时间戳]`  —— 视频/播客/逐字稿，段号按出现顺序 0,1,2…（与卡片 §N 一致）
      * `【第N段】` / `【第N条】` —— 书类语料，段号用标记里的显式 N（与卡片「第N段」对应）

    段号从 0 起，与 `tools/show.py --start/--end` 以及卡片里写的 §N 完全一致——
    **这一条必须三处同源**，否则核验器会系统性错位（见缺陷 #24/#29）。
    """
    # 注意：re.M 必须编进 pattern。给已编译 pattern 的 finditer 传flags **无效**，
    # 会静默返回空列表 → 全篇判 0 段 → 核验器对任何引语都PASS。
    # **这正是缺陷 #28「if not cands: continue 静默跳过」的同一种死法。**
    marks: list[tuple[int, str, int | None]] = []
    for m in TS_RE.finditer(text):
        marks.append((m.start(), "ts", None))
    for m in BOOK_RE.finditer(text):
        marks.append((m.start(), "book", int(m.group(1))))
    if not marks:
        raise ValueError(
            "语料里找不到任何 [时间戳] 或 【第N段】 标记——无法建立段号索引。"
            "书类语料请用 td.py corpus-anchor 规整成 【第N段】 形式，"
            "视频/播客请用 td.py transcript 产出 [时间戳] 逐字稿。")
    marks.sort(key=lambda x: x[0])
    out: dict[int, str] = {}
    cursor = 0
    for i, (start, kind, num) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        if kind == "ts":
            seg = cursor
            cursor += 1
        else:
            seg = num  # 书类用显式段号，直接对应卡片里写的「第N段」
        out[seg] = text[start:end]
    return out


CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def normalize_book_corpus(text: str, max_chars: int = 0) -> tuple[str, dict]:
    """把书类原文规整成 anchor 可读的 `【第N段】` 形式（复审 #1 的"内置转换器"）。

    * 已有 `【第N段】` 标记：按标记切段、重新顺序编号（去掉跳号/重复）。
    * 无标记：**按结构切段** —— 先按 markdown 标题（`#`～`######`）切，
      标题以下到下一个标题之间为一段；没有标题时退回按空行切。
    * `max_chars > 0` 时把过长的段再切一刀（不截断内容，只拆段），
      否则一段近万字时，引语挂到「第N 段」等于挂到整本书。

    anchor 原生读 `【第N段】`，所以规整后即可直接 `td.py anchor <卡> --corpus <规整后>`。
    返回 (规整后文本, 统计)。

    ⚠️ 2026-10-10（#70）：原实现只按**空行**切段。真实公版典籍
    （维基文库导出的《資治通鑑》等）是「**一行一段、无空行**」的格式，
    628 行只切出 **6 段**（每段近万字）——段号失去定位意义，
    而工具**照常输出「✅ 规整完成」**，没有任何异常。
    「切段失败」比「切错」更隐蔽：它给出的是一个看起来合法的段号体系。
    """
    if BOOK_RE.search(text):
        parts = BOOK_RE.split(text)
        blocks = []
        for i in range(1, len(parts), 2):
            body = (parts[i + 1] if i + 1 < len(parts) else "").strip()
            if body:
                blocks.append(body)
        resequenced = True
        had = True
        by = "markers"
    else:
        blocks = _split_by_structure(text)
        resequenced = False
        had = False
        by = "headings" if any(b.startswith("#") for b in blocks) else "blank_lines"
    if max_chars > 0:
        blocks = _oversized(blocks, max_chars)
    out = "\n\n".join(f"【第{i}段】\n{b}" for i, b in enumerate(blocks, 1))
    return out, {"segments": len(blocks), "had_markers": had,
                 "resequenced": resequenced, "split_by": by,
                 "max_chars": max_chars}


def _split_by_structure(text: str) -> list[str]:
    """按 markdown 标题切段；标题之前的前言单独成段。"""
    lines = text.splitlines()
    blocks: list[str] = []
    cur: list[str] = []
    for ln in lines:
        if re.match(r"^#{1,6}\s", ln):
            if any(x.strip() for x in cur):
                blocks.append("\n".join(cur).strip())
            cur = [ln]
        else:
            cur.append(ln)
    if any(x.strip() for x in cur):
        blocks.append("\n".join(cur).strip())
    if len(blocks) <= 1:                      # 完全没有标题 → 退回按空行
        return [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    return [b for b in blocks if b.strip()]


def _oversized(blocks: list[str], max_chars: int) -> list[str]:
    """把超过 max_chars 的段按空行/句子边界再切，**不丢内容**。"""
    out: list[str] = []
    for b in blocks:
        if len(b) <= max_chars:
            out.append(b)
            continue
        cur: list[str] = []
        n = 0
        for piece in re.split(r"(?<=[。！？；])|\n\s*\n", b):
            if not piece:
                continue
            if cur and n + len(piece) > max_chars:
                out.append("\n".join(cur).strip())
                cur, n = [], 0
            cur.append(piece)
            n += len(piece)
        if cur:
            out.append("\n".join(cur).strip())
    return [x for x in out if x.strip()]


def norm_words(text: str) -> list[str]:
    """分词：ASCII 整词 + 中文按字符 bigram（#56）。

    ⚠️ 2026-10-07：原实现是 `WORD_RE.findall(text.lower())`，只认 `[a-z0-9']+`——
    **纯中文引语切出 0 个词** → `k = None` → 判 `TOO_SHORT` → 被静默跳过，
    最后 CLI 打印「引语 0 条」+「✅ 判定 PASS」。
    也就是说：**专门为防「伪造引语」而建的这个命令，对中文卡片完全失明，
    还给出绿色的假安心**。这是同一类（#52 overlap、#55 transcript）的第三例。
    """
    out: list[str] = []
    run: list[str] = []
    word: list[str] = []

    def flush_word() -> None:
        if word:
            out.append("".join(word))
            word.clear()

    def flush_cjk() -> None:
        if run:
            if len(run) == 1:
                out.append(run[0])
            else:
                out.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
            run.clear()

    for ch in text:
        if CJK_CHAR_RE.match(ch):
            flush_word()
            run.append(ch)
        elif ch.isalnum() or ch == "'":
            flush_cjk()
            word.append(ch.lower())
        else:
            flush_word()
            flush_cjk()
    flush_word()
    flush_cjk()
    return out


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

    # 复审 #1（2026-10-09）：**无 §N 标注的引语**（target is None）不是"挂错段号"，
    # 而是"根本没有可锚定的段号"——本命令无从核验。此前它被判 SPAN_HIT / NOT_IN_CORPUS
    # 并计入 FAIL，于是官方样例卡（3 条 R 段引语带 §、另 3 条正文引语不带 §）被判 FAIL，
    # 与 verify-quotes（无出处引用块跳过）、lint-quotes（语言信号框跳过）口径不一致。
    # 现在单列为 UNANCHORED：**不判失败**，但如实计数、如实列出（不静默）。
    # 关键：UNANCHORED 由**标注有无**唯一确定，与 TOO_SHORT 不重叠——
    # 所以 `unanchored` 计数与 reconciliation 的分区完全一致，对账必平。
    # 挂了 §N 的引语照旧严判，本模块的第一性目的（抓"引语挂错段号"）不受影响。
    def _unanchored(rates: dict[str, float] | None = None) -> dict:
        rates = rates or {}
        best = max(rates, key=lambda kk: rates[kk]) if rates else None
        best_rate = round(rates[best], 3) if best is not None else None
        # 在语料里确实存在（命中率 ≥0.6）就把段号报出来供人工补标；否则置 None，不假装有命中。
        return {"verdict": "UNANCHORED",
                "hit_at": best if (best_rate is not None and best_rate >= 0.6) else None,
                "spans": sorted(rates), "candidates": _top(rates),
                "words": len(qw), "ngram": k or 0, "rate": best_rate}

    if k is None:
        return _unanchored() if target is None else {
            "verdict": "TOO_SHORT", "hit_at": None, "spans": [],
            "candidates": [], "words": len(qw), "ngram": 0}
    qsh = shingles(qw, k)
    if not qsh:
        return _unanchored() if target is None else {
            "verdict": "TOO_SHORT", "hit_at": None, "spans": [],
            "candidates": [], "words": len(qw), "ngram": 0}

    rates: dict[int, float] = {}
    for num, ptext in para_texts.items():
        psh = shingles(norm_words(ptext), k)
        if not psh:
            continue
        hit = sum(1 for s in qsh if s in psh)
        if hit:
            rates[num] = hit / len(qsh)

    if target is None:
        return _unanchored(rates)

    if not rates:
        return {"verdict": "NOT_IN_CORPUS", "hit_at": None, "spans": [],
                "candidates": [], "words": len(qw)}

    best = max(rates, key=lambda k: rates[k])
    # 严格门槛：与 verify_quotes 对齐（>=0.6 判命中），避免两个工具口径打架
    if rates[best] >= 0.6:   # noqa: PLR2004 —— 与 verify_quotes 同口径
        # 走到这里 target 必不为 None（target is None 已在上面归 UNANCHORED 提前返回）
        if best == target:
            return {"verdict": "ANCHOR_HIT", "hit_at": best, "spans": [],
                    "candidates": _top(rates), "words": len(qw), "ngram": k,
                    "rate": round(rates[best], 3)}
        # 引语确实存在，但不在声明的那一段 → 段号挂错。
        # **这里绝不能因为"引语存在"就放行**——那正是本命令存在的理由。
        return {"verdict": "SPAN_HIT", "hit_at": best, "spans": sorted(rates),
                "candidates": _top(rates), "words": len(qw), "ngram": k,
                "rate": round(rates[best], 3)}
    if rates.get(target, 0.0) >= 0.4:
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


def verify_file(claim_file: Path, corpora: dict[str, dict[int, str] | Corpus],
                n: int = 5, require_anchor: bool = True) -> dict:
    """核验一份卡片/候选文件里的所有带定位标记的引语。

    支持四类定位标记：§N / [时间戳] / 【第N段】 / 篇-章号（如 一之三）。
    没标注的属于"不可定位"，单列出来（与 verify-quotes / lint-quotes「无出处即跳过」同口径）。
    这与 CONSTRAINTS C10「引用数 ≠ 核验数」同一个纪律：
    **必须把"引语总数"与"锚定核验数"都报出来，并对账。**
    """
    # #71：入参可能是老测试直接传的 plain dict（{int:str}）——包一层 Corpus 保证接口一致。
    corpora = {s: (c if isinstance(c, Corpus) else Corpus(c)) for s, c in corpora.items()}
    text = claim_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    results = []
    unresolved: list[dict] = []
    seen_quotes = 0
    citations_seen = 0      # 卡片里出现的 §N / [时间戳] 标注数（#56 空集守卫用）
    noise = 0   # 被引语形状过滤掉的中文正文数
    # #61：抽取层对账（C10）。旧实现把"太短的中文候选"直接混进 noise，
    # 于是**看不出自己漏了多少**——现在单列计数 + 留样本。
    quote_candidates = 0
    skipped_cjk_short = 0
    short_samples: list[dict] = []
    # 短候选的"疑似真引语"判据：**逐字见于语料**。
    # 4~7 字这个区间，"经典引语"（「柔乘剛也」）与"卡片自造短语"（「缺啥补啥」）
    # 用长度**在原理上分不开**——但用"是否存在于语料"能干净分开。
    # 注意：判为"疑似真引语"只**单列提示**，绝不计入失败，也不参与判定——
    # 短词恰好出现在语料里（术语）是常态，据此判失败会制造假阳性。
    corpus_blob = {stem: re.sub(r"\s+", "", "\n".join(p.values()))
                   for stem, p in corpora.items()}

    def _find_in_corpus(q: str) -> dict | None:
        needle = re.sub(r"\s+", "", q.strip().strip("。，；：、！？"))
        if len(needle) < 4:
            return None
        for stem, blob in corpus_blob.items():
            if needle in blob:
                for num, ptext in corpora[stem].items():
                    if needle in re.sub(r"\s+", "", ptext):
                        return {"src": stem, "para": num}
                return {"src": stem, "para": None}
        return None

    default_src = next(iter(corpora)) if corpora else None
    # 上一个显式段号（第N段 / 篇-章号），供「同上」跨块沿用（复审 #1 + #71）。
    last_target: int | None = None

    for lineno, line in enumerate(lines, 1):
        is_block = line.lstrip().startswith(">")
        # 书类引用块的段号信号：出处行写「—— 《书名》第N段」。
        # last_target **不随离开引用块重置**——「—— 同上」就是故意跨块沿用上一个
        # 显式段号（书类卡常写成「第1段 / 同上 / 同上」三连），重置会让它们全部退化成
        # 「未标注段号」而被判 SPAN_HIT。block_target 只在向后看**真的看到**段号信号
        # （第N段 / 篇-章号 / 同上）时才赋值，所以不重置也不会让无出处的块凭空拿到段号。
        if is_block:
            mseg = re.search(r"第(\d+)[段条]", line)
            if mseg:
                last_target = int(mseg.group(1))
        # 一行里可能有多个 §N（并列时间戳），也可能有多个引语
        cits: list[tuple[str | None, int, None]] = []
        for m in CITE_RE.finditer(line):
            stem = _resolve_src(m.group(1), corpora)
            group = [int(m.group(2))]
            # 吃掉并列锚点：§60/§74、§143/§144
            tail = line[m.end():]
            jm = re.match(r"((?:\s*/\s*§\d+)+)", tail)
            if jm:
                group += [int(x) for x in JOIN_RE.findall(jm.group(1))]
            cits += [(stem, g, None) for g in group]
        # 篇-章号定位（如 一之三）：#71。《論語》类卡片用独占一行的篇-章号作细粒度段号。
        # 卡片侧三种形状（见 _verse_locator）：行首标签+引号 / 出处行 —— 标签 / 同行紧邻引号。
        vloc: tuple[str | None, int, str] | None = None
        vl = _verse_locator(line)
        if vl:
            vprefix, vlabel = vl
            vstem = _resolve_src(vprefix, corpora) or default_src
            vc = corpora.get(vstem)
            if not vc:
                unresolved.append({"line": lineno, "src": vstem,
                                   "quote": None,
                                   "reason": "篇-章号来源未在 --corpus 中提供"})
            else:
                vkey = vc.verses.get(vlabel)
                if vkey is None:
                    unresolved.append({"line": lineno, "src": vstem, "label": vlabel,
                                       "quote": None,
                                       "reason": "篇-章号未在语料中提供"})
                else:
                    vloc = (vstem, vkey, vlabel)
                    last_target = vkey
        # 书类/篇-章号引用块：本行是引语但无内联 §N/篇-章号时，向后看同一引用块的下一行取段号。
        # 书类卡常见「> 「引语」」在「> —— 《书》第N段」**之前**，必须向后看。
        block_target: int | None = None
        if is_block and not cits and not vloc:
            # 向后看**同一引用块**的下一行取段号。引用块内的视觉空行（卡片作者常用来给
            # 长引语与出处行之间留白）必须跳过——否则 `> 「引语」` 与 `> —— 篇-章号` 之间
            # 一旦有空行，循环就停在空行上、永远够不到出处行（#71 正例 (b) 复现的死法）。
            # 遇到非块、非空行即停（那是下一个引用块 / 正文，不能再沿用本块的段号）。
            nxt = lineno
            while nxt < len(lines):
                nxt_line = lines[nxt]
                if nxt_line.strip() == "":
                    nxt += 1
                    continue
                if not nxt_line.lstrip().startswith(">"):
                    break
                nm = re.search(r"第(\d+)[段条]", nxt_line)
                if nm:
                    block_target = int(nm.group(1))
                    break
                # 仅认**出处行**（`—— 篇-章号`）形状的段号；不认"下一行自带标签的引语"，
                # 否则会错把那条引语的段号继承给当前无标注引语（#71 回归护栏）。
                vm = _verse_outro(nxt_line)
                if vm:
                    vp, vlbl = vm
                    vs = _resolve_src(vp, corpora) or default_src
                    vcorp = corpora.get(vs)
                    if vcorp and vlbl in vcorp.verses:
                        block_target = vcorp.verses[vlbl]
                        break
                if "同上" in nxt_line and last_target is not None:
                    block_target = last_target
                    break
                nxt += 1
            # 同行「—— 同上」：引语与承接标注在同一行（如 `> 「…」—— 同上`）
            if block_target is None and "同上" in line and last_target is not None:
                block_target = last_target
        if cits or vloc or block_target is not None:
            citations_seen += 1
        # 引语必须"以英文词开头、以英文词收尾"才算引语。
        # 单纯 r'"([^"\n]{12,600})"' 会把两个引号之间的**中文正文**也当成引语
        # （如 `"Give me some evidence for that" ——**同一句式对敌我双方各用一次**。`）。
        # 这类不是引语却进了核验器，产出假阳性——**核验器自己的噪声**。
        def _is_quote(q: str) -> bool:
            q = q.strip()
            if not q:
                return False
            cjk = len(CJK_CHAR_RE.findall(q))
            if cjk >= 8 and cjk >= len(q) * 0.4:
                # 中文（或中英混排）引语按**汉字数**判。
                # 2026-10-09（#61）：旧实现先判 `len(q) < 12` 就丢，而 12 字符是**英文**尺度——
                # 中文 7 个字已是完整命题（「天行健，君子以自強不息」11 字、
                # 「不可為典要，唯變所適」10 字、「窮理盡性以至於命」8 字），
                # 于是最该被核验的经典引语整类进不了核验，还被计入 noise **静默消失**。
                # 实测 zhouyi-yili 卡 25 条候选只认出 9 条（16 条被丢，其中 8 条为 8~11 字）。
                # **这是同一类「用英文假设处理中文」的第 5 例（前四例：#52/#55/#56/#60）。**
                return True
            if re.match(r"[A-Za-z0-9]", q) and re.search(r"[A-Za-z]{2}", q):
                return len(q) >= 12      # ASCII 引语仍用字符下限（约 2 个英文词）
            return False

        # 抽取正则的下限也必须放宽到 4 字符，否则短中文引语**根本进不了候选**，
        # 修了 _is_quote 也白修（两道闸门都卡在同一个英文尺度上）。
        _cands: list[str] = re.findall(r'"([^"\n]{4,600})"', line) \
            + re.findall(r"[「“]([^」”\n]{4,600})[」”]", line)
        quotes = [q for q in _cands if _is_quote(q)]
        quote_candidates += len(_cands)
        # 复审 5（建议）：**带 §N 标注的短候选升级为可核验**。
        # <8 汉字的候选里，「柔乘剛也」「窮理盡性以至於命」这类经典引语与「缺啥补啥」
        # 这类卡片自造短语用长度分不开——但**是否逐字见于语料**能干净分开。
        # 规则（非对称，故意如此）：
        #   * 逐字见于语料 + 同行有 §N  → 进入核验；**命中即计入核验数**（正向证据）。
        #   * 不命中 → 记为 short_misplaced **只报警不判失败**：≤7 字的短语在多引用行上
        #     归属本就含糊，硬判会制造假阳性（本项目「假阳性比漏报更坏」的纪律）。
        short_cited: set[str] = set()
        if cits:
            for q in _cands:
                if q in quotes or q in short_cited:
                    continue
                if not (4 <= len(CJK_CHAR_RE.findall(q)) < 8):
                    continue
                if _find_in_corpus(q):
                    short_cited.add(q)
        # #71：显式以**篇-章号**定位（vloc / block_target 来自篇-章号或「同上」）的短引语，
        # 作者已明确给出出处，必须与 §N 同口径进入核验——且计入硬失败（is_short=False），
        # 因为"标注了段号"即意味可定位、可核对（这正是「标注了就要核验」的纪律）。
        # 例：論語「巧言令色，鮮矣仁。」仅 7 汉字，若按通用短候选阈值会被静默丢弃，
        # 于是这条被明确锚定到「一之三」的引语根本没被核验——典型的"看起来没事"。
        # （仅 verse 定位触发；书类【第N段】段落的引语天然较长，不受影响。）
        located_short: set[str] = set()
        if vloc or (block_target is not None):
            for q in _cands:
                if q in quotes or q in short_cited or q in located_short:
                    continue
                if not (4 <= len(CJK_CHAR_RE.findall(q)) < 8):
                    continue
                if _find_in_corpus(q):
                    located_short.add(q)
        quotes = quotes + sorted(short_cited) + sorted(located_short)
        # 抽取层对账（C10）：候选 = 认出 + 噪声 + 因太短跳过的中文候选。
        # 旧实现把"太短的中文候选"混进 noise，于是**看不见自己漏了什么**。
        skipped_here = [q for q in _cands
                        if q not in quotes and len(CJK_CHAR_RE.findall(q)) >= 4]
        skipped_cjk_short += len(skipped_here)
        for q in skipped_here:
            loc = _find_in_corpus(q)
            entry = {"line": lineno, "quote": q.strip()[:60], "in_corpus": loc}
            if loc:
                # 短候选**逐字见于语料**但同行没有 §N（有 §N 的已升级为可核验）→ 提示补段号
                entry["status"] = "unattributed" if not cits else "not_promoted"
            short_samples.append(entry)
        noise += len(_cands) - len(quotes) - len(skipped_here)
        for q in quotes:
            seen_quotes += 1
            is_short = q in short_cited
            # 该行所有段号里，任一命中即算锚定成功（并列锚点是合法用法）
            best_local = None
            # 书类块无内联 §N/篇-章号时，用块携带的段号（向后看取到的）作为目标
            if cits:
                targets = cits
            elif vloc:
                targets = [vloc]
            elif block_target is not None:
                targets = [(default_src, block_target, None)]
            else:
                targets = [(default_src, None, None)]
            # 每个标注 (来源, 段号, 标签) 各查一次：**段号只在它自己的来源内解释**
            for stem, target, label in targets:
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
                r["claimed_label"] = label
                if r.get("hit_at") is not None:
                    r["found_label"] = para.labels.get(r["hit_at"])
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
            r["anchored"] = bool(cits) or bool(vloc) or block_target is not None
            r["short"] = is_short      # 短引语（<8 汉字但逐字见于语料）——见下方非对称规则
            r.setdefault("claimed_label", None)
            r.setdefault("found_label", None)
            results.append(r)

    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1

    # 只有 ANCHOR_HIT 算通过。SPAN_HIT = 引语在别的段里 = 挂错段号 = 失败。
    # （旧版把 SPAN_HIT 也算过，那等于给"段号写错"开后门。）
    anchored = sum(1 for r in results if r["verdict"] == "ANCHOR_HIT")
    partial = [r for r in results if r["verdict"] == "ANCHOR_PARTIAL"]
    # 复审 #1：失败只统计**带段号标注**的失配。无 §N 的引语归 UNANCHORED（不可定位），
    # 单列出来、如实计数，但不判失败——它不是"挂错段号"，是"没段号可锚"。
    # 复审 5（建议）：**短引语不参与硬失败**（非对称）——命中已计入 anchored（正向证据），
    # 失配只进 short_misplaced 报警。理由：≤7 字的短语在多引用行上归属含糊，硬判会假阳性。
    miss = [r for r in results
            if not r["short"] and r["anchored"]
            and r["verdict"] in ("ANCHOR_MISS", "NOT_IN_CORPUS", "SPAN_HIT")]
    short_hits = [r for r in results if r["short"] and r["verdict"] == "ANCHOR_HIT"]
    short_bad = [r for r in results
                 if r["short"] and r["verdict"] in ("ANCHOR_MISS", "NOT_IN_CORPUS", "SPAN_HIT")]
    unanchored_list = [r for r in results if r["verdict"] == "UNANCHORED"]
    unanchored = len(unanchored_list)
    # #71：有"可定位标记"的引语数（§N / 【第N段】 / 篇-章号 / [时间戳] 任一命中）。
    # 这是判定 UNVERIFIED 的账本：有引语但 0 条可核验 → 不是通过，是"没核验"。
    checked = sum(1 for r in results if r.get("anchored"))

    return {
        "file": str(claim_file),
        "quotes_seen": seen_quotes,
        "citations_seen": citations_seen,
        # 2026-10-07（#56）：**空集不得判 PASS**。
        # 卡片里明明有 §N/[时间戳] 标注，却一条引语都没抽出来 —— 这不是"没问题"，
        # 是**核验器没干活**。旧版在这种情况下打印「引语 0 条」+「✅ 判定 PASS」，
        # 给了完全虚假的安心（中文卡片 100% 命中这个假绿）。
        # 与 v1.3 的「空集假绿」是同一个纪律：空集不能算通过。
        "vacuous": seen_quotes == 0 and citations_seen > 0,
        "anchored_checked": anchored,
        "tally": tally,
        "unanchored": unanchored,
        # 无标注引语的明细（不判失败，但必须看得见——静默的"没检查"比报错更难查）
        "unanchored_quotes": [{"line": r["line"], "quote": r["quote"],
                               "in_corpus_at": r.get("hit_at"),
                               "best_rate": r.get("rate")} for r in unanchored_list],
        # 复审 5（建议）：短引语（<8 汉字、逐字见于语料、同行带 §N）已**升级为可核验**。
        # 命中计入 anchored；失配单列在此，**只报警不判失败**（理由见抽取段注释）。
        "short_quotes": {
            "verified": len(short_hits),
            "misplaced": [{"line": r["line"], "claimed_at": r.get("claimed_at"),
                           "verdict": r["verdict"], "found_at": r.get("hit_at"),
                           "quote": r["quote"]} for r in short_bad],
        },
        "unresolved_sources": unresolved,
        "noise_filtered": noise,
        # #61 抽取层对账：候选 = 认出（seen）+ 噪声 + 因太短跳过的中文候选。
        # 这三项必须严格加和等于 candidates（`balanced` 为机器可判的自检位）。
        "quote_candidates": quote_candidates,
        "skipped_cjk_short": skipped_cjk_short,
        "skipped_cjk_short_samples": short_samples[:20],
        # 短候选里**逐字见于语料**的那些：多半是真经典引语（只是汉字数 <8 被判成短语）。
        # 只提示、不判失败——但要让人看见，否则就是又一个静默盲区。
        "short_but_in_corpus": [s for s in short_samples if s.get("in_corpus")][:20],
        "extraction_reconciliation": {
            "candidates": quote_candidates,
            "quotes_seen": seen_quotes,
            "noise_filtered": noise,
            "skipped_cjk_short": skipped_cjk_short,
            "balanced": quote_candidates == seen_quotes + noise + skipped_cjk_short,
        },
        # 对账：见到的引语 = 各 verdict 之和（分区必须严丝合缝，漏一项就是账不平）
        "reconciliation": {
            "seen": seen_quotes,
            "anchor_hit": anchored,
            "unanchored": unanchored,
            "anchor_partial": sum(1 for r in results if r["verdict"] == "ANCHOR_PARTIAL"),
            "span_hit": sum(1 for r in results if r["verdict"] == "SPAN_HIT"),
            "anchor_miss": sum(1 for r in results if r["verdict"] == "ANCHOR_MISS"),
            "not_in_corpus": sum(1 for r in results if r["verdict"] == "NOT_IN_CORPUS"),
            "too_short": sum(1 for r in results if r["verdict"] == "TOO_SHORT"),
        },
        "failures": [
            {"line": r["line"], "claimed_at": r["claimed_at"],
             "claimed_src": r.get("claimed_src"), "verdict": r["verdict"],
             "claimed_label": r.get("claimed_label"), "found_label": r.get("found_label"),
             "found_at": r.get("hit_at"), "rate": r.get("rate"),
             "quote": r["quote"], "candidates": r.get("candidates", [])}
            for r in miss
        ],
        # 来源解析失败也算 FAIL：无法核验 ≠ 通过
        "partial": [{"line": r["line"], "claimed_at": r["claimed_at"],
                     "rate": r.get("rate"), "quote": r["quote"]} for r in partial],
        # PARTIAL 不判FAIL：它已落在正确段号内，只是被字幕分段切开。
        # 但必须报出来让人看见——**静默的"差不多对"比报错更难查**。
        # #71：三态收口——FAIL（有挂错/来源缺失）/ PASS（有核验且全过）/ UNVERIFIED（有引语但 0 条可核验）。
        # 0 核查的"软 PASS"是假绿（缺陷 #71）：不能因为"没核验出错误"就印 ✅，
        # 那等于默认所有人都没标注段号。UNVERIFIED ≠ PASS，CLI 会 die。
        "checked": checked,
        "verdict": ("FAIL" if (miss or unresolved)
                    else "UNVERIFIED" if (seen_quotes > 0 and checked == 0)
                    else "PASS"),
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


def load_corpora(paths: list[Path]) -> dict[str, Corpus]:
    return {p.stem: index_corpus(p.read_text(encoding="utf-8", errors="replace"))
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
        "verdict": ("FAIL" if any(f for r in reports for f in r["failures"])
                    else "UNVERIFIED" if any(r["verdict"] == "UNVERIFIED" for r in reports)
                    else "PASS"),
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
    return 2 if merged["verdict"] != "PASS" else 0


if __name__ == "__main__":
    sys.exit(main())
