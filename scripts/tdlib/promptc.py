# -*- coding: utf-8 -*-
"""tdlib.promptc — 把技能包编译成单文件 prompt（对标 yeadon 的 scripts/compile-prompt.py）。

用途：目标环境**不支持 skill 目录加载**时（某些 agent 框架、CLI、API 调用），
把 SKILL.md + 引用文档压成一个可直接塞进 system prompt 的文本。

三种模式：
  entry   只编入口（SKILL.md 本体，最省 token）
  inline  把同目录/子目录的 references 全部内联（自包含，但贵）
  cards   能力卡包：入口 + 全部能力卡摘要（给人看目录用）
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import (MANIFEST_NAME, ToolError, count_tokens, info, load_frontmatter,
                   now_iso, read_text, token_source, write_json)

INLINE_SUFFIXES = (".md", ".template")


def compile_prompt(src: Path, out: Path | None = None, mode: str = "inline",
                   max_ref_chars: int = 20000) -> dict:
    src = Path(src)
    if not src.exists():
        raise ToolError(f"路径不存在：{src}")
    entry = src if src.is_file() else _find_entry(src)
    if entry is None:
        raise ToolError(f"未找到 SKILL.md：{src}")
    fm, body = load_frontmatter(entry)

    parts: list[str] = []
    parts.append("<!-- 由 rulai-skill td.py compile-prompt 生成。\n"
                 f"     mode={mode} 源={entry} 生成于 {now_iso()}\n"
                 "     这是压缩产物：完整分节与引用关系请以原技能包为准。 -->")
    parts.append(f"# {fm.get('title') or fm.get('name') or entry.parent.name}")
    if fm.get("description"):
        parts.append(f"> {str(fm['description']).strip()}")
    parts.append("")

    if mode in ("inline", "entry") and entry.is_file() and entry.name == "SKILL.md":
        parts.append(body.strip())

    inlined: list[str] = []
    if mode == "inline":
        base = entry.parent
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in INLINE_SUFFIXES:
                continue
            if p == entry or p.name in ("FIDELITY.md",) or MANIFEST_NAME in p.parts:
                continue
            rel = p.relative_to(base)
            t = read_text(p)
            if len(t) > max_ref_chars:
                t = t[:max_ref_chars] + f"\n\n<!-- 截断：原文件 {len(t)} 字符，仅内联前 {max_ref_chars} -->"
            inlined.append(str(rel))
            parts.append(f"\n---\n\n## 附：{rel}\n\n{t.strip()}")

    if mode == "cards":
        base = entry.parent
        for p in sorted(base.rglob("*.md")):
            if p.name in ("SKILL.md", "FIDELITY.md") or p == entry:
                continue
            f2, b2 = load_frontmatter(p)
            first = next((ln for ln in b2.splitlines() if ln.startswith("# ")), p.stem)
            desc = str(f2.get("description", "")).strip().replace("\n", " ")
            parts.append(f"\n- **{p.stem}** — {first.lstrip('# ').strip()}\n  {desc[:160]}")

    text = "\n".join(parts) + "\n"
    out_path = Path(out) if out else entry.with_suffix(".prompt.md")
    out_path.write_text(text, encoding="utf-8")
    result = {
        "schema": "rulai-skill/prompt-compile@1",
        "generated_at": now_iso(),
        "mode": mode,
        "entry": str(entry),
        "out": str(out_path),
        "inlined": inlined,
        "chars": len(text),
        "tokens": count_tokens(text),
        "counter": token_source(),
    }
    write_json(out_path.with_suffix(".prompt.json"), result)
    return result


def _find_entry(root: Path) -> Path | None:
    direct = root / "SKILL.md"
    if direct.exists():
        return direct
    cands = sorted(root.rglob("SKILL.md"))
    return cands[0] if cands else None
