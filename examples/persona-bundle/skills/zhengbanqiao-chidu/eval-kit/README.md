# eval-kit · zhengbanqiao-chidu

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

## 判别力警示（缺陷 #82 · 别把虚分当证据）

1. `consistency-*` 的题干**直接嵌入卡片 description 原句**（`discriminative: low`）——
   答题 Agent 持卡照抄就能满分，**这些题的高分只证明「读懂了卡片」，不构成质量证据**。
   实测：7 张卡的标准 rubric 轮，5 张拿到满分 100，无一例外。
2. `style-1` 必须用 `style-decoys.md` 里的 2 份通用回答做**随机混排盲辨**。
   不做盲排就给 style 高分是假绿——`scores-*.json` 的 style.note 必须先声明盲排状态。
3. 真正有判别力的是：`source=human` 的题（邻近混淆 + 素材外）与 style 的盲排结果。
