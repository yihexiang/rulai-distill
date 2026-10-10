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
import re
from pathlib import Path

from . import fidelity as fid
from .util import ToolError, ensure_dir, read_text

KIT_SCHEMA = "rulai-distill/eval-kit@1"
QUESTIONS_SCHEMA = "rulai-distill/eval-kit-questions@1"
DIM_MAX = {k: mx for k, _pat, mx in fid.DIMS}
# 模板占位指令（answers.template.json 里的话）。**只有这些**算「未作答」——
# 不能凭「以【开头」一刀切：诚实声明（如「【无卡片·如实声明】…」）是有内容的答案。
TEMPLATE_FILL_RE = re.compile(r"填写该题的回答|只能依据卡片|必填：|请填写")


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
        txt = str(a.get("answer") or "").strip()
        # 判据是「**模板占位指令**」，不是「以【开头」——
        # 2026-10-10 实测：baseline 答题者（无卡片对照）如实写「【无卡片·如实声明】我没有拿到
        # 本卡正文…」，却被旧判据整类判成「未作答」。**把诚实声明判成没作答**，
        # 会让对照组要么被丢弃、要么被迫编造——两样都比假阳性更坏（#62/#65 同源纪律）。
        if not txt or TEMPLATE_FILL_RE.search(txt):
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

    # 先算 verdict（report 里要写它——"失败产物改名当正常报告"的防线）
    verdict = "pass" if (not errors and uniq_graders >= fid.CROSS_REVIEW_MIN_SCORERS
                         and cross.get("verdict") == "pass"
                         and not (answerer and any(g == answerer for g in graders))) else "fail"

    # 复审 G1 残余（2026-10-09）：blocking_issues 必须**穷尽**所有"不得放行"的理由。
    # 此前只收交叉复核 reasons + 同名，于是 **errors 类失败**（如空答题）写出的产物
    # blocking_issues 为空 → 把它改名成正常报告，gate 照样放行（实测 exit 0）。
    # 修法：①errors 全量并入；②报告带 verdict；③fid.vetoes 对 verdict=fail 一律拒。
    blocking: list[str] = []
    # 交叉复核**未过**才计入否决。注意 cross.reasons 里还有一条"多个评分给相同分数"
    # 的提醒——那是 pass 时的提示，**不能**当否决项（否则两个评分者恰好都给 95 就误杀）。
    if cross.get("verdict") != "pass":
        blocking += list(cross.get("reasons") or [])
    if answerer and any(g == answerer for g in graders):
        blocking.append(f"答题者与评分者同名（{answerer}）：不满足独立质检要求")
    for e in errors:
        if e not in blocking:
            blocking.append(e)
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
        "verdict": verdict,
    }
    return {"report": report, "cross": cross, "verdict": verdict, "errors": errors,
            "graders": graders, "unique_graders": uniq_graders, "answerer": answerer}


# --------------------------------------------------------------------------
# 效用实验：no-skill vs with-skill（同题库 · 同 rubric · 跨会话）
# --------------------------------------------------------------------------
# 为什么要有这一层（2026-10-10「精品分水岭」）：
# 本项目能证明「这张卡的引语没造假、结构齐全、两个评分者都打 A」，
# 却**证明不了「用了这张卡比不用强」**——A 分可能只来自卡片写得漂亮，
# 与答题时有没有卡片无关。缺的是**同题对照**。
#
# 为什么用「机械信号」而不是让评分者打「有用/没用」（#72/#73 的同一条教训）：
# 评分者打的主观效用分与卡片 FIDELITY 的 A 分**不独立**——同一批人看同一张卡，
# 容易把「卡片质量」当成「这张卡有用」。所以这里只判**可机判的行为特征**：
#
#   M1 locator_citation   答案带段号/篇-章号定位引用（能被别人机器复核）
#   M2 verbatim_quote     答案逐字复用了卡片 R 段的引语（专有内容，不是通用表述）
#   M3 boundary_declared  答案对素材外问题明确声明「素材没讲/未覆盖」
#   M4 card_term          答案复用了卡片自述的能力标签（frontmatter tags）
#
# **边界声明（必须随报告一起引用）**：这四道信号只覆盖「行为特征」，
# **不覆盖结论正确性、说服力与专业判断**；且 with/without 由同一模型家族的不同会话产出，
# **不构成跨模型因果证据**。增益等级描述的是「行为特征的差异」，不是「效果的因果」。

LOCATOR_RE = re.compile(r"§\d+|【第\d+[段条]】|第\d+[段条]|[一二三四五六七八九十]+之[一二三四五六七八九十]+")
BOUNDARY_RE = re.compile(r"未覆盖|没有覆盖|素材[^。；\n]{0,8}没讲|素材[^。；\n]{0,8}不覆盖|不适用|本卡不负责|超出本卡")
UTILITY_SIGNALS = ("locator_citation", "verbatim_quote", "boundary_declared", "card_term")


def card_signals(card_text: str) -> dict:
    """从卡片正文抽取「专有元素」——用于机判答案是否真的用了这张卡。

    专有元素取两处（都是卡片自述、**不靠人工指定关键词**）：
    - frontmatter `tags`：卡片自己声明的能力标签；
    - R 段引语的前 6 字：逐字锚在原文上的专有串（通用 AI 腔不会碰它）。
    """
    tags: set[str] = set()
    m = re.search(r"^tags:\s*\[(.*?)\]", card_text, re.M | re.S)
    if m:
        tags = {t.strip().strip("\"'") for t in m.group(1).split(",") if t.strip()}
    quote_keys = sorted({q.strip()[:6] for q in re.findall(r"[「“]([^」”\n]{6,})[」”]", card_text)})
    return {"tags": sorted(t for t in tags if len(t) >= 2), "quote_keys": quote_keys}


def answer_signals(answer_text: str, sig: dict) -> dict:
    """对一份答案打四道机械信号（0/1）。"""
    text = re.sub(r"\s+", "", answer_text)
    return {
        "locator_citation": bool(LOCATOR_RE.search(answer_text)),
        "verbatim_quote": any(re.sub(r"\s+", "", k) in text for k in sig["quote_keys"]),
        "boundary_declared": bool(BOUNDARY_RE.search(answer_text)),
        "card_term": any(re.sub(r"\s+", "", t) in text for t in sig["tags"]),
    }


def _answers_blob(answers: dict) -> str:
    return "\n".join(str(a.get("answer") or "") for a in (answers.get("answers") or []))


def utility(card_path: Path, with_path: Path, without_path: Path,
            subject: str | None = None, questions_path: Path | None = None) -> dict:
    """同题对照：with-skill vs no-skill 的机械信号增益。

    返回 {"subject", "signals", "with", "without", "delta", "gain", "boundary", "errors"}。
    `gain` ∈ significant / moderate / none —— **none 是合法结论**（增益不显著就如实写 none，
    不许虚报；这条由 t_evalkit_utility_baseline 的负向探针钉住）。

    `questions_path` 给定时做**题面泄漏剔除**：题库 description 里往往已经写了卡片的能力标签，
    答题者照抄题面就能"命中" card_term——那不是卡片的功劳。剔掉的词记进 `leaked_terms`，
    报告里如实可见（**剔除本身也要留痕**，否则等于悄悄放宽判据）。
    """
    errors: list[str] = []
    card_text = read_text(Path(card_path))
    sig = card_signals(card_text)
    if not sig["tags"] and not sig["quote_keys"]:
        raise ToolError(f"卡片抽不出任何专有元素：{card_path}",
                        "效用对照需要 frontmatter tags 或 R 段引语作为「专有元素」锚点")
    leaked: list[str] = []
    if questions_path:
        qtext = re.sub(r"\s+", "", read_text(Path(questions_path)))
        leaked = [t for t in sig["tags"] if re.sub(r"\s+", "", t) in qtext]
        sig["tags"] = [t for t in sig["tags"] if t not in leaked]

    with_a = _load(with_path)
    without_a = _load(without_path)
    for label, a in (("with", with_a), ("without", without_a)):
        who, errs = check_answers(a)
        if errs:
            errors += [f"{label}: {e}" for e in errs]
    if errors:
        return {"subject": subject or "unnamed", "signals": list(UTILITY_SIGNALS),
                "with": {}, "without": {}, "delta": {}, "gain": "invalid",
                "boundary": [], "errors": errors}

    w = answer_signals(_answers_blob(with_a), sig)
    wo = answer_signals(_answers_blob(without_a), sig)
    delta = {k: int(w[k]) - int(wo[k]) for k in UTILITY_SIGNALS}
    n_delta = sum(max(0, d) for d in delta.values())
    n_with = sum(1 for k in UTILITY_SIGNALS if w[k])
    n_without = sum(1 for k in UTILITY_SIGNALS if wo[k])
    if n_delta >= 2 and n_with >= 3 and n_without <= 1:
        gain = "significant"
    elif n_delta >= 1:
        gain = "moderate"
    else:
        gain = "none"
    return {
        "subject": subject or "unnamed",
        "card": str(card_path),
        "signals": list(UTILITY_SIGNALS),
        "with": w, "without": wo, "delta": delta,
        "counts": {"with": n_with, "without": n_without, "delta": n_delta},
        "leaked_terms": leaked,
        "gain": gain,
        "boundary": [
            "只判机械可判的行为特征（定位引用/引语复用/边界声明/术语复用），不覆盖结论正确性与说服力",
            "with/without 由同一模型家族的不同会话产出，不是跨模型因果证据",
            "无增益（none）是合法结论，不得为凑效果虚报",
            "题面已出现的 tags 已从判据剔除（leaked_terms），否则答题者照抄题面即算命中",
        ],
        "errors": [],
    }
