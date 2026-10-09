# -*- coding: utf-8 -*-
"""tdlib.publish — 确定性编译与原子发布：staging 校验 → 快照 → rename 原子替换。

对标 kangarooking/cangjie-skill 的 compile_single.py / compile_pack.py，合并为
`compile --mode {pack,single}`：
  * pack   —— 每个能力一个独立 SKILL.md（默认）
  * single —— 编译为单一 SKILL.md + 能力卡目录（single-first 策略，见 strategy.py）

关键安全属性（cangjie 同样具备，rulai-distill 保留并强化）：
  * 拒绝绝对路径 / .. 逃逸 / 符号链接
  * FIDELITY 门槛不达标 → 拒绝发布（--force 可强发但 manifest 留 forced=true）
  * 发布前检测本地手工改动 → 拒绝静默覆盖（--overwrite 才放行）
  * 快照写在 target 的**兄弟目录**，因为 rename 原子替换会换掉整个 target 目录
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path

from . import contracts
from .fidelity import GRADES, parse_report
from .util import (MANIFEST_NAME, ToolError, ensure_dir, info, now_id, now_iso, ok,
                   read_json, safe_target, sha256_of, step, warn, write_json)

SKILL_SUFFIXES = (".md", ".json", ".yaml", ".yml")


class WriterLock:
    """同一目标同时只允许一个 writer。用 O_EXCL 创建锁文件，崩溃后可按 pid/时间人工清理。

    借鉴 kangarooking/cangjie-skill 的同名原语：两个进程同时 publish 到同一目录时，
    第二个会拿到半成品 target（rename 竞态），这类损坏事后极难排查。
    """

    def __init__(self, target: Path, name: str = ".td-write-lock"):
        self.path = Path(target).parent / (Path(target).name + name)
        self.acquired = False

    def __enter__(self):
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = self.path.read_text(encoding="utf-8").strip()
            except OSError:
                pid = "unknown"
            raise ToolError(
                f"目标正在被另一个写者占用：{self.path}",
                f"锁持有者 pid={pid}；若确认是崩溃残留，删除该锁文件后重试",
                f"锁文件位置：{self.path}")
        with os.fdopen(fd, "w") as f:
            f.write(f"pid={os.getpid()} at={now_iso()}")
        self.acquired = True
        return self

    def __exit__(self, *exc):
        if self.acquired:
            self.path.unlink(missing_ok=True)
        return False


def snap_root(target: Path) -> Path:
    return target.parent / (target.name + ".td_snapshots")


def detect_local_edit(target: Path) -> list[str]:
    changed: list[str] = []
    mf = target / MANIFEST_NAME
    if not mf.exists():
        return changed
    try:
        data = read_json(mf)
    except ToolError:
        return changed
    for rel, expect in (data.get("published_hashes") or {}).items():
        p = target / rel
        if not p.is_file():
            changed.append(f"{rel}（已删除）")
        elif sha256_of(p) != expect:
            changed.append(rel)
    return changed


def snapshot(target: Path, label: str = "") -> str:
    if not target.is_dir():
        raise ToolError(f"快照目标不是目录：{target}")
    sid = now_id()
    root = snap_root(target)
    dest = root / sid
    n = 2
    while dest.exists():
        dest = root / f"{sid}-{n}"
        n += 1
    ensure_dir(dest)

    files = [p for p in target.rglob("*") if p.is_file() and snap_root(target) not in p.parents]
    hashes = {}
    for p in files:
        rel = str(p.relative_to(target))
        hashes[rel] = sha256_of(p)
        outp = dest / "data" / rel
        ensure_dir(outp.parent)
        shutil.copy2(p, outp)
    write_json(dest / "SNAPSHOT.json", {
        "id": dest.name, "created_at": now_iso(), "label": label,
        "file_count": len(files), "hashes": hashes,
    })
    return dest.name


def rollback(target: Path, sid: str) -> dict:
    root = snap_root(target)
    if not root.is_dir():
        raise ToolError(f"没有快照目录：{root}", "先跑 `td.py snapshot <dir>` 建立基线")
    cands = sorted(d.name for d in root.iterdir() if (d / "SNAPSHOT.json").exists())
    if not cands:
        raise ToolError("没有任何可用快照", f"目录：{root}")
    if sid == "latest":
        sid = cands[-1]
    snap = root / sid
    if not (snap / "SNAPSHOT.json").exists():
        raise ToolError(f"快照不存在：{sid}", "可用快照：" + ", ".join(cands))
    meta = read_json(snap / "SNAPSHOT.json")

    pre = snapshot(target, f"before-rollback-to-{sid}")
    for p in list(target.rglob("*")):
        if p.is_file() and snap_root(target) not in p.parents:
            p.unlink()
    for d in sorted([d for d in target.rglob("*") if d.is_dir() and snap_root(target) not in d.parents],
                    key=lambda x: -len(x.parts)):
        try:
            d.rmdir()
        except OSError:
            pass
    data = snap / "data"
    if data.exists():
        for src in data.rglob("*"):
            if src.is_file():
                dst = target / src.relative_to(data)
                ensure_dir(dst.parent)
                shutil.copy2(src, dst)
    return {"restored": sid, "files": meta.get("file_count", "?"), "pre_snapshot": pre}


# --------------------------------------------------------------------------
def load_bundle(bundle_path: Path) -> dict:
    bj = Path(bundle_path) / "bundle.json"
    if not bj.exists():
        raise ToolError(f"缺少 bundle.json：{bj}", "td.py init <dir> 可生成模板")
    bundle = read_json(bj)
    for k in ("schema", "version", "source", "skills"):
        if k not in bundle:
            raise ToolError(f"bundle.json 缺顶层字段：{k}")
    return bundle


def compile_bundle(bundle_path: Path, out: Path, allow_grade: str | None = None,
                   force: bool = False, overwrite: bool = False,
                   mode: str = "pack", with_reports: bool = False) -> dict:
    """编译 bundle。

    with_reports=True：把每张卡的 FIDELITY 报告（若存在）一并放进产物
    （`skills/<slug>/FIDELITY.<ext>`），让质量证据**随包发布**（复审 #3）。
    默认 False，保持既有产物形状不变。
    """
    bundle_path = Path(bundle_path).resolve()
    out = Path(out).resolve()
    if not bundle_path.is_dir():
        raise ToolError(f"bundle 目录不存在：{bundle_path}")
    if out == bundle_path:
        raise ToolError("输出目录不能等于 bundle 目录", "换一个 --out")
    if bundle_path in out.parents:
        raise ToolError("输出目录不能位于 bundle 内部", "换一个 --out")

    bundle = load_bundle(bundle_path)
    min_grade = allow_grade or bundle.get("publish", {}).get("allow_grade_below", "B")
    entries = []
    sibling_srcs = {(bundle_path / "bundle.json").resolve()}
    for s in bundle["skills"]:
        if not s.get("slug"):
            raise ToolError(f"bundle.json 里有缺 slug 的条目：{s}")
        p = safe_target(bundle_path, s.get("src", ""))
        entries.append((s, p))
        sibling_srcs.add(p.resolve())

    staging = bundle_path / f".td_staging_{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        published: dict[str, str] = {}
        results = []
        fid_reports: dict[str, dict | None] = {}
        for s, src in entries:
            slug = s["slug"]
            if not src.exists():
                raise ToolError(f"[{slug}] 源文件不存在：{src}")
            if src.is_symlink():
                raise ToolError(f"[{slug}] 拒绝符号链接源文件：{src}")

            fm = _fm(src)
            if fm.get("name") and fm["name"] != slug:
                raise ToolError(f"[{slug}] frontmatter name 与 bundle slug 不一致：{fm.get('name')}")

            score, grade, rep_path, rep_dict = _fidelity_for(bundle_path, src, s)
            if score is None or grade is None:
                if not force:
                    raise ToolError(f"[{slug}] 缺少 FIDELITY 报告且未给 fidelity_score",
                                    f"先跑阶段 4b 生成 {src.parent / 'FIDELITY.md'}",
                                    "或临时应急：python3 scripts/td.py compile ... --force")
                warn(f"[{slug}] 无 FIDELITY 报告 —— --force 下发，标记为未质检")
                grade, score = "D", 0
            elif GRADES.get(grade, 0) < GRADES.get(min_grade, 0):
                if not force:
                    raise ToolError(f"[{slug}] FIDELITY {score} 分 {grade} 级，低于门槛 {min_grade}",
                                    "回到 stage 4b：每步补完成标准、B 段补失败模式、引语补出处",
                                    "确需强发：--force（manifest 会留 forced=true）")
                warn(f"[{slug}] FIDELITY {score} ({grade}) 低于门槛 {min_grade} —— 强制发布")

            dest = (staging / "skills" / slug) if mode == "pack" else (staging / "cards")
            ensure_dir(dest)
            outfile = dest / "SKILL.md" if mode == "pack" else dest / f"{slug}.md"
            shutil.copy2(src, outfile)
            published[str(outfile.relative_to(staging))] = sha256_of(outfile)
            for extra in sorted(src.parent.glob("*")):
                if not extra.is_file() or extra.name in ("SKILL.md", "FIDELITY.md", MANIFEST_NAME):
                    continue
                if extra.resolve() in sibling_srcs or extra.suffix not in SKILL_SUFFIXES:
                    continue
                shutil.copy2(extra, dest / extra.name)
                rel = str((dest / extra.name).relative_to(staging))
                published[rel] = sha256_of(dest / extra.name)
            # 报告随包发布：FIDELITY 报告（质量证据）随卡一并进产物。
            # 注意**不含**答案/诱饵等测试材料（那些会泄题）。
            if with_reports and rep_path and Path(rep_path).exists():
                rf = dest / ("FIDELITY" + Path(rep_path).suffix)
                shutil.copy2(rep_path, rf)
                rel = str(rf.relative_to(staging))
                published[rel] = sha256_of(rf)
            results.append({"slug": slug, "fidelity_score": score, "fidelity_grade": grade,
                            "report": str(rep_path) if rep_path else None})
            fid_reports[slug] = rep_dict

        if mode == "single":
            _write_single_entry(staging, bundle, results, published)

        manifest = {
            "schema": "rulai-distill/manifest/v1",
            "generator": "td.py compile",
            "mode": mode,
            "built_at": now_iso(),
            "bundle_version": bundle.get("version"),
            "source": bundle.get("source", {}),
            "min_grade_enforced": min_grade,
            "forced": bool(force),
            "with_reports": bool(with_reports),
            "skills": results,
            "published_hashes": published,
        }
        write_json(staging / MANIFEST_NAME, manifest)

        # ── 契约化：dependency-graph（能力之间的 depends_on/composes_with 关系可机校验）──
        dgraph = _dependency_graph(bundle, results, staging)
        dres = contracts.validate("dependency-graph", dgraph)
        if dres["ok"]:
            write_json(staging / "dependency-graph.json", dgraph)
        else:
            warn("dependency-graph 未通过上游契约校验：" + "; ".join(dres["errors"][:3]))

        reg = ensure_dir(staging / "registry")
        td_meta: dict = {"entries": {}}
        for r in results:
            entry = _registry_entry(bundle, r, manifest, mode, staging)
            res = contracts.validate("registry-entry", entry)
            if res["ok"]:
                contracts.write_verified("registry-entry", entry, reg, f"{r['slug']}.json")
                # 契约装不下的本包信息（FIDELITY 明细、素材、版本）走旁挂文件。
                # fidelity 为**结构化**：除 score/grade/report 外，含
                # eval_mode / dimensions / graders / cross_grader_gap / blocking_issues
                # （可从 FIDELITY 报告解析出的机器可读字段）。
                td_meta["entries"][r["slug"]] = {
                    "fidelity": {"score": r.get("fidelity_score"),
                                 "grade": r.get("fidelity_grade"),
                                 "report": r.get("report"),
                                 **_structured_fidelity(fid_reports.get(r["slug"]))},
                    "source": bundle.get("source", {}),
                    "bundle_version": bundle.get("version"),
                    "published_at": manifest["built_at"],
                }
            else:
                warn(f"[{r['slug']}] registry 登记不符合上游契约（仍写出供排查）："
                     + "; ".join(res["errors"][:3]))
                write_json(reg / f"{r['slug']}.json", entry)
        if td_meta.get("entries"):
            write_json(reg / "_td-meta.json", {
                "schema": "rulai-distill/registry-meta@1",
                "note": "registry-entry-v2 是 additionalProperties:false，"
                        "本包自有的质检与溯源信息只能旁挂在此文件",
                **td_meta,
            })

        pre = None
        if out.exists():
            changed = detect_local_edit(out)
            if changed and not overwrite:
                raise ToolError(f"检测到本地手工改动 {len(changed)} 处，拒绝静默覆盖：",
                                *changed[:8], *(["  ...还有更多"] if len(changed) > 8 else []))
            if changed:
                warn(f"检测到 {len(changed)} 处本地改动，--overwrite 已指定，将覆盖")
            pre = snapshot(out, f"before-compile-{bundle.get('version')}")

        ensure_dir(out.parent)
        with WriterLock(out):
            if out.exists():
                tmp_old = out.with_name(out.name + f".td_old_{os.getpid()}")
                os.rename(out, tmp_old)
                os.rename(staging, out)
                shutil.rmtree(tmp_old, ignore_errors=True)
            else:
                os.rename(staging, out)
        return {"out": str(out), "count": len(results), "mode": mode,
                "pre_snapshot": pre, "skills": results,
                "run_id": _dt.datetime.now().strftime("run-%Y%m%d-%H%M%S-%s")}
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


QUALITY_BY_GRADE = {"A": "verified", "B": "verified", "C": "community", "D": "experimental"}


def _detect_language(fm: dict, body_head: str = "") -> list[str]:
    """契约只接受 zh-CN / en / ja 三种标识。"""
    lang = str(fm.get("language") or "").lower()
    if lang.startswith("zh") or "zh" in lang:
        return ["zh-CN"]
    if lang.startswith("ja"):
        return ["ja"]
    cjk = sum(1 for ch in body_head[:2000] if "\u4e00" <= ch <= "\u9fff")
    return ["zh-CN"] if cjk > 100 else ["en"]


def _registry_entry(bundle: dict, r: dict, manifest: dict, mode: str, staging: Path) -> dict:
    """构造上游 registry-entry-v2 登记条目（15 个必填字段一个不少）。

    关键设计：quality 由 **FIDELITY 等级**推导，而不是人工填——否则"质检"会退化成装饰。
    """
    src = bundle.get("source", {}) or {}
    card = staging / "skills" / r["slug"] / "SKILL.md"
    fm = _fm(card) if card.exists() else {}
    head = card.read_text(encoding="utf-8")[:2000] if card.exists() else ""
    domains = [str(t) for t in (fm.get("tags") or []) if 2 <= len(str(t)) <= 30] or ["通用"]
    use_cases = _use_cases(fm, domains)
    grade = r.get("fidelity_grade") or "D"
    # 注意：registry-entry-v2 是 **additionalProperties: false**，
    # 多写一个字段就判不合规（实测踩过：我加了 fidelity/source/bundle_version 全被拒）。
    # 因此本包自有的质检信息**不能**塞在这里——改放到 registry/_td-meta.json 旁挂。
    return {
        "schema_version": 2,                    # 契约 const: 2（整数）
        "slug": r["slug"],
        "name": str(fm.get("title") or r["slug"])[:80],
        "summary": _summary(fm, src, r)[:240],
        "source_type": "bundled",
        "source_url": "https://github.com/yihexiang/rulai-distill",
        "skill_path": f"skills/{r['slug']}",
        "output_mode": "pack" if mode == "pack" else "single",
        "skill_count": 1,
        "entrypoint_count": 1,
        "capability_count": 1,
        "router_entrypoint": r["slug"],         # 必填：pack 模式的来源路由入口
        "domains": list(dict.fromkeys(domains))[:6],
        "language": _detect_language(fm, head),
        "status": "active" if grade in ("A", "B") else "experimental",
        "quality": QUALITY_BY_GRADE.get(grade, "experimental"),
        "use_cases": use_cases,
        "featured": False,
    }


def _summary(fm: dict, src: dict, r: dict) -> str:
    desc = str(fm.get("description") or "").strip()
    head = desc.splitlines()[0] if desc else ""
    base = head or f"由 rulai-distill 从《{src.get('material', '未知素材')}》蒸馏的能力卡"
    return f"{base}（FIDELITY {r.get('fidelity_score')}/{r.get('fidelity_grade')}）"


def _use_cases(fm: dict, domains: list[str]) -> list[str]:
    """从 description 的适用/不适用里切出 1-6 条使用场景（契约要求 4-100 字/条）。"""
    import re as _re
    desc = str(fm.get("description") or "")
    body = " ".join(ln for ln in desc.splitlines()
                    if not ln.lower().lstrip().startswith(("english", "不做", "不适用", "不用于")))
    out: list[str] = []
    for piece in _re.split(r"[。；;]|适用于：|、", body):
        piece = piece.strip().lstrip("-*• ").strip()
        if 4 <= len(piece) <= 100:
            out.append(piece)
        if len(out) >= 4:
            break
    if not out:
        out = [f"用于 {d} 相关场景的判断与执行" for d in domains[:2]]
    return list(dict.fromkeys(out))[:6]


REL_EDGE = {"depends_on": "depends_on", "composes_with": "composes_with",
            "contrasts_with": "compared_with"}


def _dependency_graph(bundle: dict, results: list, staging: Path) -> dict:
    """从各卡 frontmatter 的 depends_on / composes_with / contrasts_with 抽边。

    node_type 用契约枚举里的 capability / entrypoint；边类型用
    depends_on / composes_with / compared_with（对应我们的三级关系）。
    **指向不存在技能的边会被丢弃并在 orphans 里记账**——图里不能有悬空节点。
    """
    nodes = [{"node_id": r["slug"], "node_type": "capability",
              "label": r["slug"]} for r in results]
    known = {r["slug"] for r in results}
    edges, orphans = [], []
    for r in results:
        card = staging / "skills" / r["slug"] / "SKILL.md"
        if not card.exists():
            continue
        fm = _fm(card)
        for key, etype in REL_EDGE.items():
            val = fm.get(key)
            if isinstance(val, str):
                val = [val]
            for dep in (val or []):
                if dep in known:
                    edges.append({"from": dep, "to": r["slug"], "edge_type": etype,
                                  "evidence": f"{r['slug']}.frontmatter.{key}"})
                else:
                    orphans.append({"skill": r["slug"], "ref": dep, "field": key})
    return {
        "schema_version": 1,
        "content_pack": "content-pack-" + str(bundle.get("source", {}).get("material", "bundle"))[:40],
        "generated_by": "tdlib.publish.compile",
        "nodes": nodes,
        "edges": edges,
        "orphan_refs": orphans,
    }


def _fm(path: Path) -> dict:
    from .util import load_frontmatter
    return load_frontmatter(path)[0]


def _fidelity_for(bundle_dir: Path, src: Path, entry: dict):
    """返回 (score, grade, report_path, report_dict)。

    report_dict 供 registry 旁挂写出**结构化** FIDELITY（维度/评分者/交叉复核），
    不只是 score/grade 两个数——复审 #2「registry 结构化 fidelity」。
    """
    for cand in (src.parent / "FIDELITY.md", src.with_name("FIDELITY.md"),
                 bundle_dir / "fidelity" / f"{entry['slug']}.json",
                 bundle_dir / "fidelity" / f"{entry['slug']}.md"):
        if cand.exists():
            rep = parse_report(cand)
            return (rep.get("total", entry.get("fidelity_score")),
                    rep.get("grade", entry.get("fidelity_grade")), cand, rep)
    return entry.get("fidelity_score"), entry.get("fidelity_grade"), None, None


_STRUCT_KEYS = ("eval_mode", "total", "grade", "dimensions", "answerer", "graders",
                "cross_grader_gap", "unparsed_dims", "total_mismatch",
                "threshold_fragile", "blocking_issues")


def _structured_fidelity(rep: dict | None) -> dict:
    """从 FIDELITY 报告里取**机器可读**的子集，写进 registry 旁挂（不是散文）。"""
    if not rep:
        return {}
    return {k: rep[k] for k in _STRUCT_KEYS if k in rep and rep[k] not in (None, [], {})}


def _write_single_entry(staging: Path, bundle: dict, results: list, published: dict) -> None:
    """single 模式：额外生成一个路由入口 SKILL.md，把所有能力卡串成一张表。"""
    lines = [
        "---",
        "name: " + str(bundle.get("source", {}).get("material", "distilled-pack")).lower()
        .replace(" ", "-").replace("《", "").replace("》", "")[:40] + "-pack",
        "description: |",
        "  本包由 rulai-distill 蒸馏产出，包含以下能力的路由入口："
        + "、".join(r["slug"] for r in results[:6]),
        "  适用：在本包能力范围内的问题。不做：与上述能力无关的通用问答。",
        "---",
        "",
        f"# 路由入口 · {bundle.get('source', {}).get('material', '')}",
        "",
        "| 能力 | 何时用 | FIDELITY |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| `{r['slug']}` | 见该卡 A2 段 | {r['fidelity_score']} ({r['fidelity_grade']}) |")
    lines += ["", "> 单卡详情见 `cards/`。不确定该用哪张时，读各卡 A2 的『与邻近能力的区分』。"]
    p = staging / "SKILL.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    published["SKILL.md"] = sha256_of(p)
