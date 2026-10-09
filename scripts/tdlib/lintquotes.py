# -*- coding: utf-8 -*-
"""tdlib.lintquotes — 引语体检器（lint-quotes）：在正式核验之前，先把**可疑引语**标出来。

## 定位（复审 P1：把 guoxue 现场工具产品化）

`verify-quotes` / `anchor` 是**核验**：逐字去语料里找，找不到就判失败——但它们只给
"❌ 全篇语料中均未找到"这种**结论**，不告诉你**为什么**。guoxue 做产物时另有一套
"体检"小工具先扫一遍，把可疑之处连原因一起标出来。本模块内置其中最常用的三条：

  1. **简繁不一致**（glyph）：卡片写「将孰有能」，语料是繁体「將孰有能」→ 核验必然失败。
     本体检器直接告出差异字形对（将→將），而不是丢一句"找不到"。
  2. **引语含省略号**（ellipsis）：引语里出现 `…` / `...` → 它**不是逐字原文**，
     任何段落级核验都无法确认；要么补全，要么明确标注为节引。
  3. **归属可疑**（authorship）：一小段引号文本在语料里根本不存在，且含
     「我 / 你」+「还是 / 要不要」这类**作者行文特征** → 疑似把作者自己的举例
     当成来源引语（真实样本卡 `five-affairs` 行 91「该选 A 还是 B，我两边都说得通」即此）。

## 与核验的分工（别搞混）

| 工具 | 回答的问题 | 判定 |
|---|---|---|
| `verify-quotes` | 这条引语**在语料里存在吗** | 存在即过 |
| `anchor` | 它在**它声明的那一段**里吗 | 段号对才过 |
| `lint-quotes` | 这条引语**看起来正常吗** | **提示器**：glyph 确证判失败；ellipsis/authorship 只提示 |

**纪律**：glyph 只在**真的找到了近似匹配**时才报（纯粹找不到的交给 verify-quotes，本器不越界），
所以不会对"编造引语"乱开炮；ellipsis / authorship 是启发式，一律只 `warn`，不当硬失败。

字形表的覆盖是**有边界的**（见 `_S2T_LIST`，人工整理的常用对）。表没覆盖到的简繁对，
会走"最相近语料句 + 逐字差异"兜底（近似度阈值 0.80，与核验器同一套保守口径），仍能报出
差异字形对，只是标注为"疑似用字不一致"，不硬说是简繁。
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

QUOTE_PATTERNS = [re.compile(r"「([^」]{8,400})」", re.S),
                  re.compile(r'"([^"\n]{8,400})"')]
META_TAGS = ("归属拆分", "**归属**", "归属：", "归属标注", "措辞修正", "口径统一", "更正记录")
# 作者举例框：卡片常在这类小节里用引号列出"用户会怎么说"的示范句——那是作者行文，
# 不是来源引语。把它们与元描述框同等跳过（否则 authorship 检查会误报，假阳性更坏）。
AUTHOR_FRAME = ("语言信号", "用户会怎么说", "触发情境")
ELLIPSIS_RE = re.compile(r"…|\.\.\.|⋯|。。。")
# 作者行文特征：必须同时出现人称代词与选择/假设词，才判"疑似作者举例"（降低误报）
_AUTHOR_PRON = re.compile(r"[我咱]|你")
_AUTHOR_CHOICE = re.compile(r"还是|要不要|要么|如果|假如")

# 简化字 → 繁体字（人工整理的常用对；每条必须是 2 个字，构建时断言）
_S2T_LIST = [
    "将將", "众衆", "练練", "赏賞", "罚罰", "强強", "国國", "军軍", "计計", "谋謀", "胜勝", "败敗",
    "势勢", "权權", "战戰", "击擊", "铁鐵", "银銀", "钱錢", "领領", "项項", "顶頂", "顺順", "须須",
    "顾顧", "显顯", "题題", "类類", "数數", "学學", "觉覺", "习習", "见見", "说說", "话話", "语語",
    "读讀", "谁誰", "请請", "谢謝", "让讓", "认認", "识識", "议議", "论論", "训訓", "记記", "讲講",
    "误誤", "译譯", "词詞", "诗詩", "试試", "诚誠", "详詳", "调調", "谈談", "诸諸", "谓謂", "谕諭",
    "谨謹", "谬謬", "与與", "万萬", "无無", "处處", "备備", "敌敵", "师師", "帅帥", "团團", "围圍",
    "车車", "门門", "问問", "闻聞", "间間", "关關", "开開", "长長", "这這", "么麼", "们們", "个個",
    "种種", "样樣", "帮幫", "边邊", "变變", "标標", "别別", "气氣", "云雲", "电電", "风風", "飞飛",
    "马馬", "鸟鳥", "鱼魚", "龙龍", "义義", "艺藝", "亿億", "忆憶", "亚亞", "严嚴", "业業", "东東",
    "丝絲", "两兩", "丽麗", "举舉", "乐樂", "书書", "买買", "乱亂", "争爭", "亲親", "从從", "仓倉",
    "仪儀", "价價", "优優", "会會", "伟偉", "传傳", "伤傷", "伦倫", "伪偽", "体體", "余餘", "侠俠",
    "儿兒", "兰蘭", "兴興", "养養", "兽獸", "内內", "册冊", "写寫", "冲衝", "决決", "况況", "冻凍",
    "净淨", "凉涼", "减減", "几幾", "则則", "刚剛", "创創", "删刪", "剂劑", "剑劍", "剧劇", "劝勸",
    "办辦", "务務", "动動", "劳勞", "勋勳", "区區", "医醫", "华華", "协協", "单單", "卖賣", "卫衛",
    "却卻", "厂廠", "历歷", "厉厲", "压壓", "县縣", "双雙", "发發", "叙敘", "叠疊", "叶葉", "号號",
    "叹嘆", "吓嚇", "听聽", "启啟", "员員", "咏詠", "响響", "哑啞", "唤喚", "嘱囑", "园園", "图圖",
    "场場", "坏壞", "块塊", "坚堅", "坛壇", "坟墳", "坠墜", "垒壘", "垦墾", "垫墊", "壮壯", "声聲",
    "壳殼", "复復", "头頭", "夹夾", "夺奪", "奋奮", "奖獎", "妇婦", "妈媽", "娇嬌", "娱娛", "婴嬰",
    "观觀", "规規", "视視", "览覽", "誉譽", "触觸", "讳諱", "讶訝", "诞誕", "询詢", "该該", "诫誡",
    "诬誣", "谦謙", "谱譜", "贝貝", "贞貞", "负負", "贡貢", "财財", "责責", "贤賢", "账賬", "货貨",
    "质質", "贩販", "购購", "贯貫", "贱賤", "贴貼", "贵貴", "贷貸", "贸貿", "费費", "贺賀", "贼賊",
    "赃贓", "资資", "赋賦", "赌賭", "赎贖", "赐賜", "赔賠", "赚賺", "赛賽", "赞贊", "赠贈", "赢贏",
    "赵趙", "赶趕", "趋趨", "软軟", "轮輪", "转轉", "轰轟", "轻輕", "载載", "较較", "轿轎", "辅輔",
    "辆輛", "辈輩", "输輸", "辐輻", "辑輯", "辖轄", "辞辭", "辩辯", "达達", "迁遷", "过過", "运運",
    "还還", "进進", "远遠", "违違", "连連", "迟遲", "迹跡", "适適", "选選", "逊遜", "递遞", "逻邏",
    "遗遺", "邓鄧", "邮郵", "郑鄭", "邻鄰", "钦欽", "钻鑽", "铃鈴", "铅鉛", "铜銅", "铺鋪", "链鏈",
    "销銷", "锁鎖", "锅鍋", "锋鋒", "锐銳", "错錯", "锡錫", "锦錦", "键鍵", "镇鎮", "镜鏡",
]
S2T: dict[str, str] = {}
for _p in _S2T_LIST:
    assert len(_p) == 2, f"简繁表条目必须是 2 个字：{_p!r}"
    if _p[0] != _p[1]:
        S2T[_p[0]] = _p[1]
T2S = {v: k for k, v in S2T.items()}

_CLEAN_RE = re.compile(r"[\s，。！？；：、,.!?;:\-—–~～·\|丨'" + r'“”"「」『』（）()《》〈〉\[\]【】…⋯]+')


def _clean(s: str) -> str:
    return _CLEAN_RE.sub("", s)


def _s2t(s: str) -> str:
    return "".join(S2T.get(c, c) for c in s)


def _t2s(s: str) -> str:
    return "".join(T2S.get(c, c) for c in s)


def _diff_pairs(a: str, b: str, limit: int = 8) -> list[tuple[str, str]]:
    """逐字对齐 a→b，返回差异字符对 [(a_char, b_char), ...]。"""
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            ca = a[i1 + k] if i1 + k < i2 else ""
            cb = b[j1 + k] if j1 + k < j2 else ""
            if ca and cb:
                out.append((ca, cb))
        if len(out) >= limit:
            break
    return out[:limit]


_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def _looks_like_path(q: str) -> bool:
    """引号里括着的其实是**文件名 / 通配符 / URL**（技术 token），不是引语。

    实测假阳性（#62）：卡片写 `任一返回"未找到 references/…md"时…`，
    体检器把它当成"含省略号的引语"报了出来——**工具自己的噪声**（假阳性比漏报更坏）。
    判据用"斜杠后是否为非中文内容"，所以中文夹斜杠的「孩子/新事物如何启蒙」不会被误杀。
    """
    if "://" in q or "*" in q or "?" in q:
        return True
    for m in re.finditer(r"[/\\]([^/\\\s]{0,40})", q):
        tail = m.group(1)
        if tail and not _CJK_CHAR_RE.search(tail):
            return True
    return False


def extract_quotes(text: str) -> list[dict]:
    """抽取引号文本（「」/""），带行号与"是否在元描述框内"。"""
    out: list[dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        for pat in QUOTE_PATTERNS:
            for m in pat.finditer(line):
                q = m.group(1).strip()
                if len(q) < 8 or _looks_like_path(q):
                    continue
                ctx = "\n".join(lines[max(0, i - 2):min(len(lines), i + 1)])
                # 作者举例框的标记通常在小节标题上，离引语可能隔几行 → 用更宽的窗口
                ctx_wide = "\n".join(lines[max(0, i - 8):min(len(lines), i + 1)])
                out.append({
                    "line": i, "quote": q,
                    "meta": (any(t in ctx for t in META_TAGS)
                             or any(t in ctx_wide for t in AUTHOR_FRAME)),
                })
    return out


def count_technical_tokens(text: str) -> int:
    """被 `_looks_like_path` 判掉的技术 token 数——单独计数，不静默丢弃。"""
    n = 0
    for pat in QUOTE_PATTERNS:
        for m in pat.finditer(text):
            if _looks_like_path(m.group(1).strip()):
                n += 1
    return n


def lint_corpus(quote: str, corpus_clean: str, corpus_sentences: list[str]) -> dict | None:
    """对单条引语做三项检查。返回发现 dict 或 None（无发现）。"""
    qc = _clean(quote)
    if not qc:
        return None
    # 2) 省略号：不是逐字原文，任何段落核验都无法确认
    if ELLIPSIS_RE.search(quote):
        return {"kind": "ellipsis", "quote": quote,
                "why": "引语含省略号（…/...），非逐字原文；段落级核验无法确认。"
                       "要么补全为原文，要么明确标注为节引"}
    # 1) 字形不一致：先精确找，再用简繁表，再兜底近似句
    if corpus_clean and qc not in corpus_clean:
        for conv, label in ((_s2t(qc), "简繁不一致（卡片用简体、语料用繁体）"),
                            (_t2s(qc), "简繁不一致（卡片用繁体、语料用简体）")):
            if conv != qc and conv in corpus_clean:
                return {"kind": "glyph", "quote": quote, "why": label,
                        "pairs": _diff_pairs(qc, conv)}
        if corpus_sentences:
            best = max(corpus_sentences,
                       key=lambda s: difflib.SequenceMatcher(None, qc, s).ratio())
            ratio = difflib.SequenceMatcher(None, qc, best).ratio()
            if ratio >= 0.80 and abs(len(best) - len(qc)) <= max(4, len(qc) // 4):
                pairs = _diff_pairs(qc, best)
                if pairs:
                    return {"kind": "glyph", "quote": quote,
                            "why": f"疑似用字不一致（近似度 {ratio:.2f}，可能是异体/错字/简繁表未覆盖）",
                            "pairs": pairs}
        # 4) 归属可疑：不在语料（也不在简繁变换后）+ 作者行文特征
        if _AUTHOR_PRON.search(qc) and _AUTHOR_CHOICE.search(qc):
            return {"kind": "authorship", "quote": quote,
                    "why": "语料中找不到，且含人称代词 + 选择/假设词 —— "
                           "疑似把作者自己的举例当成来源引语；确认是行文就去掉引号"}
    return None


def lint(card: Path, corpus_texts: dict[str, str] | None = None) -> dict:
    """体检一张卡片。corpus_texts = {名称: 原文}（可为空）。"""
    text = Path(card).read_text(encoding="utf-8", errors="replace")
    corpus_texts = corpus_texts or {}
    corpus_clean = "".join(_clean(t) for t in corpus_texts.values())
    corpus_sentences: list[str] = []
    for t in corpus_texts.values():
        corpus_sentences += [s for s in (_clean(x) for x in re.split(r"[。！？；\n]+", t))
                             if len(s) >= 8]

    quotes = [q for q in extract_quotes(text) if not q["meta"]]
    lines = text.splitlines()
    findings: list[dict] = []
    for q in quotes:
        f = lint_corpus(q["quote"], corpus_clean, corpus_sentences)
        if f:
            # 工具自己给的处置是二选一：「补全为原文，**或明确标注为节引**」。
            # 那就必须认这个标注——否则照做的人反而永远被提示，等于工具在说"我怎么都不满意"。
            ctx = "\n".join(lines[max(0, q["line"] - 3):min(len(lines), q["line"] + 1)])
            if f["kind"] == "ellipsis" and ("节引" in ctx or "節引" in ctx):
                continue
            f["line"] = q["line"]
            findings.append(f)
    by_kind: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
    has_corpus = bool(corpus_clean)
    # 空集守卫：卡片含引语候选，却一条都没抽出来 → 体检器没干活，不是"没问题"
    raw_candidates = sum(len(p.findall(text)) for p in QUOTE_PATTERNS)
    # #62：引号里的技术 token（文件名/通配/URL）不是引语——单独计数，不静默丢弃，
    # 也不让它们参与 vacuous 判定（否则"只有技术 token"会被误报成空集）。
    technical = count_technical_tokens(text)
    vacuous = (not quotes) and (raw_candidates - technical) > 0
    glyph = [f for f in findings if f["kind"] == "glyph"]
    return {
        "schema": "rulai-distill/lint-quotes@1",
        "card": str(card),
        "corpus_provided": has_corpus,
        "quotes_checked": len(quotes),
        "technical_tokens_skipped": technical,
        "findings": findings,
        "by_kind": by_kind,
        "vacuous": vacuous,
        "notes": "" if has_corpus else "未提供 --corpus：只做了省略号检查（简繁/归属需语料）",
        # 只有 glyph（确证"近似但不逐字"）判失败；ellipsis/authorship 是启发式，只提示。
        "verdict": "vacuous" if vacuous else ("fail" if glyph else "pass"),
    }
