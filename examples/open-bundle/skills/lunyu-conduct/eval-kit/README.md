# eval-kit · lunyu-conduct

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

    td.py eval-kit check <本目录> --answers answers.json \
        --scores scores-1.json scores-2.json --out FIDELITY.json

它会：校验格式 → 算两个评分者的分差门禁（>10 拒绝）→ 产出符合
`schemas/fidelity.schema.json` 的 FIDELITY JSON。然后：

    td.py gate FIDELITY.json

> 注意：`init` 生成的题是**种子**，`needs_human_augmentation=true`。带 `source=human` 的题
> （尤其 edge_honesty）必须人工补——那是唯一能抓出「拿素材权威包装编造内容」的一维。
