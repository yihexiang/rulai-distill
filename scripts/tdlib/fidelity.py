# -*- coding: utf-8 -*-
"""tdlib.fidelity — FIDELITY 出厂质检报告的解析、门槛判定与自检降级规则。

对标 alchaincyf/nuwa-skill 的 references/fidelity-scorecard.md，改为可执行判定：
  * 支持 Markdown 报告与 JSON 报告（rulai-distill/fidelity/v1）
  * fallback-self 模式识别 + 打折（见 references/scoring-rubric.md）
  * 四个一票否决项：编造(维度3=0) / 自评自证 / 伪装双 Agent / 伪造引语

铁律：**答题 Agent 与评分 Agent 必须是两个独立 Agent**。依据 SkillLens
（arXiv 2605.23899）实证 LLM 自评 skill 质量准确率仅 46.4%，接近随机。

第三条铁律（交叉复核）也已机器化：见 `cross_review()`。原文口径是
「重要结论建议 2 个独立评分 agent，分差 >10 分人工复核」——**比较用 `>` 不是 `>=`**，
贴边时函数自报 `threshold_fragile`，不许把单点读数当结论。
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import ToolError, read_text, warn

GRADES = {"A": 85, "B": 70, "C": 55, "D": 0}
CROSS_REVIEW_THRESHOLD = 10.0   # nuwa 第三铁律：分差 >10 分须人工复核
CROSS_REVIEW_MIN_SCORERS = 2    # 「建议 2 个独立评分 agent」——少于 2 不构成交叉复核
DIMS = [("consistency", r"立场/结论一致性", 30), ("style", r"风格辨识度", 20),
        ("edge_honesty", r"边缘诚实度", 20), ("source_transparency", r"来源透明度", 15),
        ("structure", r"结构完整度", 15)]
PERSONA_DIMS = [("consistency", r"立场/结论一致性", 30), ("style", r"风格辨识度", 20),
                ("edge_honesty", r"边缘诚实度", 20), ("source_transparency", r"来源透明度", 15),
                ("structure", r"认知结构完整度", 15)]
FALLBACK_DISCOUNT = 0.8  # fallback-self 时维度 1/3 记录值打 8 折


def _parse_dims(text: str, table) -> tuple[dict, list[str]]:
    """解析维度打分表。返回 (已解析维度, 未解析维度键列表)。

    未解析的维度键（报告里该维度行没被正则命中，**或命中了但分数没解析出来**）
    必须**显式返回**，不能静默丢弃——否则 gate 会基于一个被悄悄低估的总分开绿灯
    （第三方测评 #2 / 报告 P1-2：解析宽松导致"看起来完整"的报告实际漏维度）。
    """
    marks = [(k, pat, mx, re.search(pat, text)) for k, pat, mx in table]
    out: dict[str, int] = {}
    missing: list[str] = []
    for key, _pat, mx, m in marks:
        if not m:
            missing.append(key)
            continue
        start = m.end()
        nxt = next((mm.start() for _, _, _, mm in marks if mm and mm.start() > start), len(text))
        seg = text[start:nxt]
        hit = re.search(rf"(\d{{1,3}})\s*/\s*{mx}", seg) or re.search(r"得分[:：]\s*(\d{1,3})", seg)
        if hit:
            out[key] = int(hit.group(1))
        else:
            # 维度行存在但分数没解析出来（格式不对）→ 同样算未解析，提示而非假装 0
            missing.append(key)
    return out, missing


def parse_report(path: Path) -> dict:
    """解析 FIDELITY 报告（md 或 json），返回归一化 dict。"""
    path = Path(path)
    if not path.exists():
        raise ToolError(f"FIDELITY 报告不存在：{path}", "阶段 4b 未执行，或文件名不是 FIDELITY.md")
    if path.suffix == ".json":
        import json
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ToolError(f"FIDELITY JSON 解析失败：{e.msg}")
        data.setdefault("source_file", str(path))
        data.setdefault("grade", grade_of(data.get("total", 0)))
        data.setdefault("eval_mode", "unknown")
        return data

    text = read_text(path)
    dims, missing = _parse_dims(text, DIMS)
    if not dims:
        dims, missing = _parse_dims(text, PERSONA_DIMS)
    m = re.search(r"\*\*?总分\*\*?[^\d\-]{0,8}(\d{1,3})", text)
    declared_total = int(m.group(1)) if m else None
    sum_dims = sum(dims.values())
    # 报告声明了总分，但其维度之和与之不符 = 报告自相矛盾（少维度 / 多维度 / 写错数）。
    # 第三方测评 #2 / 报告 P1-2：这种不一致此前被静默忽略，gate 直接信任声明总分。
    total_mismatch = declared_total is not None and declared_total != sum_dims
    total = declared_total if declared_total is not None else sum_dims
    grade = grade_of(total)
    mode = "unknown"
    if "fallback-self" in text or "自测模式" in text:
        mode = "fallback-self"
    elif "dual-agent" in text:
        mode = "dual-agent"
    weakest = re.search(r"最弱项[^：:\n]*[：:]\s*(.+)", text)
    return {
        "source_file": str(path),
        "eval_mode": mode,
        "total": total,
        "declared_total": declared_total,
        "dimension_sum": sum_dims,
        "total_mismatch": bool(total_mismatch),
        "grade": grade,
        "dimensions": dims,
        "unparsed_dims": missing,
        "weakest_dimension": weakest.group(1).strip() if weakest else None,
        "dual_agent_proof": bool(re.search(r"答题\s*Agent|评分\s*Agent|answerer|grader", text)),
    }


def grade_of(total: float) -> str:
    for g, thr in GRADES.items():
        if total >= thr:
            return g
    return "D"


# --------------------------------------------------------------------------
# 第三条铁律：交叉复核（多评分 Agent 分差门禁）
# --------------------------------------------------------------------------
def cross_review(scores, threshold: float = CROSS_REVIEW_THRESHOLD,
                 min_scorers: int = CROSS_REVIEW_MIN_SCORERS,
                 subject: str | None = None) -> dict:
    """多评分 Agent 交叉复核判定。

    口径（照抄上游，不含糊化）：
      * 分差 = max - min，**严格大于** threshold 才须人工复核（原文「分差 >10 分」）。
      * 评分人数 < min_scorers → `insufficient_scorers`：单 Agent 打分不构成交叉复核，
        不得当作「已复核」。
      * |spread - threshold| <= 1 → `threshold_fragile=True`。贴边时阈值是脆的，
        **单点数不许单独引用**（见 CONSTRAINTS.md：阈值脆弱必须自检）。
      * 空输入直接报错，**不判通过**——空集假绿比报错危险（缺陷 #12 的同型教训）。
    """
    if scores is None:
        raise ToolError("缺少评分列表", "用法：td.py cross-review 95,88")
    vals = [s for s in scores if s is not None]
    if not vals:
        raise ToolError("交叉复核至少需要 1 个评分", "空输入不得判为通过——请提供各评分 Agent 的总分")
    bad = [s for s in vals if not isinstance(s, (int, float)) or not (0 <= s <= 100)]
    if bad:
        raise ToolError(f"评分必须在 0–100 之间：{bad}", "总分口径为百分制；分量表请换算后再传")

    lo, hi = min(vals), max(vals)
    spread = round(float(hi) - float(lo), 2)
    reasons: list[str] = []
    verdict = "pass"
    if len(vals) < min_scorers:
        verdict = "insufficient_scorers"
        reasons.append(f"只有 {len(vals)} 个评分（<{min_scorers}）——单 Agent 打分不构成交叉复核")
    if spread > threshold:
        if verdict == "pass":
            verdict = "needs_human_review"
        reasons.append(f"分差 {spread:g} > 阈值 {threshold:g}：评分 Agent 判断分歧过大，须人工复核")
    if len(set(vals)) == 1 and len(vals) >= min_scorers:
        reasons.append("多个评分给出完全相同分数：请确认它们是独立评分而非互相抄录")

    return {
        "schema": "rulai-distill/cross-review@1",
        "subject": subject,
        "scorers": len(vals),
        "scores": list(vals),
        "min": lo,
        "max": hi,
        "spread": spread,
        "threshold": float(threshold),
        "min_scorers": min_scorers,
        "verdict": verdict,
        "needs_human_review": verdict != "pass",
        "threshold_fragile": abs(spread - float(threshold)) <= 1,
        "reasons": reasons,
        "source": "nuwa-skill FIDELITY 第三条铁律（交叉复核）",
    }


def apply_fallback_discount(rep: dict) -> tuple[dict, list[str]]:
    """自测模式打折：维度 1/3 按 0.8 记录，并禁用维度 2（自认风格无意义）。"""
    notes: list[str] = []
    if rep.get("eval_mode") != "fallback-self":
        return rep, notes
    d = dict(rep.get("dimensions") or {})
    for k in ("consistency", "edge_honesty"):
        if k in d:
            d[k] = int(d[k] * FALLBACK_DISCOUNT)
    notes.append(f"fallback-self：维度 1/3 按 {FALLBACK_DISCOUNT:.0%} 记录")
    if "style" in d:
        d["style"] = 0
        notes.append("fallback-self：维度 2（风格辨识度）作废——自己认自己的风格永远高分")
    rep = dict(rep)
    rep["dimensions"] = d
    rep["total"] = sum(d.values()) if d else rep.get("total", 0)
    rep["grade"] = grade_of(rep["total"])
    rep["fallback_applied"] = True
    return rep, notes


def vetoes(rep: dict) -> list[str]:
    """返回一票否决项列表（空列表 = 通过）。"""
    out = []
    d = rep.get("dimensions") or {}
    if d.get("edge_honesty") == 0:
        out.append("维度 3 边缘诚实度 = 0：存在编造行为，产物比没有技能更危险")
    if rep.get("eval_mode") == "unknown":
        out.append("评测模式无法判定：不能证明答题与评分是独立 Agent")
    if rep.get("fallback_applied") and "对外" in (rep.get("self_eval_note") or ""):
        out.append("自测结果被用于对外质量宣称")
    # 复审 G1：报告自带 blocking_issues（eval-kit 判 fail 时会写）→ 一票否决。
    # gate 此前只读总分/人数，于是「失败产物」照样能过——现在见到即拒（纵深防御）。
    if rep.get("blocking_issues"):
        out.append("报告载有 blocking_issues（评测未通过）：不得放行 —— "
                   + "；".join(str(x) for x in rep["blocking_issues"][:3]))
    return out


def gate(rep: dict, min_grade: str = "B", allow_fallback: bool = False,
         cross: dict | None = None) -> tuple[bool, list[str]]:
    """门槛判定。默认**拒绝**非双 Agent 评测通过：自测分数不是质检结论。

    allow_fallback=True 时允许 fallback-self 通过，但调用方须自行承担结论风险
    （registry 会标 eval_mode=fallback-self，事后可审计）。

    cross 为 `cross_review()` 的结果时，交叉复核未过（分差过大 / 评分人数不足）
    一律**拒绝放行**——这是 nuwa 第三条铁律的门禁形态。
    """
    reasons: list[str] = []
    v = vetoes(rep)
    total, grade = rep.get("total", 0), rep.get("grade", "D")
    if v:
        return False, v
    if rep.get("eval_mode") != "dual-agent" and not allow_fallback:
        reasons.append(
            f"评测模式为 {rep.get('eval_mode')}，非双 Agent 盲测 —— 不得作为质检通过依据；"
            "若仅作内部参考请显式加 --allow-fallback")
        return False, reasons
    if cross is not None and cross.get("needs_human_review"):
        detail = "；".join(cross.get("reasons") or []) or cross.get("verdict", "")
        reasons.append(f"交叉复核未通过（{cross.get('verdict')}）：{detail}")
    if total < GRADES.get(min_grade, 70):
        reasons.append(f"总分 {total} 低于门槛 {min_grade}（≥{GRADES.get(min_grade)}）")
    return (not reasons), reasons
