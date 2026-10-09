# -*- coding: utf-8 -*-
"""tdlib.validate — 技能卡静态校验：frontmatter / 死链 / UTF-8 / 步骤禁令 / 结构完整度 / 来源占比。

对标三个来源的校验能力并合并到一处：
  * cangjie `validate_skill_pack.py`：路径穿越、符号链接、frontmatter、编译产物完整性
  * yeadon  `quality_check.py`：认知植入结构、显式步骤检测
  * nuwa    `quality_check.py`：一手来源占比、调研来源存在性

额外补的（本技能自创）：
  * description 必须声明「不做/不适用」（防抢调用）
  * E 段必须有完成标准（可执行性硬门槛）
  * 交叉引用完整性：contrasts-with 指向的 slug 必须真实存在
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import (iter_links, load_frontmatter, read_text, safe_target, warn)

REQUIRED_FM = ["name", "description"]
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HARD_STEP_RE = re.compile(r"(?im)^\s*(?:step\s*\d|第[一二三四五六七八九十]+步\s*[:：]|\d+\.\s)")
PERSONA_SECTION_RE = re.compile(r"(?m)^#{1,4}\s*我看问题的方式.*?$([\s\S]*?)(?=^#{1,4}\s|\Z)")
# 段标题必须兼容中英双语与带括号注释的写法。
# 交叉互评实测：cangjie 的产物写 "## E — 可执行步骤 (Execution)"，
# 只匹配 "E — Execution" 会把它误报成"未发现 E 段"——**假阳性比漏报更坏**，
# 因为它会让健康的产品看起来有病。
E_SECTION_RE = re.compile(r"(?m)^#+\s*E\s*[—-]\s*(?:Execution|可执行步骤)")
B_SECTION_RE = re.compile(r"(?m)^#+\s*B\s*[—-]\s*(?:Boundary|边界)")
SOURCE_KEYS = re.compile(
    r"source_locator|source_book|source_chapter|source_manifest|素材来源|^#{1,4}\s*来源",
    re.M)
ONE_HAND_RE = re.compile(r"\[一手\]|一手来源合计权重|coverage")

# 这些是流水线自身的产物/文档，不是技能卡
NON_CARD_DOCS = {"FIDELITY.md", "SOURCES.md", "BOOK_OVERVIEW.md", "README.md",
                 "CHANGELOG.md", "TEST-SUITE.md", "TEST-SUITE.yaml"}


def _is_skill_doc(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if "skills" not in parts or path.name in NON_CARD_DOCS:
        return False
    # references/ 下的 .md 是卡片的参考资料，不是卡片本身。
    if "references" in parts:
        return False
    # SKILL.md 恒为卡片（哪怕 frontmatter 坏了，也要让 check_card 去报错，不能静默放过）。
    if path.name == "SKILL.md":
        return True
    # 复审：技能目录**根级**还有一批辅助文档（VERIFY.md / COVERAGE.md / …），
    # 它们被当成卡片校验会因缺 frontmatter 而误判「不允许发布」（guoxue zhouyi 实测 error 6）。
    # 判据用「有没有 frontmatter」而不是硬编码文件名——每加一份新辅助文档不会再漏。
    try:
        fm, _ = load_frontmatter(path)
    except Exception:  # noqa: BLE001 —— frontmatter 坏了仍当卡片，让 check_card 去报错
        return True
    return bool(fm.get("name") or fm.get("description"))


def iter_markdown(base: Path, skip_dirs: tuple[str, ...] = (".td", ".td_snapshots", ".git")):
    for p in sorted(base.rglob("*.md")):
        if any(part in skip_dirs for part in p.parts):
            continue
        yield p


def check_dead_links(base: Path) -> list[tuple[str, str, str]]:
    problems = []
    for md in iter_markdown(base):
        try:
            _, body = load_frontmatter(md)
        except Exception as e:  # noqa: BLE001
            problems.append(("error", _rel(md, base), str(e)))
            continue
        for tgt in iter_links(body):
            try:
                p = safe_target(md.parent, tgt)
            except Exception as e:  # noqa: BLE001
                problems.append(("error", _rel(md, base), str(e)))
                continue
            if not p.exists():
                problems.append(("error", _rel(md, base), f"死链：{tgt}"))
    return problems


def check_card(path: Path, base: Path, known_slugs: set[str] | None = None) -> list[tuple[str, str]]:
    """返回 [(级别, 说明)]，级别 ∈ {error, warn}。"""
    rel = _rel(path, base)
    out: list[tuple[str, str]] = []
    fm, body = load_frontmatter(path)

    for k in REQUIRED_FM:
        if not fm.get(k):
            out.append(("error", f"frontmatter 缺字段：{k}"))
    if fm.get("name") and not KEBAB_RE.match(str(fm["name"])):
        out.append(("error", f"name 必须是 kebab-case：{fm.get('name')}"))

    desc = str(fm.get("description", ""))
    if len(desc) < 40:
        out.append(("warn", "description 过短（<40 字），触发边界写不下"))
    if not re.search(r"不做|不适用|不要用于|不用于", desc):
        out.append(("warn", "description 未声明『不做/不适用』，容易被邻近技能抢调用"))

    # 交叉引用必须指向真实存在的 slug
    for field in ("depends_on", "composes_with", "contrasts_with"):
        val = fm.get(field)
        if isinstance(val, list) and known_slugs:
            for dep in val:
                if dep not in known_slugs:
                    out.append(("warn", f"{field} 指向不存在的 slug：{dep}"))

    is_persona = bool(fm.get("subject_type") == "person" or fm.get("material_type") == "person")

    if is_persona:
        if "你不是在模仿语气" not in body:
            out.append(("error", "人物卡首句缺少『认知植入而非角色扮演』声明"))
        sec = PERSONA_SECTION_RE.search(body)
        if not sec:
            out.append(("error", "人物卡缺少『我看问题的方式』段"))
        else:
            hits = [h.strip() for h in HARD_STEP_RE.findall(sec.group(1))]
            if hits:
                out.append(("error", f"『我看问题的方式』含显式步骤 {hits[:3]} —— 会退化成 SOP，请改为判断句"))
        for label, pat, lo in (("信念及其来源", r"信念及其来源", 3), ("认知边界", r"我明确不懂的", 2),
                               ("内在矛盾", r"内在矛盾", 1), ("红线", r"我绝不会做的事", 3)):
            if pat not in body:
                out.append(("error", f"人物卡缺少『{label}』段"))
        if not ONE_HAND_RE.search(body):
            out.append(("warn", "人物卡未见一手来源权重声明，FIDELITY 维度 4 会扣分"))
        # 人物卡**不能**有 E 段：模板明令禁止显式步骤（写了就退化成 SOP）。
        # 因此 E/B 段检查只适用于能力卡——否则校验器会自相矛盾地要求一个被禁止的东西。
        return out

    if E_SECTION_RE.search(body):
        if "完成标准" not in body:
            out.append(("error", "E 段存在但没有『完成标准』——未通过可执行性检查"))
        steps = len(re.findall(r"(?m)^\*\*Step\s*\d", body))
        if steps == 0:
            out.append(("warn", "E 段未使用 `**Step N · 名字**` 结构，难以机械核对"))
        elif steps > 6:
            out.append(("warn", f"E 段有 {steps} 步，建议拆成两张卡（>6 步说明职责过宽）"))
        if not B_SECTION_RE.search(body):
            out.append(("warn", "缺少 B（边界）段，失败模式无处登记"))
        elif "失败模式" not in body:
            out.append(("error", "B 段存在但没有『失败模式』——返工的主要来源没被记录"))
    else:
        out.append(("warn", "未发现 E — Execution 段（能力卡六段结构不完整）"))

    if not SOURCE_KEYS.search(body) and not any(
            fm.get(k) for k in ("source_locator", "source_book", "source_chapter", "material", "material_type")):
        out.append(("warn", "缺少可溯源定位（source_locator / source_book / source_chapter / 素材来源）"))
    return [(lvl, f"[{rel}] {msg}") for lvl, msg in out]


def _rel(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# bundle 级校验
# --------------------------------------------------------------------------
def collect_slugs(bundle_dir: Path) -> set[str]:
    import json
    bj = bundle_dir / "bundle.json"
    if not bj.exists():
        return set()
    try:
        data = json.loads(bj.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {s.get("slug") for s in data.get("skills", []) if s.get("slug")}


def validate_path(target: Path) -> tuple[list[tuple[str, str, str]], dict]:
    """校验文件或目录，返回 (problems, stats)。"""
    target = Path(target)
    problems: list[tuple[str, str, str]] = []
    stats = {"cards": 0, "docs": 0, "errors": 0, "warns": 0}

    if target.is_file():
        base, docs = target.parent, [target]
    else:
        base = target
        docs = list(iter_markdown(target))

    slugs = collect_slugs(base) if base.is_dir() else set()

    for md in docs:
        if target.is_file() or _is_skill_doc(md):
            stats["cards"] += 1
            for lvl, msg in check_card(md, base, slugs):
                problems.append((lvl, _rel(md, base), msg.split("] ", 1)[-1]
                                 if msg.startswith("[") else msg))
        else:
            stats["docs"] += 1

    if target.is_dir():
        problems.extend(check_dead_links(target))
        problems.extend(check_bundle_json(target))

    stats["errors"] = sum(1 for p in problems if p[0] == "error")
    stats["warns"] = sum(1 for p in problems if p[0] == "warn")
    return problems, stats


def check_bundle_json(bundle_dir: Path) -> list[tuple[str, str, str]]:
    import json
    bj = bundle_dir / "bundle.json"
    if not bj.exists():
        # 只有「看起来像 bundle」的目录（带 skills/）才提示；技能包本身不是 bundle
        if (bundle_dir / "skills").is_dir():
            return [("warn", "bundle.json", "缺少 bundle.json，无法用 compile 发布")]
        return []
    try:
        bundle = json.loads(bj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [("error", "bundle.json", f"JSON 解析失败：{e.msg}（行 {e.lineno}）")]
    out: list[tuple[str, str, str]] = []
    for k in ("schema", "version", "source", "skills"):
        if k not in bundle:
            out.append(("error", "bundle.json", f"缺顶层字段：{k}"))
    seen: set[str] = set()
    for s in bundle.get("skills", []):
        slug, src = s.get("slug"), s.get("src")
        if not slug or not src:
            out.append(("error", "bundle.json", f"skill 条目缺 slug/src：{s}"))
            continue
        if slug in seen:
            out.append(("error", "bundle.json", f"slug 重复：{slug}"))
        seen.add(slug)
        try:
            p = safe_target(bundle_dir, src)
        except Exception as e:  # noqa: BLE001
            out.append(("error", "bundle.json", f"[{slug}] {e}"))
            continue
        if not p.exists():
            out.append(("error", "bundle.json", f"[{slug}] src 不存在：{src}"))
        elif p.is_symlink():
            out.append(("error", "bundle.json", f"[{slug}] src 是符号链接，拒绝"))
    return out


# --------------------------------------------------------------------------
# 来源占比（nuwa 能力）
# --------------------------------------------------------------------------
def check_source_ratio(path: Path, min_ratio: float = 0.7) -> tuple[float, list[str]]:
    """从 FIDELITY.md / SOURCES.md / 人物卡里读一手来源占比。"""
    text = read_text(path)
    notes: list[str] = []
    m = re.search(r"一手来源合计权重[：:]\s*([0-9.]+)", text)
    if m:
        return float(m.group(1)), notes
    m = re.search(r"one_hand_ratio[：:]\s*([0-9.]+)", text)
    if m:
        return float(m.group(1)), notes
    one = len(re.findall(r"\[一手\]", text))
    two = len(re.findall(r"\[二手\]", text))
    if one + two == 0:
        notes.append("未找到一手/二手来源标记（需在 FIDELITY 或 SOURCES 中声明）")
        return 0.0, notes
    return one / (one + two), notes
