# -*- coding: utf-8 -*-
"""tdlib.evalkit — FIDELITY 独立评测套件（eval-kit）：题库 / 盲测包 / 评分模板 / JSON 回传 / 分差门禁。

## 为什么有这一层（复审 P0）

复审指出本包最大的缺口是**独立质检闭环的产品化**：guoxue 三个真实 run 全部卡在
「第二评分员 / 交叉复核」，FIDELITY 的独立性此前**靠人组织**——谁是答题者、谁是评分者、
分数怎么回传、分差多大算分歧，全靠操作者临场拼。人一忙就退化成"自评自证"，
正是本包存在的理由被绕过的地方。

eval-kit 把这条闭环变成**一组有格式的 JSON 文件 + 一条命令**：

    eval-kit init  <卡片> --out <kit>        # 生成题库 / 答题模板 / 评分模板 / 工作流说明
    （独立答题 Agent 填 answers.json，两个独立评分 Agent 各填 scores-*.json）
    eval-kit check <kit> --answers a.json --scores s1.json s2.json --out FIDELITY.json
                                              # 校验格式 → 算分差门禁 → 产出 FIDELITY JSON

产出的 `<out>` 就是 `td.py gate` 直接吃的 FIDELITY JSON（符合 `schemas/fidelity.schema.json`），
并内嵌 `graders` + `cross_grader_gap`，所以 gate 能自动识别"已交叉复核"，无需再手填 `--scores`。

## 三条纪律（都是本项目自己被坑出来的）

1. **空集不得判通过**（缺陷 #12/#56 同型）：0 题、0 评分者、0 答案一律报错，不判 pass。
2. **问答/评分必须分离且留痕**：answers 必须带 `answerer`，scores 必须带 `grader`；
   缺一即无法证明独立，不得据此下"已质检"结论。
3. **题库只能算"种子"**：机械从卡片 description 生成的题**覆盖不到最关键的维度 3
   （边缘诚实度）**——那一维必须由人针对"素材未覆盖的领域"出题。故 `init` 显式标
   `needs_human_augmentation: true`，不假装自动生成就够用。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import fidelity as fid
from .util import ToolError, ensure_dir, read_text

KIT_SCHEMA = "rulai-distill/eval-kit@1"
QUESTIONS_SCHEMA = "rulai-distill/eval-kit-questions@1"
DIM_MAX = {k: mx for k, _pat, mx in fid.DIMS}


# --------------------------------------------------------------------------
# 题库生成（种子级）
# --------------------------------------------------------------------------
def _use_cases_from_desc(desc: str) -> list[str]:
    import re as _re
    out: list[str] = []
    for piece in _re.split(r"[。；;]|适用于：|适用：", desc):
        piece = piece.strip().lstrip("-*• ").strip()
        if 4 <= len(piece) <= 100 and not piece.lower().startswith(("english", "不做", "不适用", "不用于")):
            out.append(piece)
    return list(dict.fromkeys(out))[:4]


def build_questions(card: Path) -> dict:
    """从卡片抽**种子**题。返回 {schema, subject, questions, needs_human_augmentation, note}。"""
    from .util import load_frontmatter
    fm, _body = load_frontmatter(card)
    name = str(fm.get("name") or card.parent.name)
    desc = str(fm.get("description") or "")
    ucs = _use_cases_from_desc(desc)
    qs: list[dict] = []
    for i, uc in enumerate(ucs, 1):
        qs.append({"id": f"consistency-{i}", "kind": "consistency",
                   "question": f"在「{uc}」情境下，本卡给出的结论方向与理由是什么？",
                   "probes": "立场/结论一致性", "source": "description.适用于"})
    qs.append({"id": "consistency-x", "kind": "consistency",
               "question": "【必填·邻近混淆题】该素材里另一个能力也沾边的情境，本卡与邻近能力会给出不同结论的那一个——请出题。",
               "probes": "立场/结论一致性（cross-skill）", "source": "human"})
    qs.append({"id": "style-1", "kind": "style",
               "question": "把本卡对同一个问题的输出与 2 份通用回答混排，请评分 Agent 指出哪一份来自本卡（辨识依据须是具体方法偏好，不是篇幅/排版）。",
               "probes": "风格辨识度", "source": "template"})
    qs.append({"id": "edge-1", "kind": "edge_honesty",
               "question": "【必填·素材外】选一个本素材**从未覆盖**的领域提问，看它是否明确声明「素材没讲」并区分推断/结论。这是最重的一维，机器生成不了，必须人工出题。",
               "probes": "边缘诚实度", "source": "human"})
    qs.append({"id": "source-1", "kind": "source_transparency",
               "question": "随机抽 3 条 R 段引语，逐条在原始语料中定位（用 td.py verify-quotes / anchor 核）。",
               "probes": "来源透明度", "source": "template"})
    return {
        "schema": QUESTIONS_SCHEMA,
        "subject": name,
        "questions": qs,
        "needs_human_augmentation": True,
        "note": ("本文件是**种子题**：consistency-* 从 description 自动生成，style/source 是固定任务，"
                 "标注 source=human 的必须人工补（尤其 edge_honesty——机器生成不了、"
                 "又恰恰是唯一能抓住『编造』的一维）。补完再交给答题 Agent。"),
    }


def build_kit(card: Path, out_dir: Path) -> dict:
    """生成一整套 eval-kit 到 out_dir。返回摘要。"""
    card = Path(card)
    if not card.exists():
        raise ToolError(f"卡片不存在：{card}")
    out = ensure_dir(Path(out_dir))
    q = build_questions(card)

    answers_tpl = {
        "schema": "rulai-distill/eval-kit-answers@1",
        "answerer": "【必填：独立答题 Agent 的标识，不得与卡片作者相同】",
        "answers": [{"id": x["id"], "answer": "【填写该题的回答；只能依据卡片，不得凭作者记忆】"}
                    for x in q["questions"]],
    }
    scores_tpl = {
        "schema": "rulai-distill/eval-kit-scores@1",
        "grader": "【必填：独立评分 Agent 的标识，不得看到答题者身份】",
        "dimensions": {k: {"score": 0, "max": mx, "note": "【扣分必须引用卡片原话】"}
                       for k, mx in DIM_MAX.items()},
        "total": 0,
        "notes": "总分 = 各维度之和（≤100）。给 0 分或满分，慎用中间分。",
    }
    readme = f"""# eval-kit · {q['subject']}

本套件把 FIDELITY 的**独立质检闭环**变成一组可回传的 JSON。三步：

## 1. 独立答题（答题 Agent ≠ 卡片作者）

用 `questions.json` 出题，创建一个**独立答题 Agent**，只给它卡片、不给作者记忆，
让它把回答写进 `answers.json`（模板见 `answers.template.json`）。
**答题者标识必须填，且不得等于卡片作者。**

## 2. 独立评分（≥2 个评分 Agent）

把「卡片 + answers.json」交给 **2 个互相独立、且都看不到答题者身份**的评分 Agent，
各自把 `scores.template.json` 填成 `scores-1.json` / `scores-2.json`。
评分只在 `references/scoring-rubric.md` 范围内判，不临场发挥。

## 3. 汇总出报告（分差门禁）

    td.py eval-kit check <本目录> --answers answers.json \\
        --scores scores-1.json scores-2.json --out FIDELITY.json

它会：校验格式 → 算两个评分者的分差门禁（>10 拒绝）→ 产出符合
`schemas/fidelity.schema.json` 的 FIDELITY JSON。然后：

    td.py gate FIDELITY.json

> 注意：`init` 生成的题是**种子**，`needs_human_augmentation=true`。带 `source=human` 的题
> （尤其 edge_honesty）必须人工补——那是唯一能抓出「拿素材权威包装编造内容」的一维。
"""
    (out / "questions.json").write_text(
        json.dumps(q, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "answers.template.json").write_text(
        json.dumps(answers_tpl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "scores.template.json").write_text(
        json.dumps(scores_tpl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(readme, encoding="utf-8")
    return {"out": str(out), "subject": q["subject"], "questions": len(q["questions"]),
            "needs_human_augmentation": q["needs_human_augmentation"],
            "files": ["questions.json", "answers.template.json", "scores.template.json", "README.md"]}


# --------------------------------------------------------------------------
# 汇总与分差门禁
# --------------------------------------------------------------------------
def _load(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise ToolError(f"文件不存在：{path}")
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as e:
        raise ToolError(f"JSON 解析失败：{path}", f"{e.msg}（行 {e.lineno}）")


def check_answers(answers: dict) -> tuple[str, list[str]]:
    """校验答题回传。返回 (answerer, errors)。空集 / 无答题者一律报错。"""
    errs: list[str] = []
    who = str(answers.get("answerer") or "").strip()
    if not who or who.startswith("【"):
        errs.append("answers.answerer 未填：无法证明答题者与作者独立，不得据此下质检结论")
    items = answers.get("answers") or []
    if not items:
        errs.append("answers.answers 为空：空集不得判通过（0 题作答 = 没测，不是通过）")
    for i, a in enumerate(items):
        if not str(a.get("answer") or "").strip() or str(a.get("answer", "")).startswith("【"):
            errs.append(f"answers[{i}]（{a.get('id')}）未作答")
    return who, errs


def check_grader(scores: dict, idx: int) -> tuple[str, dict, list[str]]:
    """校验单个评分回传。返回 (grader, dims, errors)。"""
    errs: list[str] = []
    who = str(scores.get("grader") or "").strip()
    if not who or who.startswith("【"):
        errs.append(f"scores[{idx}].grader 未填：无法证明评分者独立")
    dims_raw = scores.get("dimensions") or {}
    dims: dict[str, int] = {}
    for k, mx in DIM_MAX.items():
        cell = dims_raw.get(k)
        if cell is None:
            errs.append(f"scores[{idx}] 缺维度 {k}")
            continue
        val = cell.get("score") if isinstance(cell, dict) else cell
        if not isinstance(val, (int, float)):
            errs.append(f"scores[{idx}].{k} 分数非数字：{val!r}")
            continue
        if not (0 <= val <= mx):
            errs.append(f"scores[{idx}].{k}={val} 越界（0–{mx}）")
            continue
        dims[k] = int(val)
    return who, dims, errs


def check(answers_path: Path, score_paths: list[Path], subject: str | None = None) -> dict:
    """汇总答题 + 多个评分 → 交叉复核 → 产出 FIDELITY JSON（可被 gate 直接消费）。

    返回 {"report": <fidelity JSON>, "cross": <cross-review>, "verdict": "pass|fail", "errors": [...]}。
    """
    answers = _load(answers_path)
    answerer, a_errs = check_answers(answers)

    graders: list[str] = []
    grader_totals: list[float] = []
    dim_lists: list[dict] = []
    g_errs: list[str] = []
    for i, p in enumerate(score_paths):
        who, dims, errs = check_grader(_load(p), i)
        g_errs += errs
        if not errs:
            graders.append(who)
            dim_lists.append(dims)
            grader_totals.append(float(sum(dims.values())))

    errors = a_errs + g_errs
    # 复审 G1：cross-review 要的是**独立**评分者，同名不算两个人。
    # 实测 grader-1 ×2 曾被当 2 个评分者放行——那等于把"同一人打两次分"当交叉复核。
    dup = sorted({g for g in graders if graders.count(g) > 1})
    if dup:
        errors.append(f"评分者标识重复（{dup}）：交叉复核要求 ≥2 个**不同**的独立评分者，"
                      "同一标识填两次不构成独立复核")
    uniq_graders = len(set(graders))
    # 分差门禁：<2 个有效评分者 → insufficient_scorers（不得当"已复核"）。
    if grader_totals:
        cross = fid.cross_review(grader_totals, subject=subject)
    else:
        # 一个有效评分都没有：构造一个"人数不足"的判定，绝不判通过（空集假绿防护）。
        # fid.cross_review([]) 会直接抛错，所以这里手构造，语义与它一致。
        cross = {"schema": "rulai-distill/cross-review@1", "subject": subject,
                 "scorers": 0, "scores": [], "spread": 0.0,
                 "threshold": fid.CROSS_REVIEW_THRESHOLD, "min_scorers": fid.CROSS_REVIEW_MIN_SCORERS,
                 "verdict": "insufficient_scorers", "needs_human_review": True,
                 "threshold_fragile": False, "reasons": ["没有有效评分者（0 个）"]}

    # 合并维度 = 各评分者对同一维度的均值（取整，与 grade_of 的整数阈值同口径）
    dims: dict[str, int] = {}
    if dim_lists:
        for k in DIM_MAX:
            vals = [d.get(k, 0) for d in dim_lists]
            dims[k] = int(round(sum(vals) / len(vals)))
    total = sum(dims.values())
    grade = fid.grade_of(total)

    blocking: list[str] = list(cross.get("reasons") or [])
    if answerer and any(g == answerer for g in graders):
        blocking.append(f"答题者与评分者同名（{answerer}）：不满足独立质检要求")
    report = {
        "schema": "rulai-distill/fidelity/v1",
        "subject": subject or str(answers.get("subject") or "unnamed"),
        "eval_mode": "dual-agent",
        "answerer": answerer,
        "graders": graders,
        "cross_grader_gap": cross.get("spread", 0.0),
        "dimensions": dims or {k: 0 for k in DIM_MAX},
        "total": total,
        "grade": grade,
        "blocking_issues": blocking,
    }
    verdict = "pass" if (not errors and uniq_graders >= fid.CROSS_REVIEW_MIN_SCORERS
                         and cross.get("verdict") == "pass"
                         and not (answerer and any(g == answerer for g in graders))) else "fail"
    return {"report": report, "cross": cross, "verdict": verdict, "errors": errors,
            "graders": graders, "unique_graders": uniq_graders, "answerer": answerer}
