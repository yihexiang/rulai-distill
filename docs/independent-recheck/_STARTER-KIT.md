# 跨模型复评 · 操作启动包（P1#2）

> 你是**用另一个模型家族 / 另一个 Agent 的人**。本包教你怎样对 rulai-distill 的某张卡片做一次**独立复评**，把产物丢回本项目，我的聚合脚本就会把它从「结构独立」升为「组织独立」。
> 协议全文：`references/independent-recheck-protocol.md`。聚合脚本：`scripts/tdlib/independent_recheck.py`。

## 为什么需要你

rulai-distill 的出厂质检是**结构独立**（答题/评分是两个 Agent，但同属一个模型家族、由本项目调度）。同族互评可能存在偏宽松的残余风险。要消除它，必须引入**你这个真外部视角**——用不同的模型家族，按同一套方法重答+重评。

## 你只需要做三件事

### 1. 取卡片材料

对每张你想复评的卡片，取两个文件：
- 卡片本身：`<card>/SKILL.md`（本仓在 `examples/.../skills/<card>/SKILL.md`；guoxue 系列在独立仓库 `guoxue-skills/`；musk 系列在 `musk-run` / `musk-run2` / `evalkit-run-musk-decisions`）。
- 卡片的底稿/来源（用于判断答案是否编造）：卡片目录里的 `references/sources/` 或 `corpus/` 或原始素材。

### 2. 让你的异族 LLM 跑「重答 + 重评」

把下面这段**提示词**贴进你的 LLM（替换 `<卡片路径>` 与 `<素材路径>`）：

```
你是独立复评者（模型家族与 rulai-distill 不同）。请对以下 Agent Skill 做一次盲态复评：

【技能文件】<卡片 SKILL.md 全文>
【底稿/来源】<素材路径>

任务：
1. 自测出题：基于底稿，出 8 道评测题，覆盖——立场/结论一致性（3 题）、风格辨识度（1 题，盲读判断）、边缘诚实度（1 题：底稿没讲过的问题，看是否编造）、来源透明度（1 题）、结构完整度（1 题）、综合（1 题）。题目不要泄露答案。
2. 由另一个会话（或你自己切换角色）持该技能作答这 8 题。
3. 你作为评分者（不知道答题者是谁、不被提示"这是在测哪个维度"）按以下百分制打分：
   - 立场/结论一致性 30 ｜ 风格辨识度 20 ｜ 边缘诚实度 20 ｜ 来源透明度 15 ｜ 结构完整度 15
   - 等级：A≥85 / B 70-84 / C 55-69 / D<55
   - 边缘诚实度若发现编造（把没讲过的内容当事实、或第一人称编造未标示例），记 fabrication=true。
4. 输出一个 JSON（见下方 schema）。
```

### 3. 写回 `review.json` 并丢进本项目

在你本地建目录 `docs/independent-recheck/<card>/<你的模型族名>/review.json`，内容：

```json
{
  "card": "<card-slug>",
  "reviewer_type": "cross_model",
  "model_or_reviewer": "<你的模型族名，如 gpt-5 / claude-opus / gemini>",
  "date": "YYYY-MM-DD",
  "answers_rechecked": [
    {"id": 1, "verdict": "consistent", "notes": "与底稿立场一致"},
    {"id": 2, "verdict": "consistent"},
    {"id": 3, "verdict": "consistent"},
    {"id": 4, "verdict": "consistent", "notes": "盲读能认出风格"},
    {"id": 5, "verdict": "consistent", "notes": "边缘题未编造"},
    {"id": 6, "verdict": "consistent"},
    {"id": 7, "verdict": "consistent"},
    {"id": 8, "verdict": "inconsistent", "notes": "结构缺 B 段失败模式"}
  ],
  "fidelity_grade_reconfirmed": "A",
  "fabrication_flagged": false,
  "independence_note": "使用 <模型族> 独立重答+重评，与 rulai-distill 同族无关"
}
```

> `verdict` 取值：`consistent` / `inconsistent` / `fabrication`。任一题 `fabrication` 或 `fabrication_flagged=true` → 该复评**不通过**，须回写缺陷台账，不计入组织独立。

### 4. 跑聚合（交给我，或你自己跑）

把 `review.json` 放好后，在本项目根目录执行：

```bash
python3 scripts/tdlib/independent_recheck.py
```

它会扫描 `docs/independent-recheck/`，生成 `ORG-INDEPENDENCE-LEDGER.json / .md`。每张有 ≥1 份有效 cross_model 复评的卡，即标记为「组织独立」。

## 诚实边界（你也得守）

- 不得用 rulai-distill 同族模型伪装复评——那不算组织独立。
- 1 份复评只能降风险，不能消除；建议每卡 ≥2 份异源（跨模型 + 人类各一）才算稳健。
- 若你发现编造/降级，请如实写 `fabrication_flagged` 并告诉我，我会登记缺陷台账。
