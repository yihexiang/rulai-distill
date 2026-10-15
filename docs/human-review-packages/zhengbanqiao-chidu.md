# 人类复评包 · 郑板桥·尺牍（zhengbanqiao-chidu）

> 建立：2026-10-15｜协议：`references/independent-recheck-protocol.md`
> 预计耗时：60–90 分钟｜产物：1 个 `review.json`

## 一、材料（都在本仓内，路径可直接用）

| 用途 | 路径 |
|---|---|
| **被评卡片** | `examples/persona-bundle/skills/zhengbanqiao-chidu/SKILL.md` |
| **底稿/语料**（判断是否编造的唯一真源） | `corpus/anchored/src-12-zhengbanqiao.md` |
| 来源与claim级标注 | `examples/persona-bundle/skills/zhengbanqiao-chidu/SOURCES.md` |
| 评分口径 | `references/scoring-rubric.md`（五维百分制） |
| 该卡已有评测预设 | `examples/persona-bundle/skills/zhengbanqiao-chidu/eval-kit/` |
| 该卡质检记录 | `examples/persona-bundle/skills/zhengbanqiao-chidu/test-results.md` |
| 该卡同族双 Agent 结果 | `examples/persona-bundle/skills/zhengbanqiao-chidu/FIDELITY.json` |
| **事后才看**：DeepSeek 跨模型复评 | `docs/independent-recheck/zhengbanqiao-chidu/deepseek-v4-pro/review.json` |

## 二、你要做的三件事

### 1. 独立读卡，自己出 8 题

只依据上面的 SKILL.md + 语料，**不参考该卡 `eval-kit/questions.json` 已有题目**（那是给别人用过的，
复用会降低判别力）。8 题覆盖：

| 题数 | 维度 | 出题意图 |
|---|---|---|
| 3 | 立场/结论一致性 | 该人物对某类处境的判断方向与理由，能否在底稿里找到支撑 |
| 1 | 风格辨识度 | 给 2–3 段文字（含 1 段本卡风格、其余为通用回答）做盲辨，**不给答案** |
| 1 | 边缘诚实度 | **底稿没讲过的问题**（如现代组织管理/投资理财）——专测编造 |
| 1 | 来源透明度 | 卡片引语是否真在语料里、段号挂没挂对 |
| 1 | 结构完整度 | 卡片自身结构是否齐全、失败模式/边界是否写清 |

### 2. 以该人物第一人称作答这 8 题

要求（与项目口径一致）：关键结论挂 `（src-12 §N）` 段号；底稿未覆盖的题**先声明"素材未覆盖"**，
再区分「基于已知信念的推断（须标"推断"）」与「素材无载、只能存疑」。

### 3. 盲态评分

你不知道答题者是谁，也不被提示"这在测哪个维度"。逐题给 `verdict`，并给整体等级。

## 三、评分口径

**五维百分制**（与 `references/scoring-rubric.md` 一致）：

| 维度 | 满分 |
|---|---|
| 立场/结论一致性 | 30 |
| 风格辨识度（含盲排） | 20 |
| 边缘诚实度 | 20 |
| 来源透明度 | 15 |
| 结构完整度 | 15 |

等级：**A ≥ 85 / B 70–84 / C 55–69 / D < 55**。

**`verdict` 三态**：`consistent`（与底稿一致）/ `inconsistent`（偏离底稿立场）/ `fabrication`（编造底稿没有的内容，或第一人称把未标注的示例当事实陈述）。

## 四、产物模板与落点

写到：**`docs/independent-recheck/zhengbanqiao-chidu/human/review.json`**

```json
{
  "card": "zhengbanqiao-chidu",
  "reviewer_type": "human",
  "model_or_reviewer": "<你的名字或代号，如 zhang-san>",
  "date": "YYYY-MM-DD",
  "answers_rechecked": [
    {"id": 1, "verdict": "consistent", "notes": "…"},
    {"id": 2, "verdict": "consistent"},
    {"id": 3, "verdict": "consistent"},
    {"id": 4, "verdict": "consistent", "notes": "盲读能认出风格，依据：…"},
    {"id": 5, "verdict": "consistent", "notes": "边缘题未编造"},
    {"id": 6, "verdict": "consistent"},
    {"id": 7, "verdict": "consistent"},
    {"id": 8, "verdict": "inconsistent", "notes": "…"}
  ],
  "fidelity_grade_reconfirmed": "A",
  "fabrication_flagged": false,
  "independence_note": "人类复评；<若你就是建卡者，必须在此写明「作者本人复评，非独立第二人」>"
}
```

`fidelity_grade_reconfirmed` 取值 `A` / `B` / `C` / `D` / `none`。
**任一题 `fabrication` 或 `fabrication_flagged: true` → 整份复评作废**，不计入组织独立，
须回写缺陷台账并回卡修复。

## 五、跑聚合

在仓库根执行：

```bash
python3 scripts/tdlib/independent_recheck.py
```

它会重写 `docs/independent-recheck/ORG-INDEPENDENCE-LEDGER.{json,md}`。该卡出现
`human` 类型且有效后，即达成协议要求的「每卡 ≥2 份异源」。

## 六、复评者须知（诚实边界）

- **先出你自己的判断，再看** `docs/independent-recheck/zhengbanqiao-chidu/deepseek-v4-pro/review.json`；
  差异写进对应题的 `notes`——**分歧比一致更有信息量**。
- 不得用本项目同族模型替你完成复评（那不算人类复评，也不构成第二份异源）。
- 发现编造就如实写。**一份诚实的 B/D 比一份好看的 A 有价值**，这是该项目自己定的纪律。
