# 组织级独立复评协议（把「结构独立」升级为「组织独立」）

> 目的：兑现 README 已声明的诚实边界——当前 FIDELITY 质检是**结构独立**（答题/评分是两个 Agent，但同属一个模型家族、由本项目调度）。本协议定义如何引入**外部独立视角**，让结论从「结构独立」升级为「组织独立」。
> 状态：**协议已就绪，实测已开始**。截至 2026-10-14，3 张人物卡（郑板桥 / 王阳明 / 曾国藩）
> 完成跨模型复评（DeepSeek `deepseek-v4-pro`），产物见 `docs/independent-recheck/`。
> 阻塞点已解除一半：用户提供了 DeepSeek 访问权（跨模型 ✅）；**人类评者仍未引入**。

## 两种独立视角

| 类型 | 谁来做 | 解决什么 | 产物 |
|---|---|---|---|
| 跨模型复评 | 不同模型家族（如本项目用 A 族，复评用 B 族）按同一 8 题 rubric 重答+重评 | 「同族互评偏宽松」「自评偏差」的残余风险 | `review.json`（reviewer_type=cross_model） |
| 第二人复评 | 人类评者盲读卡片+底稿，按 rubric 打分 | 「机器评分是否脱离人类判断」 | `review.json`（reviewer_type=human） |

任一类型 ≥1 份有效复评即可把该卡片标记为「组织独立」。

## 复评产物 schema（`docs/independent-recheck/<card>/<reviewer>/review.json`）

```json
{
  "card": "<card-slug>",
  "reviewer_type": "cross_model | human",
  "model_or_reviewer": "<模型族名 或 评者代号>",
  "date": "YYYY-MM-DD",
  "answers_rechecked": [
    {"id": 1, "verdict": "consistent | fabrication | inconsistent", "notes": "<可选>"}
  ],
  "fidelity_grade_reconfirmed": "A | B | C | D | none",
  "fabrication_flagged": false,
  "independence_note": "<该复评如何独立：不同模型族 / 盲读人类>"
}
```

`fabrication_flagged=true` 或 `fidelity_grade_reconfirmed=none` → 该复评**不通过**，须回写缺陷台账并回到对应卡片修复，不得计入「组织独立」。

## 落点与聚合

- 每份复评落在 `docs/independent-recheck/<card>/<reviewer>/review.json`。
- 聚合脚本：`python3 scripts/tdlib/independent_recheck.py` 扫描该目录，输出：
  - `docs/independent-recheck/ORG-INDEPENDENCE-LEDGER.json`（机器可读：每张卡是否组织独立、有效复评数、类型）
  - `docs/independent-recheck/ORG-INDEPENDENCE-LEDGER.md`（人读摘要）
- 当某卡首次达成组织独立，在其注册表条目与 README 的诚实边界里把「结构独立」改为「组织独立（已复评 N 次）」。

## 诚实边界（协议自带）

- 复评不是「再跑一遍自家脚本」——必须由**真外部**视角执行；用本项目同族模型伪装复评视为作弊，不计入。
- 复评样本量小（1 次）只能降「结构独立」风险，不能消除；建议每卡 ≥2 份异源复评（跨模型 + 人类各一份）才算稳健。
- **人类复评的开工包已备好（2026-10-15）**：`docs/human-review-packages/`（总说明 + 郑/王/曾三卡各一份，
  含材料路径、出题口径、五维百分制、`review.json` 模板与精确落点）。**当前人类复评例数仍为 0**——
  包备好不等于复评已做。已由 `t_org_independence_ledger` 钉住「凡组织独立的卡必须配包」。
- 为什么不用"第二个模型族"顶上：DeepSeek 同族不同档位（如 v4-flash）**不算异族**（换档位≠换家族）；
  WorkBuddy 平台模型与卡片作者同族，用它复评是同族自证。故唯一合法第二源是人类评者。
- **复评者若就是建卡者本人**，须在 `independence_note` 如实写明；该复评只算「作者自评的人类交叉」，
  不得对外称作独立第二人复评。
- 本协议不声称已执行；实际复评发生后，须登记缺陷台账（如有编造/降级发现）并补 e2e 守卫钉住「声明=实际」。
