#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmarks/token-savings/measure.py — 长书token 节省实测（P0-3）。

**为什么要有这个脚本**：README曾写"分块+索引让长书只读 1/x 的 token"，
但那是**估计**，不是测量。本脚本把几种读法在同一本书上各跑一遍，
用 tiktoken 真计量，给出**区间 + 方法 + 不可外推声明**。

## 被测的四种读法

| 模式 | 模拟的真实做法 | 读多少 |
|---|---|---|
| `whole` | 整本灌进上下文 | 全书 100% |
| `window` | 分块后按关键词定位，读**全部命中块** | 命中块 |
| `window_ctx` | 同上 + 每个命中块前后各 1 块当上下文 | 命中块 + 去重后的邻块 |
| `index_then_read` | 只读索引（每块讲什么），再定点读**最相关的 1 块** | 索引 + 1 块 |

**「省」的是什么**：省的是**每次必须过一遍的文字**，不是"书变小了"。
分块不减少书的内容，只减少通读量。

## 三条不能省的诚实

1. **不给单点数字，给区间。** 节省倍数几乎完全由「关键词有多具体」决定：
   宽关键词（命中大半个书）≈ 不省，窄关键词（命中一个章节）才省几十倍。
   只报最好看的那一个数字就是在自欺。`--sweep` 会跑多组关键词并把区间一起报出来。
2. **计量单元必须是 `chunks.jsonl` 里的 `ck-*` 块** —— 那才是 `index --grep`
   真正返回的东西。（首版读的是 `document.json` 的 elements，字段名也写错了，
   得数全是错的；这类"量具本身错了"的错比不测更坏。）
3. **没装 tiktoken 就明确报"未运行"并以退出码 2 结束**，绝不用字数估算冒充
   token 数——那正是这份报告要消除的东西。

## 用法

    # 单组关键词
    python3 benchmarks/token-savings/measure.py --corpus book.md --keywords 月令 印綬大运
    # 扫描多组关键词，给出区间（推荐）
    python3 benchmarks/token-savings/measure.py --corpus book.md --sweep --out report.md
    # 自动从索引标题里挑关键词做扫描
    python3 benchmarks/token-savings/measure.py --corpus book.md --sweep auto

计量需要 `tiktoken`：`python3 -m venv <dir> && <dir>/bin/pip install tiktoken`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TD = ROOT / "scripts" / "td.py"

# 自动扫描用的关键词组：从「宽」到「窄」各一组，逼出区间的两端。
# 宽组刻意选高频词——**它会得出"几乎不省"的结果，那正是要如实报出来的那一端**。
SWEEP_SETS: list[list[str]] = [
    ["月令", "印綬", "大运"],
    ["大运"],
    ["论大运"],
    ["五行元理消息"],
]

# 按语料名指定扫描组。**必须显式指定、不许自动挑词**：
# 挑词的人会不自觉挑一个命中又少又准的词，把倍数刷高（这正是本脚本
# 一开始想消灭的那类自欺）。短书/逐字稿没有章节标题，只能这样给。
BOOK_KEYWORDS: dict[str, list[list[str]]] = {
    "arj7oStGLkU.en.transcript.md": [
        ["procrastination", "deadline", "work", "regret"],
        ["procrastination"],
        ["deadline"],
    ],
    "src-09-xiaoxiang.md": [
        ["君子", "大人", "凶", "吉", "勿", "宜", "厉"],
        ["大人"],
        ["宜"],
    ],
}

# CAVEATS 里要引用实际测了几本书，所以做成函数（首版写成常量，
# 报告里就固定说"只测了1 本书"——**报告模板说谎**比数字错更难发现）。
def _caveats(nbooks: int) -> list[str]:
    return [
        f"只测了 {nbooks} 本书（见各书 sha256），换书会变——"
        f"**区间下端来自短书/宽词，不是所有书都能省到那么多**",
        "节省倍数**主要由两件事决定**：书有多长、关键词有多具体。"
        "书短或词宽时几乎不省（本次实测下端就在 1.0× 附近）。单点数字没有意义",
        "window 类模式假设关键词能定位到正确的块。关键词选不准时，省下的 token "
        "会以「读错块」的形式还回去——**省 token 与读对内容是两件事**",
        "index_then_read 只读了 1 块，覆盖面最窄；它最省，但最可能不够用",
        "只算文本 token，不含工具调用、Agent 系统提示、图片 / 音频转写",
        "tiktoken 是 OpenAI 的编码（cl100k_base）；别的厂商绝对值不同、比例关系大体成立",
    ]


def get_encoder():
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:      # noqa: BLE001  离线时可能拉不到 BPE 文件
        return None


def chunk_corpus(src: Path, sidecar: Path) -> tuple[list[dict], dict]:
    """跑真实的 `td.py chunk` —— 不自己实现分块，否则测的不是这个工具。

    计量单元取 `chunks.jsonl` 的 **ck-\\* 块**（`index --grep` 真正返回的东西）。
    """
    proc = subprocess.run(
        [sys.executable, str(TD), "chunk", str(src), "--sidecar", str(sidecar)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"chunk 失败：\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}")
    rows = []
    for line in (sidecar / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        # heading_path 在 chunks.jsonl 里已经是 list；字符串形态也遇到过，先归一。
        hp = c.get("heading_path")
        if isinstance(hp, str):
            try:
                hp = json.loads(hp)
            except (ValueError, TypeError):
                hp = [hp]
        rows.append({
            "id": c["chunk_id"],
            "title": " / ".join(hp or []) or "(root)",
            "text": c.get("text") or "",
            "chars": int(c.get("chars") or 0),
        })
    index_meta = json.loads((sidecar / "index.json").read_text(encoding="utf-8"))
    return rows, index_meta


def measure(rows: list[dict], ntok, kw: list[str], whole: int) -> dict:
    """给定一组关键词，算出各读法的 token 与相对整本的倍数。

    **一个关键词都没命中时返回 `hits_none`**：0/0 得不出倍数，
    硬算会得到 `None` 或0，混进区间里就是一个假的端点。
    """
    def hits(r: dict) -> int:
        return sum(1 for k in kw if k and k in r["text"])

    hit_rows = [r for r in rows if hits(r) > 0]
    if not hit_rows:
        return {"keywords": kw, "hit_blocks": 0, "total_blocks": len(rows),
                "degenerate_hit_blocks": [], "hits_none": True,
                "best_block": None, "tokens": {"whole": whole},
                "saving_vs_whole": {}}
    m_window = sum(r["tokens"] for r in hit_rows)

    # **退化命中检测**：若**全部**命中块都小到只剩标题（<200 token），倍数会飙到四位数。
    # 那不是"省得多"，是**关键词只命中了目录行、没命中正文**。
    # 判据必须是「全部」而不是「存在」——一本书里总有几个只含标题的块，
    # 若按「存在」判定，会把「宽关键词命中 49/80 块」这种最有价值的样本
    # 全部标成退化（2026-10-10 首版就犯这个错，反而把最诚实的那一端藏了）。
    tiny = [r["id"] for r in hit_rows if r["tokens"] < 200]
    degenerate = tiny if (hit_rows and len(tiny) == len(hit_rows)) else []

    # 邻块必须**去重**：命中块本身已计入，相邻的命中块不能重复加
    # （首版没去重，算出"窗口比整本还贵"的荒谬结论）。
    pos = {r["id"]: i for i, r in enumerate(rows)}
    hit_ids = {r["id"] for r in hit_rows}
    ctx_ids = set()
    for r in hit_rows:
        i = pos[r["id"]]
        for j in (i - 1, i + 1):
            if 0 <= j < len(rows) and rows[j]["id"] not in hit_ids:
                ctx_ids.add(rows[j]["id"])
    m_ctx = m_window + sum(r["tokens"] for r in rows if r["id"] in ctx_ids)

    idx_lines = [f"{r['id']}  {r['title']}  ({r['chars']}c, 命中 {hits(r)})"
                 for r in rows]
    m_index_list = ntok("\n".join(idx_lines))
    best = max(hit_rows, key=lambda r: (hits(r), -r["tokens"])) if hit_rows else None
    m_index = m_index_list + (best["tokens"] if best else 0)

    def ratio(x: int):
        return round(whole / x, 2) if x else None

    return {
        "keywords": kw,
        "hit_blocks": len(hit_rows),
        "total_blocks": len(rows),
        "degenerate_hit_blocks": degenerate,
        "hits_none": False,
        # 退化样本的倍数会失真，标成 null 而不是照报一个四位数
        "best_block": ({"id": best["id"], "title": best["title"],
                        "tokens": best["tokens"], "hits": hits(best)}
                       if best else None),
        "tokens": {
            "whole": whole,
            "window_hit_only": m_window,
            "window_with_neighbours": m_ctx,
            "index_list_only": m_index_list,
            "index_then_read_one": m_index,
        },
        "saving_vs_whole": {
            "window_hit_only": None if degenerate else ratio(m_window),
            "window_with_neighbours": None if degenerate else ratio(m_ctx),
            "index_then_read_one": ratio(m_index),
        },
    }


def auto_keywords(rows: list[dict], index_meta: dict, k: int = 4) -> list[list[str]]:
    """从真实章节标题里挑关键词——**不手挑**，免得挑出一个好看的数字。

    三道筛子，每道都来自实测踩到的坑：
    1. **在正文里真的出现过** —— 拿一个哪块都没命中的词去测，得到的是
       0/0 的假象，不是"这本书省不了"。
    2. **长度 ≥ 2 且不是文件名** —— 逐字稿的标题是
       `逐字稿 · arj7oStGLkU.en`，拿这种"词"当关键词，命中的其实是 frontmatter
       里的来源声明，读回来的是元数据不是正文（2026-10-10 实测）。
    3. 至少留下一组；一组都留不下就**如实返回空**，由调用方明确报"无法自动取词"，
       而不是塞一个必然命中 0 块的短词充数。
    """
    heads = [h for h in (index_meta.get("headings") or {}) if h and h != "(root)"]
    cands = []
    for h in heads:
        seg = h.split("/")[-1].strip()
        if len(seg) < 2 or _looks_like_filename(seg):
            continue
        if not any(seg in r["text"] for r in rows):
            continue
        cands.append([seg])
    return cands[:k]


def _looks_like_filename(s: str) -> bool:
    """带扩展名/路径分隔/版本号的，不是章节标题而是文件名或来源声明。"""
    return ("." in s or "/" in s or "·" in s
            or re.search(r"\d{3,}", s) is not None)


def render(rep: dict) -> str:
    L = []
    L.append("# 长书 token 节省实测\n")
    L.append("> 由 `benchmarks/token-savings/measure.py` 生成。方法与脚本同源，"
             "**每个数字都可复跑**。\n")
    for b in rep["books"]:
        L.append(f"## 《{b['label']}》\n")
        L.append("| 项 | 值 |")
        L.append("|---|---|")
        L.append(f"| sha256 | `{b['corpus_sha256']}` |")
        L.append(f"| 全书字符 | {b['corpus_chars']:,} |")
        L.append(f"| 分块数（`index --grep` 的返回单元） | {b['blocks']} |")
        L.append("")
        if b.get("no_keywords"):
            L.append("> **未测**：这本书的章节标题里取不到「在正文里出现过、"
                     "且不是文件名」的关键词，所以**没有数字**。"
                     "硬塞一个必然命中 0 块的词只会得到一张全 0 的假表"
                     "（看着像「这本书省不了」，其实是词不对）。"
                     "手动给词重来："
                     f"`--corpus {b['label']} --keywords <词1> <词2>`\n")
            continue
        L.append("| 关键词 | 命中块 | 整本 | 窗口(命中块) | 窗口(+邻块) | 索引+读1块 |")
        L.append("|---|---:|---:|---:|---:|---:|")
        for r in b["runs"]:
            kws = "、".join(r["keywords"])
            if r.get("hits_none"):
                L.append(f"| {kws} | 0/{r['total_blocks']} | — | — | — | — |")
                continue
            t, s = r["tokens"], r["saving_vs_whole"]
            if r.get("degenerate_hit_blocks"):
                kws += " ⚠️"
            f = lambda x: "—" if x is None else f"{x:,}"        # noqa: E731
            g = lambda x: "退化" if x is None else f"{x}×"      # noqa: E731
            L.append(f"| {kws} | {r['hit_blocks']}/{r['total_blocks']} | "
                     f"{f(t['whole'])} | {f(t['window_hit_only'])} / {g(s['window_hit_only'])} | "
                     f"{f(t['window_with_neighbours'])} / {g(s['window_with_neighbours'])} | "
                     f"{f(t['index_then_read_one'])} / **{g(s['index_then_read_one'])}** |")
        L.append("")
        deg = [r for r in b["runs"] if r.get("degenerate_hit_blocks")]
        none_ = [r for r in b["runs"] if r.get("hits_none")]
        if deg:
            L.append("> ⚠️ 标 ⚠️ 的行是**退化样本**：关键词只命中了只有标题、"
                     "没有正文的块（chunk "
                     + "、".join(deg[0]["degenerate_hit_blocks"]) + "）。"
                     "照算会得到四位数倍的「节省」，但那是**没读到正文**，不是省。"
                     "这类样本的窗口倍数置为「退化」，不计入区间。")
        if none_:
            L.append("> 命中 0 块的关键词组不给倍数（0/0 得不出的东西不能写成数字），"
                     "已如实留空。")
        L.append("")
        _range_block(L, b)
    _overall(L, rep)
    L.append("## 不可外推声明\n")
    for i, c in enumerate(rep.get('caveats') or _caveats(len(rep['books'])), 1):
        L.append(f"{i}. {c}")
    L.append("")
    L.append("## 复跑\n")
    L.append("```bash")
    L.append("python3 -m venv <dir> && <dir>/bin/pip install tiktoken")
    # 单本 + 自动取词：给个只用 --sweep-auto 的路径时，keywords 必为空，
    # 不能退回"扫描多组"（扫出来的词对这本书未必合适）
    L.append("<dir>/bin/python benchmarks/token-savings/measure.py \\")
    L.append("  --corpus <书1> --corpus <书2> --sweep")
    L.append("# 换书后内置词可能全不命中；脚本会自动从该书章节标题取词，")
    L.append("# 也可显式指定：--sweep-auto")
    L.append("```")
    L.append("")
    L.append("没装 `tiktoken` 时脚本**明确报「未运行」并以退出码 2 结束**，"
             "不会用字数估算冒充 token 数。\n")
    return "\n".join(L)


def _range_block(L: list, b: dict) -> None:
    """把一本书的区间写出来，并点明**最诚实的那一端**（几乎没有节省的那次）。"""
    runs = [r for r in b["runs"] if not r.get("hits_none")]
    L.append("**本书记法能省多少**\n")
    if not runs:
        L.append("- 无有效样本\n")
        return
    for key, label in (("window_hit_only", "窗口（只读命中块）"),
                       ("window_with_neighbours", "窗口（+邻块，现实口径）"),
                       ("index_then_read_one", "索引 → 定点读 1 块")):
        vals = [r["saving_vs_whole"][key] for r in runs
                if r["saving_vs_whole"].get(key)]
        if not vals:
            continue
        #只有一个样本时**不写"区间"**——把同一个数写成"1/x ～ 1/x"，
        # 会让读者以为还有别的样本。宁可写"单样本"。
        if len(vals) == 1:
            L.append(f"- **{label}**：单样本，整本的 **{vals[0]}×**"
                     f"（共 {len(runs)} 组关键词，只这组有有效数字）")
        else:
            L.append(f"- **{label}**：整本的 **1/{max(vals):.2f} ～ 1/{min(vals):.2f}**"
                     f"（{min(vals):.2f}× ～ {max(vals):.2f}×）")
    L.append("")
    wc = [(r, r["saving_vs_whole"]["window_with_neighbours"]) for r in runs
          if r["saving_vs_whole"].get("window_with_neighbours")]
    if len(wc) == 1:
        r, v = wc[0]
        L.append(f"- 本书只测到 1 组有效样本（{'、'.join(r['keywords'])}，命中 "
                 f"{r['hit_blocks']}/{r['total_blocks']} 块）：**{v}×**。"
                 f"**单样本不足以说明这本书的区间**，请用 `--keywords` 多给几组词。")
    elif wc:
        worst = min(wc, key=lambda x: x[1])
        bestr = max(wc, key=lambda x: x[1])
        L.append(f"- 最诚实的那一端（{'、'.join(worst[0]['keywords'])}，命中 "
                 f"{worst[0]['hit_blocks']}/{worst[0]['total_blocks']} 块）："
                 f"**只省 {worst[1]}×**。关键词一宽，「检索」就退化成「通读」"
                 f"——**这是分块的真实上限，不是意外**。")
        L.append(f"- 最好的一端（{'、'.join(bestr[0]['keywords'])}，命中 "
                 f"{bestr[0]['hit_blocks']}/{bestr[0]['total_blocks']} 块）：{bestr[1]}×。")
    L.append("")


def _overall(L: list, rep: dict) -> None:
    L.append("## 结论区间（跨书）\n")
    allv = [r["saving_vs_whole"]["window_with_neighbours"]
            for b in rep["books"] for r in b["runs"]
            if r["saving_vs_whole"].get("window_with_neighbours")]
    allw = [r["saving_vs_whole"]["window_hit_only"]
            for b in rep["books"] for r in b["runs"]
            if r["saving_vs_whole"].get("window_hit_only")]
    alli = [r["saving_vs_whole"]["index_then_read_one"]
            for b in rep["books"] for r in b["runs"]
            if r["saving_vs_whole"].get("index_then_read_one")]
    if allw:
        L.append(f"- **读全部命中块**：整本的 **1/{min(allw):.2f} ～ 1/{max(allw):.2f}**")
    if allv:
        L.append(f"- **命中块 + 邻块（现实口径）**：整本的 "
                 f"**1/{max(allv):.2f} ～ 1/{min(allv):.2f}**")
    if alli:
        L.append(f"- **索引 → 定点读 1 块**：整本的 "
                 f"**1/{max(alli):.2f} ～ 1/{min(alli):.2f}**")
    L.append("")
    L.append("**这些区间的下端不是噪声，是结论**：书越短、关键词越宽，"
             "分块越省不下东西——**短书上分块几乎没有收益**"
             "（下端那些1.0× 附近的样本就是这种情况）。"
             "所以「用分块处理长书」这句话的适用条件是"
             "**书足够长 ∧ 你知道自己在找什么**，两条缺一不可。\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="长书 token 节省实测")
    ap.add_argument("--corpus", required=True, nargs="+", action="extend",
                    help="要测的语料（可重复给或一次给多本；报告会逐本给区间）")
    ap.add_argument("--keywords", nargs="+", default=None,
                    help="单组关键词（仅单本时可用）；不给则扫描多组")
    # --sweep 用store_const + 单独一个 --sweep-auto 开关，不要 nargs="?"：
    # `nargs='?'` 的可选值会把后面的 --corpus 吃掉，且**重复 --corpus 时
    # argparse默认「后者覆盖前者」**——2026-10-10 实测`--corpus A --corpus B`
    # 只剩 B，报告里就少了一本书却毫无报错。action="extend" 修掉后者。
    ap.add_argument("--sweep", action="store_true",
                    help="扫描多组关键词（默认组；全不命中时自动退回auto）")
    ap.add_argument("--sweep-auto", action="store_true",
                    help="从这本书自己的章节标题里取关键词")
    ap.add_argument("--out", default="", help="把结果写成 markdown 报告")
    args = ap.parse_args()

    enc = get_encoder()
    if enc is None:
        print("⚠️ 未运行：需要 tiktoken。装法："
              "  python3 -m venv <dir> && <dir>/bin/pip install tiktoken")
        print("   没有它，本脚本**不会**给出任何 token 数字"
              "（凭字数猜一个数正是这份报告要消除的东西）。")
        return 2
    if args.keywords and len(args.corpus) > 1:
        print("指定 --keywords 时只能测一本（多本共用一组词没有可比性）",
              file=sys.stderr)
        return 1

    def ntok(text: str) -> int:
        return len(enc.encode(text, disallowed_special=())) if text else 0

    def label_of(p: Path) -> str:
        # 报告里不写本机绝对路径（那是作者机器的路径，进公开仓库毫无意义）。
        try:
            return str(p.relative_to(ROOT.parent))
        except ValueError:
            return p.name

    books = []
    for spec in args.corpus:
        src = Path(spec).resolve()
        if not src.exists():
            print(f"找不到语料：{src}", file=sys.stderr)
            return 1
        label = label_of(src)
        raw = src.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            rows, index_meta = chunk_corpus(src, Path(d) / "side")
        rows = [r for r in rows if r["text"].strip()]
        if not rows:
            print(f"❌ {src.name} 分块后没有正文块——不产出任何数字（空集假绿）",
                  file=sys.stderr)
            return 1
        for r in rows:
            r["tokens"] = ntok(r["text"])
        whole = sum(r["tokens"] for r in rows)

        if args.sweep_auto:
            sets = auto_keywords(rows, index_meta)
        elif args.sweep or not args.keywords:
            sets = list(SWEEP_SETS)
            # ① 语料有登记的关键词组就用它（短书/逐字稿没有章节标题）
            for name, groups in BOOK_KEYWORDS.items():
                if name in src.name:
                    sets = list(groups)
                    break
            # ② 内置组是**为《渊海子平》选的词**。换一本书后它们可能一个都命不中
            #    ——那会得到一张全是"0 块"的表，看着像"这本书省不了"，其实是词不对。
            if not any(any(k in r["text"] for r in rows) for s in sets for k in s):
                sets = auto_keywords(rows, index_meta)
        else:
            sets = [args.keywords]
        if not sets:
            # 取不到能命中的关键词 → 这一本**如实报"无法自动取词"**，
            # 塞一个必然命中 0 块的短词只会得到一张全 0 的假表。
            books.append({
                "label": label_of(src), "corpus": str(src),
                "corpus_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "corpus_chars": len(raw), "blocks": len(rows),
                "runs": [], "no_keywords": True,
            })
            continue

        try:
            label = str(src.relative_to(ROOT.parent))
        except ValueError:
            label = src.name
        books.append({
            "label": label,
            "corpus": str(src),
            "corpus_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "corpus_chars": len(raw),
            "blocks": len(rows),
            "runs": [measure(rows, ntok, kw, whole) for kw in sets],
        })

    rep = {"books": books, "caveats": _caveats(len(books))}
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(render(rep), encoding="utf-8")
        print(f"\n报告已写入 {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())