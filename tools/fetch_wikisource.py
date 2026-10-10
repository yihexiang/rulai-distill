#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-2 · 从维基文库取公版原典（P0-2 批次用）。

**为什么要写这个脚本**：P0-2 要跑「开放素材端到端批次」，而批次最大的风险是
**素材来源说不清**——引了哪一版、什么时候取的、URL 是什么，全靠记忆。
本脚本把来源与取回时间**逐份写进sidecar**，并落 sha256。

**只用公版素材**：维基文库上的先秦至宋元文本（司马光《资治通鉴》、袁枢《通鉴纲目》
等）均为公有领域。**TED 字幕是 CC BY-NC-ND，另有署名义务**，单独标注。

用法：
    python3 tools/fetch_wikisource.py --out<run>/corpus/raw \\
        --page "資治通鑑/卷001" --page "資治通鑑/卷002" --source-id src-01-zizhi-tongjian
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

API = "https://zh.wikisource.org/w/api.php"

# 维基文库的公有领域声明（用于卡片来源行；ND/NC 素材不走这个脚本）
LICENSE_NOTE = (
    "公有领域：维基文库原文取自公有领域典籍，保留原文用字与标点。"
)


def fetch_page(page: str, tries: int = 3) -> str:
    """取一页 wikitext。失败重试；都失败则抛错（**不返回空串冒充成功**）。

    页面名必须 **percent-encode**：curl 收到含中文与 `/` 的裸 URL 会自己猜路径分隔，
    返回的是 HTML 而不是 JSON —— 首版就栽在这儿，报错还只说「JSON 解析失败」，
    真正原因（URL 没编码）被藏了两层。
    """
    url = (f"{API}?action=parse&page={quote(page, safe='')}&prop=wikitext"
           f"&format=json&formatversion=2")
    last = ""
    for i in range(tries):
        p = subprocess.run(["curl", "-sS", "--max-time", "40", url],
                           capture_output=True, text=True)
        if p.returncode != 0:
            last = f"curl rc={p.returncode}"
            time.sleep(2.0 * (i + 1))
            continue
        # **限流不是错误，是「等一会」**。维基 API 会返回纯文本
        # "You are making too many requests..."（HTTP 200！），所以
        # 只能靠响应内容判断——若按 JSON 解析失败处理，报错会指向错误的根因。
        if "too many requests" in p.stdout[:200].lower():
            wait = 5.0 * (i + 1)
            print(f"  … 被限流，等 {wait:.0f}s 后重试（{page}）")
            last = "API 限流"
            time.sleep(wait)
            continue
        try:
            d = json.loads(p.stdout)
        except json.JSONDecodeError as e:
            head = p.stdout[:60].replace("\n", " ")
            last = f"JSON 解析失败：{e}｜响应开头：{head!r}"
            time.sleep(1.5 * (i + 1))
            continue
        if d.get("error"):
            last = f"API error：{d['error'].get('info')}"
            time.sleep(1.5 * (i + 1))
            continue
        wt = (d.get("parse") or {}).get("wikitext", "")
        if wt.strip():
            return wt
        last = "返回空 wikitext"
    raise SystemExit(f"❌ 取不到「{page}」：{last}（已重试 {tries} 次）")


def strip_wikitext(wt: str) -> str:
    """去模板/链接/引用，保留可读正文。**保守处理**：去不掉的行整行丢掉并计数。

    三条都是实测踩出来的，每条都曾让语料"看起来正常、实则不可用"：

    1. **多行模板必须整体去掉**。`{{header2\\n|title=…\\n|section=…}}` 跨行，
       首版只做单行 `\\{\\{[^{}]*\\}\\}` → 模板头被删、**`|title=…` 这些
       参数行留在正文里**，读起来像史料内容。
    2. **章节标题 `== X ==` 要转成 markdown `## X`**，不能丢：丢了之后
       5.9 万字只剩 6 段（每段近万字），分块粒度与引语定位一起失控。
    3. 段落之间**必须补空行**。维基文库原文是「一行一段」，
       而 `corpus-anchor` 按空行切段 —— 不补空行，628 行只会切出 6 段。
    """
    # ① 多行模板：反复删最内层 `{{...}}`，直到没有为止（模板可嵌套）
    prev = None
    while prev != wt:
        prev = wt
        wt = re.sub(r"\{\{[^{}]*\}\}", "", wt, flags=re.S)
    # ①b 剩下的是不含 {} 的残块（如 `|title=…` 单独成行）→ 丢掉
    out, dropped, headings = [], 0, 0
    for line in wt.splitlines():
        s = line.strip()
        if s.startswith("|") or s.startswith("}}") or s.startswith("{{"):
            continue
        if s == "" or s.startswith("----"):
            continue
        if re.match(r"^\[\[([^]|]*\|)?\1?\]\]$", s) and s.startswith("[["):
            continue
        # ② 章节标题：== X == / === X === → ## X / ### X
        m = re.match(r"^(={2,6})\s*(.+?)\s*\1$", s)
        if m:
            level = min(len(m.group(1)) - 1, 5)
            out.append("#" * level + " " + m.group(2))
            headings += 1
            continue
        s = re.sub(r"\[\[(?:File|Image|文件|檔案|分類|Category):[^\]]*\]\]", "", s,
                   flags=re.I)
        s = re.sub(r"\[\[([^]|]*)\|([^\]]*)\]\]", r"\2", s)
        s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
        s = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", s)
        s = re.sub(r"<[^>]+>", "", s)
        s = s.replace("'''", "").replace("''", "")
        if not s.strip():
            continue
        if "{{" in s or "[[" in s:      # 去不干净 → 丢掉并计数，不硬塞
            dropped += 1
            continue
        out.append(s)
    # ③ 段间补空行：让「按空行切段」真正切得开
    paras: list[str] = []
    for item in out:
        if item.startswith("#"):
            paras.append("\n" + item)     # 标题自带前空行
        else:
            paras.append(item)
    body = "\n\n".join(x.strip() for x in paras if x.strip())
    tail = ""
    if dropped or headings:
        tail = (f"\n<!-- stripped_wikitext: headings_kept={headings}, "
                f"malformed_lines_dropped={dropped} -->\n")
    return body + tail


def main() -> int:
    ap = argparse.ArgumentParser(description="取维基文库公版原典")
    ap.add_argument("--out", required=True, help="输出目录（建议 <run>/corpus/raw）")
    ap.add_argument("--page", action="append", required=True,
                    help="页面名，可重复；同名页面写进同一份 src")
    ap.add_argument("--source-id", default="src-01", help="来源标识")
    ap.add_argument("--title", default="", help="书名（写进 frontmatter）")
    ap.add_argument("--max-chars", type=int, default=0,
                    help=">0 时只取前 N 字（控制本批次成本，会如实记录截断）")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    parts, pages = [], []
    for pg in args.page:
        wt = fetch_page(pg)
        body = strip_wikitext(wt)
        if args.max_chars and sum(len(p) for p in parts) + len(body) > args.max_chars:
            room = args.max_chars - sum(len(p) for p in parts)
            if room <= 0:
                break
            body = body[:room] + f"\n<!-- truncated_at: {args.max_chars} 字 -->\n"
        parts.append(body)
        pages.append(pg)
        print(f"  ✓ {pg}  → {len(body):,} 字")
        time.sleep(0.4)          # 对公共 API 友好

    text = "\n\n".join(parts)
    path = out / f"{args.source_id}.md"
    header = (
        "---\n"
        f"source_id: {args.source_id}\n"
        f"title: {args.title or args.page[0]}\n"
        f"author: {args.page[0].split('/')[0]}\n"
        f"url: https://zh.wikisource.org/wiki/{args.page[0].replace(' ', '_')}\n"
        f"fetched: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')}\n"
        f"license: {LICENSE_NOTE}\n"
        f"pages: {json.dumps(pages, ensure_ascii=False)}\n"
        "---\n\n"
        "> 取自维基文库公有领域文本；保留原文用字与标点，未做现代化改写。\n"
    )
    path.write_text(header + text, encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"\n✅ {path}  {len(text):,} 字  sha256={sha[:16]}…")
    print(f"   页面：{', '.join(pages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())