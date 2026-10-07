# -*- coding: utf-8 -*-
"""tdlib.transcript — 字幕（SRT / WebVTT）→ 带时间戳的可溯源逐字稿。

对标 alchaincyf/nuwa-skill 的 scripts/srt_to_transcript.py，并做了三处改进：
  1. **不联网**：不内置字幕下载。nuwa 的 download_subtitles.sh 依赖 yt-dlp 且要求
     访问 YouTube，在国内不可用；本实现只处理**用户已获得的本地字幕文件**，
     下载环节留给用户或外部工具（README 有说明）。
  2. 支持 VTT 与多文件合并（多集/多 P 连续素材），带 --offset 与 --gap 合并阈值。
  3. 去重：字幕滚动显示会把同一句话重复 2-3 次，按归一化文本相邻去重；
     同时过滤空cue 与纯符号行。

产物：
  <out>.transcript.md   人读逐字稿（每段带 [HH:MM:SS]）
  <out>.transcript.json 机器读版本（cues + 统计），供 chunk 阶段直接消费
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import (ToolError, jaccard, ngrams, now_iso, read_json, read_text, write_json)

TS_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")
TAG_RE = re.compile(r"<[^>]+>")
SPEAKER_RE = re.compile(r"^\s*([^\s:：]{1,12})\s*[:：]\s*")
NOISE_RE = re.compile(r"^[\s\W_]*$")
BRACKET_RE = re.compile(r"[\[(（【][^\])）】]{0,20}[\])）】]\s*$")


def _ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms.ljust(3, "0"))


def parse_subtitle(text: str) -> list[dict]:
    """解析 SRT / VTT，返回 [{index,start_ms,end_ms,text}]。"""
    cues: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    idx = 0
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[0].strip().upper().startswith("WEBVTT"):
            lines = lines[1:]
            if not lines:
                continue
        ts_line = None
        for ln in lines:
            if "-->" in ln:
                ts_line = ln
                break
        if ts_line is None:
            continue
        m = TS_RE.search(ts_line)
        if not m:
            continue
        start = _ms(*m.group(1, 2, 3, 4))
        end = _ms(*m.group(5, 6, 7, 8))
        body_idx = lines.index(ts_line) + 1
        payload = " ".join(lines[body_idx:])
        payload = TAG_RE.sub("", payload)
        payload = re.sub(r"\s+", " ", payload).strip()
        if not payload or NOISE_RE.match(payload):
            continue
        idx += 1
        cues.append({"index": idx, "start_ms": start, "end_ms": end, "text": payload})
    return cues


def _norm_key(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE).lower()


def _sim(a: str, b: str) -> float:
    """相邻字幕相似度：**字符 3-gram Jaccard**，不是字符集 Jaccard。

    实测踩过（管线验证样本 15 条 cue 被误删 2 条）：用字符集算相似度时，
    英文句子的常用字母天然重叠，两句完全不同的话被判成 0.9+ → 正常字幕被
    当成滚动重复删掉。子串命中仍走短路（那才是真正的滚动重复）。
    """
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if short and short in long:
        return 1.0
    return jaccard(ngrams(short), ngrams(long))


def dedupe(cues: list[dict], min_ratio: float = 0.86) -> tuple[list[dict], int]:
    """相邻字幕去重：归一化后相似度超阈值视为滚动重复，保留更完整的一条。"""
    out: list[dict] = []
    dropped = 0
    for cue in cues:
        if out:
            prev = out[-1]
            a, b = _norm_key(prev["text"]), _norm_key(cue["text"])
            if a and b:
                ratio = _sim(a, b)
                if ratio >= min_ratio:
                    dropped += 1
                    if len(b) > len(a):
                        out[-1] = cue
                    continue
        out.append(cue)
    return out, dropped


def group_cues(cues: list[dict], gap_ms: int = 2500, max_chars: int = 420) -> list[dict]:
    """把短 cue 聚成段：间隔 < gap 且累计长度未超上限则合并，保留段首时间戳。"""
    paras: list[dict] = []
    for cue in cues:
        if paras and (cue["start_ms"] - paras[-1]["end_ms"]) <= gap_ms \
                and len(paras[-1]["text"]) + len(cue["text"]) + 1 <= max_chars:
            paras[-1]["text"] += (" " if _has_cjk(paras[-1]["text"]) else " ") + cue["text"]
            paras[-1]["end_ms"] = cue["end_ms"]
            paras[-1]["cue_count"] += 1
        else:
            paras.append({"start_ms": cue["start_ms"], "end_ms": cue["end_ms"],
                          "text": cue["text"], "cue_count": 1})
    for p in paras:
        p["text"] = p["text"].replace(" ,", ",").replace(" .", ".").strip()
        if BRACKET_RE.match(p["text"]) and len(p["text"]) < 12:
            p["_noise"] = True
    return [p for p in paras if not p.get("_noise")]


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def hhmmss(ms: int) -> str:
    s, m = ms // 1000, (ms % 1000) // 100 * 10
    h, m2 = s // 3600, (s % 3600) // 60
    return f"{h:02d}:{m2:02d}:{s % 60:02d}.{m:02d}"


def speaker_of(text: str) -> tuple[str, str]:
    """从「标签：正文」里切出说话人。**只判断、不提供改写后的字符串。**

    ⚠️ 2026-10-07（#55）：原实现只做 `SPEAKER_RE.match` 就认定是说话人，
    而 `SPEAKER_RE = ^\\s*([^\\s:：]{1,12})\\s*[:：]\\s*` **对中文完全失效**——
    中文「我想通一件事：听众其实不介意你停顿」这种句式极常见，
    冒号前的整句被当成说话人名，然后 `build_transcript` 把正文改写成
    `**那半分钟里我想通一件事**： 听众其实…`：
      1. 往逐字稿里插入了原文没有的 `**` 与空格；
      2. 而逐字稿是**所有引语核验的真值来源** → 卡片逐字引用原话反而被判
         「❌ 未在语料中找到，这类来源不实必须修掉」；
      3. 用户为了"修好"，只能把工具加进去的 `**` 抄进卡片 → **等于教用户伪造引语**。
    实测：真实英文 TED 字幕 315 条 cue 零误判，**纯中文句式必中**——
    又是一次"英文成立、中文崩"（同类见 #52）。

    现在的判据：**重复出现才算说话人标签**（真实访谈里同一标签会反复出现，
    而中文的从句只会出现一次），长度上限也收紧。判定结果只用于统计，
    **不再参与正文拼接**。
    """
    m = SPEAKER_RE.match(text)
    if not m:
        return "", text
    label = m.group(1).strip()
    if len(label) > 24 or label.endswith(("。", "！", "？", ".", "!", "?", "，", ",")):
        return "", text
    if _has_cjk(label):
        # 中文：只可能是 2–6 字的姓名/称谓（张三／主持人／罗永浩）。
        # 更长的基本都是从句（「那半分钟里我想通一件事」）——
        # 而这正是旧实现误判并改写正文的来源。
        if not (2 <= len(label) <= 6):
            return "", text
    else:
        # 英文：必须以字母开头，且不能含句末标点
        if not label[:1].isalpha():
            return "", text
    return label, text[m.end():].strip()


def collect_speakers(paras: list[dict], min_hits: int = 2) -> list[str]:
    """只在**重复出现**时确认说话人标签（#55）。

    单次出现的「X：」在中文里绝大多数是普通从句，不是说话人。
    返回按出现次数降序的标签列表，仅写进 JSON 元数据，**不改正文**。
    """
    counts: dict[str, int] = {}
    for p in paras:
        label, _ = speaker_of(p["text"])
        if label:
            counts[label] = counts.get(label, 0) + 1
    return [k for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v >= min_hits]


def build_transcript(src: Path, out_base: Path | None = None, gap_ms: int = 2500,
                     max_chars: int = 420, offset_ms: int = 0, min_ratio: float = 0.86,
                     keep_speaker: bool = True) -> dict:
    src = Path(src)
    if not src.exists():
        raise ToolError(f"字幕文件不存在：{src}",
                        "本技能不联网下载字幕。请先用外部工具获取 .srt/.vtt 放到本地。")
    if src.suffix.lower() not in (".srt", ".vtt", ".txt", ".sbv"):
        warn(f"扩展名 {src.suffix} 不常见，按纯文本解析尝试")
    text = read_text(src)
    cues = parse_subtitle(text)
    if not cues:
        raise ToolError(f"未解析出任何字幕条目：{src}",
                        "确认是 SRT/VTT 格式；或先用 ffmpeg 生成 SRT")
    if offset_ms:
        for c in cues:
            c["start_ms"] += offset_ms
            c["end_ms"] += offset_ms
    cues, dropped = dedupe(cues, min_ratio=min_ratio)
    paras = group_cues(cues, gap_ms=gap_ms, max_chars=max_chars)

    out_base = Path(out_base) if out_base else src.with_suffix("")
    # 注意：不能用 with_suffix —— 当 out_base 自身含点（如 merged.part0）会被吃掉后缀，
    # 导致所有分片写到同一个文件并在清理阶段把最终产物删掉。
    md_path = Path(str(out_base) + ".transcript.md")
    json_path = Path(str(out_base) + ".transcript.json")

    lines = [
        "---",
        f"source: {src.name}",
        f"generated_at: {now_iso()}",
        f"generator: td.transcript v1.0",
        f"cues: {len(cues)}",
        f"paragraphs: {len(paras)}",
        f"dedup_dropped: {dropped}",
        "---",
        "",
        f"# 逐字稿 · {src.stem}",
        "",
        "> 本文件由 `td.py transcript` 从本地字幕生成，时间戳可用于 `source_locator`。",
        "> 字幕为听写产物，数字与人名可能出错；关键引语需回听原视频核对。",
        "",
    ]
    # 2026-10-07（#55）：正文**原样输出**，绝不加 `**`、绝不重排冒号空格。
    # 逐字稿是引语核验的真值来源，任何改写都会让"真引语"被判成"来源不实"。
    # 说话人只作为元数据记录（且必须重复出现才确认）。
    speakers = collect_speakers(paras)
    for p in paras:
        lines.append(f"[{hhmmss(p['start_ms'])}] {p['text']}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    write_json(json_path, {
        "schema": "rulai-distill/transcript@1",
        "source": str(src),
        "source_sha_note": "生成时刻稿内容已定稿；重复运行请以 md 为准",
        "generated_at": now_iso(),
        "cue_count": len(cues),
        "paragraph_count": len(paras),
        "dedup_dropped": dropped,
        "speakers": speakers,
        "lossless_note": "逐字稿正文严格等于字幕原文（只按段落合并，不做任何改写）",
        "duration_ms": paras[-1]["end_ms"] if paras else 0,
        "paragraphs": paras,
        # cue 级明细：能力卡的引语定位需要精确到"第几句"，
        # 只留段落起点会让 [00:00:23.10] 这类引用无法核验（实测踩到）。
        "cues": [{"index": c["index"], "start_ms": c["start_ms"],
                  "end_ms": c["end_ms"], "text": c["text"]} for c in cues],
    })
    return {
        "source": str(src),
        "md": str(md_path),
        "json": str(json_path),
        "cues": len(cues),
        "paragraphs": len(paras),
        "dropped": dropped,
        "duration_ms": paras[-1]["end_ms"] if paras else 0,
    }


def merge_transcripts(srcs: list[Path], out_base: Path, gap_ms: int = 2500,
                      max_chars: int = 420) -> dict:
    """多集/多 P 合并：按文件名自然序排列，段间插入分隔标记。"""
    all_paras: list[dict] = []
    per_file = []
    for i, s in enumerate(sorted(srcs, key=lambda p: _natural_key(p.name))):
        r = build_transcript(s, out_base=Path(str(out_base) + f".part{i}"), gap_ms=gap_ms,
                             max_chars=max_chars)
        per_file.append(r)
        data = read_json(Path(r["json"]))
        for p in data["paragraphs"]:
            all_paras.append(p)
    lines = [
        "---",
        f"source_files: {len(srcs)}",
        f"generated_at: {now_iso()}",
        "generator: td.transcript v1.0 (merge)",
        f"paragraphs: {len(all_paras)}",
        "---",
        "",
        f"# 逐字稿 · {Path(out_base).name}（{len(srcs)} 个文件合并）",
        "",
    ]
    for p in all_paras:
        lines.append(f"[{hhmmss(p['start_ms'])}] {p['text']}")
        lines.append("")
    md = Path(str(out_base) + ".transcript.md")
    md.write_text("\n".join(lines), encoding="utf-8")
    for r in per_file:
        Path(r["md"]).unlink(missing_ok=True)
        Path(r["json"]).unlink(missing_ok=True)
    write_json(Path(str(out_base) + ".transcript.json"), {
        "schema": "rulai-distill/transcript@1", "mode": "merge",
        "generated_at": now_iso(), "files": [str(s) for s in srcs],
        "paragraph_count": len(all_paras), "md": str(md),
    })
    return {"md": str(md), "files": len(srcs), "paragraphs": len(all_paras)}


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]
