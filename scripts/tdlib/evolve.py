# -*- coding: utf-8 -*-
"""tdlib.evolve — 增量维护：diff / impact / repair / update / patch。

对标 kangarooking/cangjie-skill 的 diff_sources.py、impact_analysis.py、repair_flow.py、
update_flow.py、apply_skill_patch.py。合并为一个模块，但**保持每个动作可单独执行、可回滚**。

核心不变量：任何写操作默认 dry-run；真正落盘必须显式 --apply，且落盘前自动打快照。
理由：蒸馏产物的价值在人工精修，脚本擅自"修好"往往等于毁掉。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import contracts
from .util import (MANIFEST_NAME, ToolError, dump_frontmatter, ensure_dir, info,
                   load_frontmatter, now_id, now_iso, read_json, read_text, sha256_of, warn,
                   write_json)

def _pack_version(root: Path) -> str:
    """一个包目录的版本标识：manifest 里的 bundle_version，没有则用内容哈希兜底。"""
    mf = root / MANIFEST_NAME
    if mf.exists():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            v = data.get("bundle_version")
            if v:
                return f"v{v}"
        except (json.JSONDecodeError, OSError):
            pass
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.md")):
        h.update(sha256_of(p).encode())
    return f"sha256:{h.hexdigest()[:16]}"


REL_KEYS = ("depends-on", "depends_on", "composes-with", "composes_with",
            "contrasts-with", "contrasts_with")


def _cards(root: Path) -> dict[str, Path]:
    root = Path(root)
    out: dict[str, Path] = {}
    for p in root.rglob("SKILL.md"):
        if any(x in p.parts for x in (".td", ".td_snapshots")):
            continue
        out[p.parent.name] = p
    for p in root.rglob("*.md"):
        if any(x in p.parts for x in (".td", ".td_snapshots")):
            continue
        if p.name in ("SKILL.md", "FIDELITY.md", "README.md", "SOURCES.md"):
            continue
        out.setdefault(p.stem, p)
    return out


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------
def _sections(text: str) -> dict[str, str]:
    secs, cur, buf = {}, "(preamble)", []
    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)$", line.strip())
        if m:
            secs[cur] = "\n".join(buf).strip()
            cur, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    secs[cur] = "\n".join(buf).strip()
    return secs


def diff_sources(a: Path, b: Path) -> dict:
    ca, cb = _cards(Path(a)), _cards(Path(b))
    added = sorted(set(cb) - set(ca))
    removed = sorted(set(ca) - set(cb))
    changed, unchanged = [], []
    for slug in sorted(set(ca) & set(cb)):
        ta, tb = read_text(ca[slug]), read_text(cb[slug])
        if sha256_of(ca[slug]) == sha256_of(cb[slug]):
            unchanged.append(slug)
            continue
        sa, sb = _sections(ta), _sections(tb)
        mod = [s for s in sorted(set(sa) | set(sb)) if sa.get(s, "") != sb.get(s, "")]
        lines_added = sum(1 for l in difflib.unified_diff(sa.get("__x__", "").splitlines(),
                                                          sb.get("__x__", "").splitlines()))
        changed.append({"slug": slug, "sections_changed": mod,
                        "chars": [len(ta), len(tb)]})
    # ── 契约化：产出上游 change-set（版本间差异可机校验，而不只是给人看的报告）──
    cs = {
        "schema_version": 1,
        "change_id": f"chg-{now_id()}",
        "content_pack": f"content-pack-{Path(a).name}",
        "created_at": now_iso(),
        "base_version": _pack_version(Path(a)),
        "new_version": _pack_version(Path(b)),
        "changes": (
            [{"change_type": "additive", "chunk_id": slug,
              "new_hash": sha256_of(cb[slug]), "heading_path": []} for slug in added]
            + [{"change_type": "deletion", "chunk_id": slug,
                "old_hash": sha256_of(ca[slug]), "heading_path": []} for slug in removed]
            + [{"change_type": "modified", "chunk_id": c["slug"],
                "old_hash": sha256_of(ca[c["slug"]]), "new_hash": sha256_of(cb[c["slug"]]),
                "heading_path": c["sections_changed"][:5]} for c in changed]
        ),
        "summary": {"added": len(added), "removed": len(removed), "changed": len(changed),
                    "unchanged": len(unchanged)},
    }
    cres = contracts.validate("change-set", cs)
    cs_path = Path(b) / "change-set.json"
    if cres["ok"]:
        write_json(cs_path, cs)
    else:
        warn("change-set 未通过上游契约校验：" + "; ".join(cres["errors"][:3]))

    return {
        "schema": "rulai-skill/diff@1",
        "change_set": str(cs_path) if cres["ok"] else None,
        "change_set_errors": [] if cres["ok"] else cres["errors"],
        "generated_at": now_iso(),
        "a": str(a), "b": str(b),
        "added": added, "removed": removed,
        "changed": changed, "unchanged": unchanged,
        "summary": {"added": len(added), "removed": len(removed),
                    "changed": len(changed), "unchanged": len(unchanged)},
    }


# --------------------------------------------------------------------------
# impact
# --------------------------------------------------------------------------
def impact_analysis(root: Path, slug: str) -> dict:
    root = Path(root)
    hits = []
    for name, path in _cards(root).items():
        fm, body = load_frontmatter(path)
        refs: list[str] = []
        for k in REL_KEYS:
            v = fm.get(k)
            if isinstance(v, list):
                refs += [str(x) for x in v]
            elif isinstance(v, str):
                refs.append(v)
        if name != slug:
            refs += re.findall(rf"`{re.escape(slug)}`", body)
        if refs:
            hits.append({"skill": name, "file": str(path), "refs": sorted(set(refs))})
    return {"schema": "rulai-skill/impact@1", "generated_at": now_iso(),
            "target": slug, "affected": hits, "affected_count": len(hits)}


# --------------------------------------------------------------------------
# repair（保守：只做无争议的机械修复）
# --------------------------------------------------------------------------
def repair(dirpath: Path, apply: bool = False) -> dict:
    """可自动修的项：文件缺失 frontmatter 结束符、name 与目录/slug 不一致、
    CRLF → LF、行尾空白、文末缺换行。**不自动补内容**（补内容=编造）。"""
    fixes: list[dict] = []
    for name, path in _cards(Path(dirpath)).items():
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        new = text
        notes = []
        if "\r\n" in new:
            new = new.replace("\r\n", "\n")
            notes.append("CRLF→LF")
        if new and not new.endswith("\n"):
            new += "\n"
            notes.append("补文末换行")
        if re.search(r"[ \t]+\n", new):
            new = re.sub(r"[ \t]+\n", "\n", new)
            notes.append("去行尾空白")
        fm, _ = load_frontmatter(path)
        if fm.get("name") and fm["name"] != name:
            notes.append(f"name {fm['name']} → {name}")
            new = dump_frontmatter({**fm, "name": name}, new.split("\n---", 1)[-1]
                                   if new.startswith("---") else new)
        if notes:
            fixes.append({"file": str(path), "notes": notes})
            if apply:
                path.write_text(new, encoding="utf-8")
    return {"schema": "rulai-skill/repair@1", "generated_at": now_iso(),
            "applied": apply, "fixable": fixes, "count": len(fixes)}


# --------------------------------------------------------------------------
# patch
# --------------------------------------------------------------------------
SECTION_RE = r"(?m)^(#{1,4})\s+%s.*$"


def apply_patch(card: Path, patch: dict, apply: bool = False) -> dict:
    """patch = {"set_frontmatter": {...}, "replace_section": {"标题": "新正文"},
                 "append_section": {"标题": "正文"}}"""
    path = Path(card)
    text = read_text(path)
    fm, body = load_frontmatter(path)
    changes: list[str] = []
    new_fm = {**fm, **patch.get("set_frontmatter", {})}
    for k, v in patch.get("set_frontmatter", {}).items():
        if fm.get(k) != v:
            changes.append(f"frontmatter {k}: {fm.get(k)!r} → {v!r}")
    for title, content in (patch.get("replace_section") or {}).items():
        pat = SECTION_RE % re.escape(title)
        m = re.search(pat, body)
        if not m:
            raise ToolError(f"未找到章节：{title}", f"文件：{path}")
        start = m.start()
        nxt = re.search(r"(?m)^#{1,4}\s+", body[m.end():])
        end = m.end() + nxt.start() if nxt else len(body)
        head = body[start:m.end()]
        body = body[:start] + head + "\n\n" + content.strip() + "\n\n" + body[end:]
        changes.append(f"replace_section {title}")
    for title, content in (patch.get("append_section") or {}).items():
        body = body.rstrip() + f"\n\n## {title}\n\n{content.strip()}\n"
        changes.append(f"append_section {title}")
    if apply:
        path.write_text(dump_frontmatter(new_fm, body), encoding="utf-8")
    return {"file": str(path), "applied": apply, "changes": changes,
            "diff": list(difflib.unified_diff(text.splitlines(),
                                               dump_frontmatter(new_fm, body).splitlines(),
                                               lineterm=""))[:40]}


# --------------------------------------------------------------------------
# update
# --------------------------------------------------------------------------
def update_flow(bundle_dir: Path, out: Path, apply: bool = False) -> dict:
    """重新校验 + 重编译 + 产出变更报告（先 dry-run）。"""
    from .publish import compile_bundle, detect_local_edit, snapshot
    from .validate import validate_path

    bundle_dir, out = Path(bundle_dir), Path(out)
    problems, stats = validate_path(bundle_dir)
    errors = [p for p in problems if p[0] == "error"]
    pre = detect_local_edit(out) if out.exists() else []
    result: dict = {"validated": stats, "errors": errors, "local_edit": pre,
                    "applied": apply, "generated_at": now_iso()}
    if errors:
        warn(f"存在 {len(errors)} 个阻断性问题，未编译")
        return result
    if not apply:
        info("dry-run：加 --apply 才会真正编译")
        return result
    snap = snapshot(out, "before-update") if out.exists() else None
    result["compile"] = compile_bundle(bundle_dir, out, overwrite=True)
    result["pre_snapshot"] = snap
    return result
