# -*- coding: utf-8 -*-
"""tdlib.strategy — 输出形态决策器（single vs pack），对标 cangjie 的 select_output_strategy.py。

策略 `single-first-v1`：
  1. 用户显式指定 → 遵从，不覆盖；
  2. 用户声明目的（learning/reference → single；workflow/distribution → pack）；
  3. 未声明：晋级能力 ≥3 **且** 触发验证已就绪 → 推荐 pack，否则推荐 single。

为什么默认 single-first：一个包被拆成 8 个技能，触发面会互相污染；
先用单一入口收敛，等触发评测证明「拆得动」再拆。这条策略的价值在于**默认保守**。

输出可解释 decision report（rulai-distill/output-decision@1），每条理由都写清触发条件。
"""
from __future__ import annotations

from pathlib import Path

from .util import now_iso, read_json, write_json

POLICY = "single-first-v1"
PURPOSE_TO_MODE = {"learning": "single", "reference": "single",
                   "workflow": "pack", "distribution": "pack"}


def decide(bundle_dir: Path, requested: str | None = None, purpose: str | None = None,
           trigger_ready: bool = False, promo_budget: int = 8) -> dict:
    bundle = read_json(Path(bundle_dir) / "bundle.json")
    skills = bundle.get("skills", [])
    promoted = [s for s in skills if s.get("promotion", s.get("role")) == "promoted"]
    reasons: list[str] = []

    if requested in ("single", "pack"):
        selected = requested
        reasons.append(f"用户显式选择 {requested}，决策器不覆盖用户选择")
    elif purpose:
        selected = PURPOSE_TO_MODE.get(purpose, "single")
        reasons.append(f"用户目的为 {purpose} → {selected}")
    elif len(promoted) >= 3 and trigger_ready:
        selected = "pack"
        reasons.append(f"{len(promoted)} 个能力通过晋级门（≥3）且触发验证已就绪 → pack")
    else:
        selected = "single"
        if len(promoted) >= 3:
            reasons.append(f"{len(promoted)} 个能力通过晋级门，但触发验证未就绪 → 按 single-first 先收敛")
        else:
            reasons.append(f"仅 {len(promoted)} 个能力通过晋级门（<3）→ single")

    over_budget = len(promoted) > promo_budget
    if over_budget:
        reasons.append(f"⚠️ 晋级数 {len(promoted)} 超过预算 {promo_budget}，建议先砍到预算内再拆包")

    router = [s for s in skills if s.get("promotion", s.get("role")) == "router"]
    alternative = (f"single（1 个路由入口 + {len(promoted)} 张能力卡）"
                   if selected == "pack" else
                   f"pack（{len(promoted)} 个独立可发现入口 + {len(router)} 张路由卡）")

    return {
        "schema": "rulai-distill/output-decision@1",
        "policy": POLICY,
        "generated_at": now_iso(),
        "requested": requested,
        "purpose": purpose,
        "trigger_validation_ready": trigger_ready,
        "promotion_budget": promo_budget,
        "counts": {"total": len(skills), "promoted": len(promoted), "router": len(router)},
        "selected": selected,
        "reasons": reasons,
        "alternative": alternative,
        "over_budget": over_budget,
    }


def write_decision(bundle_dir: Path, report: dict, out: Path | None = None) -> Path:
    p = Path(out) if out else Path(bundle_dir) / "output-decision.json"
    write_json(p, report)
    return p
