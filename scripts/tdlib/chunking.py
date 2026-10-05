# -*- coding: utf-8 -*-
"""tdlib.chunking — 结构感知分块 + 索引 + 确定性缓存。

对标 kangarooking/cangjie-skill 的 scripts/build_chunks.py 与 build_index.py，
并把两者合并为一个命令（chunk → document + chunks + index），减少一次 IO 往返。

为什么必须结构感知：按固定字符数硬切会切断论证链条，提取出的单元无法判断
"是否被后文推翻"。本实现尊重标题层级边界，只在单个超长元素内部才二次切分。

产物（写入 --sidecar，默认 <source>.td/）：
  document.json   SourceDocument：elements + 元信息
  chunks.jsonl    结构感知块，每行一个 chunk
  index.json      标题路径 → chunk 映射，供提取阶段按需检索
  .cache.json     源文件 sha256 → 命中则跳过重算
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import uuid
from pathlib import Path

from . import contracts
from .util import (ToolError, ensure_dir, info, now_iso, read_json, read_text, sha256_of,
                   sha256_text, step, warn, write_json)

MEDIA_BY_EXT = {".md": "markdown", ".markdown": "markdown", ".txt": "txt",
                ".pdf": "pdf", ".html": "html", ".epub": "epub",
                ".srt": "subtitle", ".vtt": "subtitle", ".json": "txt"}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
SENT_SPLIT_RE = re.compile(r"(?<=[。！？；!?;])|(?<=\.\s)")
IMPL_VERSION = "td.chunk v1.2"
SCHEMA_VERSION = "source-document@1/chunk@1"


def _guess_title(text: str, src: Path) -> str:
    """取正文首个一级标题；没有就用文件名。source-document 契约要求 title 非空。"""
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()[:120]
    return src.stem


def _guess_language(text: str) -> list[str]:
    """粗判语言（契约里 language 是可选字段，缺失不影响合规，但填上更完整）。"""
    head = text[:4000]
    cjk = sum(1 for ch in head if "\u4e00" <= ch <= "\u9fff")
    if cjk > len(head) * 0.05:
        return ["zh"]
    return ["en"]


def deterministic_cache_key(stage: str, impl_version: str, schema_version: str,
                            input_hashes: list[str], params: dict) -> str:
    """缓存键必须包含**实现版本与契约版本**，否则改了算法还会命中旧结果。

    这是从 kangarooking/cangjie-skill 的 cangjie_common.deterministic_cache_key 学来的，
    本项目 v1.1.0 曾只用 (source_sha256, max_chars) 做键——改算法不失效，是真实缺陷。
    """
    payload = "\n".join([stage, impl_version, schema_version, *input_hashes,
                         json.dumps(params, ensure_ascii=False, sort_keys=True)])
    return sha256_text(payload)


def new_run_id() -> str:
    return _dt.datetime.now().strftime("run-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


# --------------------------------------------------------------------------
# 解析：markdown/txt → elements
# --------------------------------------------------------------------------
def parse_elements(text: str) -> list[dict]:
    elements: list[dict] = []
    heading_stack: list[tuple[int, str]] = []
    in_code = False
    buf: list[str] = []
    buf_type = "paragraph"
    char_pos = 0

    def flush(end_pos: int) -> None:
        nonlocal buf, buf_type
        content = "\n".join(buf).strip()
        start_pos = char_pos
        buf = []
        if not content:
            return
        elements.append({
            "element_id": f"el-{len(elements):06d}",
            "type": buf_type,
            "text": content,
            # content_hash 是上游 source-document 契约的必填项：用于跨版本判断元素是否变化
            "content_hash": f"sha256:{sha256_text(content)}",
            "heading_path": [h for _, h in heading_stack],
            "heading_level": heading_stack[-1][0] if heading_stack else 0,
            "char_start": start_pos,
            "char_end": end_pos,
        })

    for line in text.splitlines(keepends=True):
        line_end = char_pos + len(line)
        if line.lstrip().startswith("```"):
            flush(char_pos)
            in_code = not in_code
            buf_type = "code"
            buf.append(line.rstrip("\n"))
            char_pos = line_end
            continue
        if in_code:
            buf.append(line.rstrip("\n"))
            char_pos = line_end
            continue
        m = HEADING_RE.match(line.strip())
        if m:
            flush(char_pos)
            level = len(m.group(1))
            title = m.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            buf_type = "heading"
            buf = [title]
            flush(line_end)
            buf_type = "paragraph"
            continue
        stripped = line.strip()
        if not stripped:
            flush(char_pos)
            buf_type = "paragraph"
            char_pos = line_end
            continue
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            flush(char_pos)
            buf_type = "list"
            buf.append(stripped)
            char_pos = line_end
            flush(line_end)
            buf_type = "paragraph"
            continue
        if buf_type != "paragraph":
            flush(char_pos)
        buf_type = "paragraph"
        buf.append(stripped)
        char_pos = line_end
    flush(char_pos)
    return elements


# --------------------------------------------------------------------------
# 分块
# --------------------------------------------------------------------------
def _split_long(text: str, max_chars: int) -> list[str]:
    """超长元素内部按句子边界二次切分；单句超长则硬切（并记录告警）。"""
    if len(text) <= max_chars:
        return [text]
    sentences = [s for s in SENT_SPLIT_RE.split(text) if s]
    out: list[str] = []
    cur = ""
    for s in sentences:
        if len(s) > max_chars:
            if cur:
                out.append(cur)
                cur = ""
            for i in range(0, len(s), max_chars):
                out.append(s[i:i + max_chars])
            continue
        if len(cur) + len(s) <= max_chars:
            cur += s
        else:
            if cur:
                out.append(cur)
            cur = s
    if cur:
        out.append(cur)
    return out


def build_chunks(elements: list[dict], max_chars: int = 4000) -> list[dict]:
    """按标题边界聚合 elements 成块；仅在元素超长时内部再切。"""
    chunks: list[dict] = []
    cur: dict | None = None

    def close() -> None:
        nonlocal cur
        if cur and cur["text"].strip():
            cur["chars"] = len(cur["text"])
            chunks.append(cur)
        cur = None

    for el in elements:
        if el["type"] == "code":
            pieces = [el["text"]] if len(el["text"]) <= max_chars else _split_long(el["text"], max_chars)
            for p in pieces:
                close()
                cur = {
                    "chunk_id": f"ck-{len(chunks):04d}",
                    "heading_path": el["heading_path"],
                    "heading_level": el["heading_level"],
                    "elements": [{"element_id": el["element_id"], "type": el["type"]}],
                    "char_start": el["char_start"],
                    "char_end": el["char_end"],
                    "dominated_by_code": True,
                    "text": p,
                }
                close()
            continue

        pieces = [el["text"]] if len(el["text"]) <= max_chars else _split_long(el["text"], max_chars)
        for pi, piece in enumerate(pieces):
            if cur is not None:
                same_path = cur["heading_path"] == el["heading_path"]
                would_be = len(cur["text"]) + len(piece) + 2
                level_ok = el["heading_level"] <= cur["heading_level"] or cur["heading_level"] == 0
                if not (same_path and would_be <= max_chars and level_ok):
                    close()
            if cur is None:
                cur = {
                    "chunk_id": f"ck-{len(chunks):04d}",
                    "heading_path": el["heading_path"],
                    "heading_level": el["heading_level"],
                    "elements": [],
                    "char_start": el["char_start"],
                    "char_end": el["char_end"],
                    "dominated_by_code": False,
                    "text": "",
                }
            cur["text"] = (cur["text"] + "\n\n" + piece).strip() if cur["text"] else piece
            cur["char_end"] = el["char_end"]
            eid = el["element_id"] if pi == 0 else f"{el['element_id']}#{pi}"
            cur["elements"].append({"element_id": eid, "type": el["type"]})
    close()
    for c in chunks:
        c["chars"] = len(c["text"])
    return chunks


def build_index(chunks: list[dict]) -> dict:
    """标题树 → chunk 映射。提取阶段用 grep heading_path 定位相关块，避免全量读入。"""
    tree: dict = {}
    for c in chunks:
        path = c["heading_path"] or ["(root)"]
        node = tree
        for seg in path:
            node = node.setdefault(seg, {"_chunks": []})
        node["_chunks"].append(c["chunk_id"])
    return {
        "chunk_count": len(chunks),
        "max_chars_hint": max((c["chars"] for c in chunks), default=0),
        "total_chars": sum(c["chars"] for c in chunks),
        "headings": tree,
    }


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------
def chunk_file(src: Path, sidecar: Path | None = None, max_chars: int = 4000,
               source_id: str = "src-main", force: bool = False) -> dict:
    src = Path(src)
    if not src.exists():
        raise ToolError(f"源文件不存在：{src}", "检查路径，或先下载字幕文件")
    if not src.is_file():
        raise ToolError(f"期望文件，得到目录：{src}")
    sidecar = Path(sidecar) if sidecar else src.with_suffix(src.suffix + ".td")
    ensure_dir(sidecar)

    digest = sha256_of(src)
    cache_key = deterministic_cache_key(
        "build_chunks", IMPL_VERSION, SCHEMA_VERSION, [digest],
        {"max_chars": max_chars, "source_id": source_id})
    cache_root = sidecar / "cache" / "build_chunks"
    cache_path = cache_root / cache_key
    meta_path = sidecar / "document.json"
    if not force and cache_path.exists() and meta_path.exists():
        step(f"命中确定性缓存（key {cache_key[:12]}…，含实现版本 {IMPL_VERSION}）")
        return read_json(cache_path / "MANIFEST.json")

    text = read_text(src)
    run_id = new_run_id()
    elements = parse_elements(text)
    chunks = build_chunks(elements, max_chars=max_chars)
    index = build_index(chunks)
    version_id = f"sha256:{digest[:16]}"
    title = _guess_title(text, src)
    doc = {
        # ↓↓↓ 上游 source-document 契约的 6 个必填字段，一个不少 ↓↓↓
        "schema_version": contracts.SCHEMA_VERSION,
        "source_id": source_id,
        "version_id": version_id,
        "title": title,
        "media_type": MEDIA_BY_EXT.get(src.suffix.lower(), "txt"),
        "elements": elements,
        # ↑↑↑ 契约字段 ↑↑↑ 以下为本包附加的可追溯信息
        "language": _guess_language(text),
        "parser": f"{IMPL_VERSION} (tdlib.chunking)",
        # 兼容旧读者：本包自有的附加字段集中在这里
        "trace_distill": {
            "generator": IMPL_VERSION,
            "run_id": run_id,
            "source_path": str(src),
            "source_sha256": digest,
            "built_at": now_iso(),
            "chars": len(text),
            "element_count": len(elements),
            "chunk_count": len(chunks),
            "max_chars": max_chars,
        },
    }
    # 自校验：不合约就不落盘（契约的价值就在于强制）
    cres = contracts.validate("source-document", doc)
    if not cres["ok"]:
        raise ToolError("分块产物不符合上游 source-document 契约",
                        *(cres["errors"][:6]))
    # 上游规范的版本化分层：normalized/<source_id>/<version_id>/document.json
    contracts.write_verified("source-document", doc,
                             sidecar / "normalized" / source_id / digest[:16],
                             "document.json")
    write_json(meta_path, doc)
    with (sidecar / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    write_json(sidecar / "index.json", index)

    result = {
        "schema": "rulai-distill/chunk-manifest@1",
        "run_id": run_id,
        "impl_version": IMPL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "cache_key": cache_key,
        "source_id": source_id,
        "source_path": str(src),
        "source_sha256": digest,
        "max_chars": max_chars,
        "built_at": doc["trace_distill"]["built_at"],
        "element_count": len(elements),
        "chunk_count": len(chunks),
        "total_chars": sum(c["chars"] for c in chunks),
        "max_chunk_chars": index["max_chars_hint"],
        "sidecar": str(sidecar),
    }
    # 缓存内容寻址 + 每次运行独立留痕（跨版本溯源：从 runs/ 能回看任意一次的分块结果）
    ensure_dir(cache_path)
    write_json(cache_path / "MANIFEST.json", result)
    write_json(sidecar / "runs" / run_id / "manifest.json", result)
    return result


def load_chunks(sidecar: Path) -> list[dict]:
    p = Path(sidecar) / "chunks.jsonl"
    if not p.exists():
        raise FileNotFoundError(f"未找到分块产物：{p}（先跑 `td.py chunk`）")
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def preview(sidecar: Path, limit: int = 10) -> None:
    chunks = load_chunks(sidecar)
    info(f"共 {len(chunks)} 块，前 {min(limit, len(chunks))} 块：")
    for c in chunks[:limit]:
        path = " / ".join(c["heading_path"]) or "(root)"
        head = c["text"][:40].replace("\n", " ")
        info(f"  {c['chunk_id']}  {c['chars']:>5}c  {path[:40]:<40}  {head}…")


# --------------------------------------------------------------------------
# 词法索引：SQLite FTS5 + 中文 bigram + 邻接块扩展
# --------------------------------------------------------------------------
def _norm_cjk(text: str) -> str:
    return re.sub(r"[\s，。、；：？！（）()【】《》,.;:?!\"']+", "", text.lower())


def _cjk_bigrams(text: str) -> str:
    """中文按字符 bigram 预处理入库；英文/数字**整体保留为词**。

    FTS5 的 unicode61 对 CJK 不分词，直接索引中文会整段当作一个 token，检索必然失效。

    ⚠️ 曾经的 bug（由 tests/bench_index.py 的对照基准抓出）：英文也走 bigram，
    把 "cost" 拆成 "c o s t"，FTS 于是匹配任何同时含 c/o/s/t 的块——816 个假命中。
    对照发现：上游 kangarooking/cangjie-skill 的做法是「只对 CJK 做 bigram，其余原样保留」。
    修正：ASCII 连续字符累积后 **join 成词** 再入库。
    """
    out: list[str] = []
    run: list[str] = []          # 当前连续 CJK 段
    tokens: list[str] = []       # 当前英文/数字词
    punct = set("，。、；：？！（）()【】《》,.;:?!\"' \t\r\n")

    def flush_tokens() -> None:
        if tokens:
            out.append("".join(tokens))     # ← 关键：整词入库，不是逐字母
            tokens.clear()

    def flush_cjk() -> None:
        if run:
            out.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
            run.clear()

    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            flush_tokens()
            run.append(ch)          # ← 先累积，遇到非 CJK 时才结算 bigram
        else:
            flush_cjk()              # ← CJK 连续段结束，结算 bigram
            if ch in punct:
                flush_tokens()
            else:
                tokens.append(ch.lower())
    flush_tokens()
    flush_cjk()
    return " ".join(t for t in out if t)


def build_lexindex(chunks_path: Path, db_path: Path | None = None) -> dict:
    """chunks.jsonl → SQLite FTS5 词法索引。"""
    import sqlite3
    chunks_path = Path(chunks_path)
    if not chunks_path.exists():
        raise ToolError(f"未找到分块文件：{chunks_path}", "先跑 `td.py chunk <src>`")
    chunks = load_chunks(chunks_path.parent)
    db_path = Path(db_path) if db_path else chunks_path.parent / "lexical.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("CREATE VIRTUAL TABLE chunks USING fts5("
                    "chunk_id UNINDEXED, seq UNINDEXED, heading_path, keywords, text)")
        for seq, c in enumerate(chunks):
            path = " ".join(c.get("heading_path") or [])
            con.execute("INSERT INTO chunks (chunk_id, seq, heading_path, keywords, text) "
                        "VALUES (?,?,?,?,?)",
                        (c["chunk_id"], seq, path,
                         _cjk_bigrams(path), _cjk_bigrams(c["text"])))
        con.commit()
    finally:
        con.close()
    return {"db": str(db_path), "chunks": len(chunks)}


def query_lexindex(db_path: Path, query: str, limit: int = 5, neighbors: int = 1) -> list[dict]:
    """词法检索 + 邻接块扩展。

    返回命中块及其前后 `neighbors` 块——**只给命中块会断章取义**，
    这正是上游 build_index 明确要解决的问题。
    """
    import sqlite3
    db_path = Path(db_path)
    if not db_path.exists():
        raise ToolError(f"索引不存在：{db_path}", "先跑 `td.py lexindex <chunks.jsonl>`")
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT chunk_id, seq FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
            (_cjk_bigrams(query), limit)).fetchall()
        originals = {c["chunk_id"]: c for c in load_chunks(db_path.parent)}
        out = []
        for cid, seq in rows:
            src = originals.get(cid, {})
            picked = [{"chunk_id": cid, "seq": seq, "relation": "hit",
                       "heading_path": src.get("heading_path", []),
                       "snippet": _window(src.get("text", ""), query)}]
            for off in range(1, neighbors + 1):
                for d in (-off, off):
                    r = con.execute("SELECT chunk_id, seq FROM chunks where seq=?",
                                    (seq + d,)).fetchone()
                    if r:
                        nb = originals.get(r[0], {})
                        picked.append({"chunk_id": r[0], "seq": r[1], "relation": f"neighbor{d:+d}",
                                       "heading_path": nb.get("heading_path", []),
                                       "snippet": _window(nb.get("text", ""), "")[:60]})
            out.append(picked)
        return out
    finally:
        con.close()


def _window(text: str, query: str, width: int = 42) -> str:
    """从原文里截一段带查询词的窗口（索引里是 bigram，展示必须用原文）。"""
    if not text:
        return ""
    if query:
        norm = _norm_cjk(text)
        q = _norm_cjk(query)
        pos = norm.find(q) if q else -1
        if pos >= 0:
            # 归一化会改变长度，用比例估算原文字符位置
            ratio = pos / max(1, len(norm))
            start = max(0, int(ratio * len(text)) - width // 2)
            return ("…" if start else "") + text[start:start + width].replace("\n", " ") + "…"
    return text[:width].replace("\n", " ") + "…"
