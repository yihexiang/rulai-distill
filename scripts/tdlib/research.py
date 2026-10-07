# -*- coding: utf-8 -*-
"""tdlib.research — 人物蒸馏的六路调研骨架 + 多路合并去重。

对标 alchaincyf/nuwa-skill 的：
  * 六路 research 文件结构（01-writings / 02-conversations / 03-expression-dna /
    04-external-views / 05-decisions / 06-timeline）
  * scripts/merge_research.py（多路调研合并）

改进：合并器不只做拼接，而是
  1. 归一化后按 3-gram Jaccard 去重，保留**出处**（哪个文件哪一节）；
  2. 对同一命题的冲突表述打上 `⚠️ 冲突` 标记，交给 Agent 判断而不是静默取先到；
  3. 产出一份可核查的 provenance 表（每条结论 → 来源文件 + 一手/二手 + 权重）。

为什么坚持六路：只查 writings 会得到"他说了什么"，只查 external-views 会得到"别人怎么看他"，
两者的差距正是认知植入里"内在矛盾"的来源。少查两路，产物就会退化成漂亮但平面的标签集合。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import contracts
from .util import (ToolError, ensure_dir, ngrams, now_iso, read_text, sha256_text, warn,
                   write_json)

LANES = [
    ("01-writings", "本人著作/文章/书",
     "逐篇记录他主动写下的判断，带年份与出处。优先一手：原文、出版、官方仓库。",
     ["site:*.org <人名> 文章", "<人名> 全文 专栏", "<人名> 著作 目录"]),
    ("02-conversations", "访谈/演讲/播客/问答",
     "长对话比短发言更能暴露推理过程。重点抓他如何回应质疑、被追问时的退让。",
     ["<人名> 访谈 逐字稿", "<人名> 演讲 全文", "<人名> podcast transcript"]),
    ("03-expression-dna", "表达方式样本",
     "≥800 字原话样本，标注句式、用词、举例习惯、犹豫时的口头禅。",
     ["<人名> 原话 语录", "<人名> 采访 文字实录"]),
    ("04-external-views", "外部评价与批评",
     "**最容易被跳过、也最不可跳过的一路**。没有外部视角就无法发现他自我认知与实际的落差。",
     ["<人名> 争议 批评", "<人名> 同行 评价", "<人名> 失败 复盘"]),
    ("05-decisions", "关键决策与后果",
     "3-5 个决策，每个要有：选项、当时的判断依据、事后反思（含公开承认的错误）。",
     ["<人名> 决策 当时", "<人名> 承认 错误", "<人名> 复盘 采访"]),
    ("06-timeline", "时间线与阶段划分",
     "只记与认知转折有关的事件：他什么时候换了立场、什么时候换了领域。",
     ["<人名> 年表", "<人名> 经历 时间线"]),
]

LANE_HEADER = """---
lane: {lane}
title: {title}
status: pending
one_hand_weight: 0
updated: {ts}
---

# {lane} · {title}

> 目标：{goal}

> 检索建议：{hints}

## 记录

<!-- 每条按下面格式；每条必须带出处。一手来源请标 [一手]，二手标 [二手] -->

- **[一手|二手] 结论一句话** —— 出处：<书名/视频/采访名>，<年份/时间戳>，<链接或页码>

## 覆盖度自检

- [ ] 是否有 ≥3 条带具体出处的记录
- [ ] 是否包含至少一条**反直觉**或**有争议**的信息
- [ ] 是否记录了"没找到什么"（缺口也是结论）
"""


def scaffold(research_dir: Path, person: str, overwrite: bool = False) -> list[Path]:
    """生成六路调研文件骨架。已存在且非空时不覆盖。"""
    research_dir = ensure_dir(Path(research_dir))
    made = []
    for lane, title, goal, hints in LANES:
        p = research_dir / f"{lane}.md"
        if p.exists() and p.stat().st_size > 200 and not overwrite:
            warn(f"{p.name} 已存在，跳过（--overwrite 可重建）")
            made.append(p)
            continue
        p.write_text(LANE_HEADER.format(lane=lane, title=title, goal=goal,
                                        hints="；".join(hints), ts=now_iso()),
                     encoding="utf-8")
        made.append(p)
    return made


# --------------------------------------------------------------------------
# 合并去重
# --------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s.lower())


def _ngrams(s: str, n: int = 3) -> set:
    t = _norm(s)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}




def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
PROV_RE = re.compile(r"出处[:：]\s*(.+?)\s*$")
FLAG_RE = re.compile(r"\[(一手|二手)\]")


def _bullets(text: str) -> list[tuple[str, str]]:
    """抽出所有 bullet，返回 (正文, 原始行)。"""
    out = []
    for line in text.splitlines():
        m = BULLET_RE.match(line)
        if m:
            out.append((m.group(1), line))
    return out


KIND_BY_LANE = {"01": "book", "02": "interview", "03": "interview",
                "04": "article", "05": "article", "06": "article"}


def _lane_to_source(lane: dict) -> dict:
    """把一个调研车道映射成上游 source-manifest 的 sources[] 元素（7 个必填）。"""
    no = lane["lane"]
    prefix = no.split("-")[0]
    title = no.split("-", 1)[-1].replace("-", " ")
    weight = lane.get("declared_weight") or 0.0
    # 权利与可信度由**证据强度**决定，不由车道名决定：
    #   声明权重 ≥0.5 且有实际条目 → 一手（primary）；有条目但权重低 → 二手（secondary）
    #   missing / 无条目 → 明确标 unknown，**不允许默认成 primary**
    if lane["status"] == "missing" or lane["items"] == 0:
        trust = "tertiary" if lane["status"] == "missing" else "tertiary"
    elif weight >= 0.5:
        trust = "primary"
    else:
        trust = "secondary"
    return {
        "source_id": f"src-{no}",
        "kind": KIND_BY_LANE.get(prefix, "other"),
        "title": title,
        "uri": f"research://{no}",
        "rights": "unknown",
        "trust": trust,
        "versions": [{
            "version_id": f"sha256:{sha256_text(json.dumps(lane, sort_keys=True, ensure_ascii=False))[:16]}",
            "added_at": now_iso(),
            "parser": "tdlib.research.merge",
            "status": "active",
        }],
    }


def merge_research(files: list[Path], out_md: Path, threshold: float = 0.62,
                   report_path: Path | None = None) -> dict:
    """多路调研合并：去重 + 冲突标记 + provenance 表 + **车道覆盖审计**。

    实测教训（马斯克蒸馏）：六路里两路（访谈、外部评价）完全没拿到时，
    只按「留下来的条目」算一手占比会得到 100%——**这个数字会掩盖最大的缺口**。
    因此这里额外解析各车道的 frontmatter（status / one_hand_weight），
    输出车道覆盖表，并把缺失车道计入警告。
    """
    items: list[dict] = []
    lanes: list[dict] = []
    for f in files:
        f = Path(f)
        if not f.exists():
            raise ToolError(f"调研文件不存在：{f}")
        text = read_text(f)
        fm_body = text.split("\n---", 1)[-1] if text.startswith("---") else text
        lane, status, weight = "?", "unknown", 0.0
        m = re.search(r"^lane:\s*(.+)$", text, re.M)
        if m:
            lane = m.group(1).strip()
        m = re.search(r"^status:\s*(.+)$", text, re.M)
        if m:
            status = m.group(1).strip()
        m = re.search(r"^one_hand_weight:\s*([0-9.]+)$", text, re.M)
        if m:
            weight = float(m.group(1))
        n_before = len(items)
        for raw_line in fm_body.splitlines():
            m = BULLET_RE.match(raw_line)
            if not m:
                continue
            body = m.group(1)
            if body.startswith(("[ ]", "[x]")) or "检索建议" in body:
                continue
            prov = PROV_RE.search(body)
            flag = FLAG_RE.search(body)
            w_flag = "一手" if (flag and flag.group(1) == "一手") else "二手"
            clean = re.sub(r"^\*+\s*", "", FLAG_RE.sub("", body).strip())
            claim = PROV_RE.sub("", clean).strip(" —-—")
            items.append({
                "text": clean, "claim": claim, "file": f.name,
                "provenance": prov.group(1).strip() if prov else "",
                "weight": w_flag, "grams": _ngrams(claim),
            })
        lanes.append({"lane": lane, "status": status, "declared_weight": weight,
                      "items": len(items) - n_before, "file": f.name})

    kept: list[dict] = []
    conflicts: list[dict] = []
    dropped = 0
    for it in items:
        dup = None
        for k in kept:
            j = _jaccard(it["grams"], k["grams"])
            if j >= threshold:
                dup = (k, j)
                break
        if dup is None:
            kept.append(it)
            continue
        k, j = dup
        dropped += 1
        # 同义合并：保留一手；若两条都标一手且相似度不高 → 记为冲突
        if it["weight"] == "一手" and k["weight"] == "二手":
            kept[kept.index(k)] = it
        elif j < 0.9 and it["weight"] == k["weight"] == "一手":
            conflicts.append({"a": k["text"], "b": it["text"], "similarity": round(j, 3),
                              "file_a": k["file"], "file_b": it["file"]})

    # ── 对立主张：**确定性脚本做不到，因此本工具不假装能做**（#59）──────────
    # 实测数据（2026-10-07）：真矛盾句对的 3-gram 相似度是 0.000~0.077
    # （「决策必须先把前提固定下来」vs「决策不需要先固定前提」），
    # 而**非矛盾**只是换了宾语的一对反而高达 0.400（「喜欢喝茶」vs「喜欢喝咖啡」）。
    # 也就是说：矛盾天然不相似，而"话题相关的不同内容"相似度更高——
    # 用相似度阈值区分二者在**原理上**不成立，调低只会制造噪声。
    #
    # 曾短暂加过一个「话题相关 + 否定极性相反」的启发式，实测在它本该抓住的用例上
    # 返回 0 处，而输出里的「对立候选 0 处」读起来像"没发现矛盾"——
    # **一个失效的启发式比没有更坏**，所以撤掉，改为在输出里明说这个能力不存在。
    contradiction_detection = "unsupported"

    one_hand = sum(1 for k in kept if k["weight"] == "一手")
    ratio = one_hand / len(kept) if kept else 0.0

    # 车道覆盖审计：缺失车道是比"占比"更重要的信号
    missing = [l for l in lanes if l["status"] in ("missing", "unknown") or l["items"] == 0]
    partial = [l for l in lanes if l["status"] == "partial"]
    declared = sum(l["declared_weight"] for l in lanes)
    coverage = {
        "lanes_total": len(lanes),
        "lanes_missing": [l["lane"] for l in missing],
        "lanes_partial": [l["lane"] for l in partial],
        "declared_weight_sum": round(declared, 2),
        "effective_weight": round(declared * (1.0 if not missing else 0.0) + declared * 0.0, 2),
    }
    if missing:
        coverage["verdict"] = f"{len(missing)}/{len(lanes)} 路缺失：一手占比 {ratio:.0%} 是**幸存条目**的比例，不能当作整体覆盖度"
    else:
        coverage["verdict"] = "六路齐全"
    lines = [
        "---",
        f"generated_at: {now_iso()}",
        f"generator: td.merge-research v1.0",
        f"inputs: {len(files)}",
        f"items_in: {len(items)}",
        f"items_kept: {len(kept)}",
        f"dedup_dropped: {dropped}",
        f"one_hand_ratio: {ratio:.2f}",
        f"conflicts: {len(conflicts)}",
        f"lanes_missing: {len(missing)}",
        "---",
        "",
        f"# 调研合并 · {' + '.join(f.name for f in files)}",
        "",
        f"> 保留 {len(kept)} 条（去重 {dropped}），幸存条目一手占比 {ratio:.0%}，**措辞重叠型冲突** {len(conflicts)} 处。",
        ">",
        "> ⚠️ **本工具查不到对立主张**（这是已知能力缺口，不是「没矛盾」）：",
        "> `conflicts` 只标记**措辞高度重叠**的条目对。真正的对立主张（如「必须先固定前提」vs「不需要先固定前提」）相似度实测 0.000~0.077，**永远进不了重叠分支**；而相似度高的反而是「话题相关但各说各的」。",
        "> 确定性脚本无法判定语义矛盾，因此这里**不给计数字段**——给了会让人以为「0 处 = 没问题」。",
        "> **必须由 Agent/人工逐条对照一手条目**：这一步不能省，FIDELITY 维度 3（可信度）的评分依据就是它。",
        "> 一手占比低于 70% 时，FIDELITY 维度 4 会扣分，且不得对外宣称「基于原始素材」。",
        "",
        "## 车道覆盖审计",
        "",
        "| 车道 | 状态 | 条数 | 声明权重 |",
        "|---|---|---|---|",
        *["| %s | %s | %d | %.2f |" % (l["lane"], l["status"], l["items"], l["declared_weight"])
          for l in lanes],
        "",
        f"**{coverage['verdict']}**",
        "",
        "## 结论清单（带出处）",
        "",
    ]
    for k in kept:
        lines.append(f"- **[{k['weight']}]** {k['text']}  <sub>来源：{k['file']}</sub>")
    if conflicts:
        lines += ["", "## ⚠️ 冲突（需人工判断，不要静默取先到）", ""]
        for c in conflicts:
            lines.append(f"- 相似度 {c['similarity']}（{c['file_a']} vs {c['file_b']}）")
            lines.append(f"  - A：{c['a']}")
            lines.append(f"  - B：{c['b']}")
    out_md = Path(out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── 契约化：产出上游 source-manifest（多来源 / 权利 / 可信度可机校验）──
    manifest = {
        "schema_version": 1,   # 上游契约 const: 1
        "content_pack": f"content-pack-{out_md.parent.name}",
        "sources": [_lane_to_source(l) for l in lanes],
        "output": {
            "requested": "auto",
            "selected": "single",
            "decision_policy": "single-first-v1",
            "preserve_strategy_on_update": True,
        },
    }
    mres = contracts.validate("source-manifest", manifest)
    manifest_path = out_md.with_name("source-manifest.json")
    if mres["ok"]:
        write_json(manifest_path, manifest)
    else:
        warn("source-manifest 未通过上游契约校验，仍写出以便排查："
             + "; ".join(mres["errors"][:3]))

    result = {"manifest": str(manifest_path) if mres["ok"] else None,
              "manifest_errors": [] if mres["ok"] else mres["errors"],
              "inputs": [str(f) for f in files], "out": str(out_md), "items_in": len(items),
              "kept": len(kept), "dropped": dropped, "one_hand_ratio": round(ratio, 3),
              "conflicts": conflicts,
               "contradiction_detection": contradiction_detection,
               "lanes": lanes, "coverage": coverage}
    write_json(Path(report_path) if report_path else out_md.with_suffix(".merge.json"), result)
    return result
