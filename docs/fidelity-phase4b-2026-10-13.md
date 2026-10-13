---
subject: tongjian-wei-bundle 6 卡 + zengguofan-xiushen 人物卡
date: 2026-10-13
phase: Phase 4b · FIDELITY 双 Agent 独立质检
eval_mode: dual-agent（答题 ≠ 评分，两轮评分者互相独立且互相不可见）
adjudication: needs_human_review 触发（7/7 分差 > 10）→ 已人工复核，见第四节
---

# Phase 4b · FIDELITY 双 Agent 评测报告（7 张随包卡）

> **本文只写实测数字与可复核结论。** 两轮评分的机器可读原件在各卡的
> `eval/fidelity/<slug>/scores-1.json` / `scores-2.json`；工具汇总结果在
> `FIDELITY.rejected.json`（**注意后缀**：7 张卡全部没过交叉复核门禁，文件名就是证据）。

## 一、怎么跑的

1. **建套件**：`td.py eval-kit init <卡> --out eval/fidelity/<slug>`。`init` 产的是**种子题**，
   其中 `source=human` 的两道（邻近混淆 `consistency-x`、素材外 `edge-1`）由人逐卡补写——
   这两道是唯一有判别力的题，不由机器代劳。
2. **独立答题**：7 个答题 Agent，各只读**自己那一张卡**，禁止读语料、禁止凭历史知识补充；
   答案里的 `answerer` 字段在交评分前被抹去（`answers.anon.json`），评分者看不到答题者身份。
3. **独立评分（两轮，互不通信）**：
   - 第 1 轮 7 个 Agent，用标准 `references/scoring-rubric.md`；
   - 第 2 轮 7 个 Agent，用**严格** `references/scoring-rubric-strict.md`，且明确告知「你的职责是找扣分点」，
     **不给它看第 1 轮的分数**（只告知"存在另一位评分者"）。
   - 两轮都被要求**真跑** `td.py verify-quotes`，把命中/未找到条数写进 `source_transparency` 的判据。

## 二、两轮分数（原始，未经修饰）

| 卡片 | 第 1 轮（标准 rubric） | 第 2 轮（严格 rubric） | 分差 | 门禁 |
|---|---|---|---|---|
| mingfen-scan | **100** (30/20/20/15/15) | **84** (22/16/20/13/13) | 16 | ❌ >10 |
| cai-de-two-column | **100** (30/20/20/15/15) | **84** (22/12/20/15/15) | 16 | ❌ >10 |
| zhiren-five-looks | **100** (30/20/20/15/15) | **76** (22/12/20/10/12) | 24 | ❌ >10 |
| zai-de-bu-zai-xian | **98** (30/20/20/13/15) | **76** (22/12/20/10/12) | 22 | ❌ >10 |
| chunchi-structure | **97** (30/20/20/12/15) | **76** (22/16/16/10/12) | 21 | ❌ >10 |
| jiao-di-cycle | **100** (30/20/20/15/15) | **82** (22/15/18/13/14) | 18 | ❌ >10 |
| zengguofan-xiushen（人物卡） | **100** (30/20/20/15/15) | **86** (22/16/20/15/13) | 14 | ❌ >10 |

维度顺序：consistency(30) / style(20) / edge_honesty(20) / source_transparency(15) / structure(15)。

**7/7 全部分差超阈值**，`eval-kit check` 一张都没放行，产物写成 `FIDELITY.rejected.json`。

## 三、分差不是噪声，是两处系统性偏差（已登记为缺陷 #82）

两名严格评分者在互不通气的情况下，指出了**同两个根因**：

1. **`consistency-1~N` 的题干逐字嵌入卡片 description**（`source: description.适用于`）——
   答题 Agent 持卡复述就能满分，测的是「读没读懂卡片」而不是「能不能用卡片」。
   严格轮 7 张卡的 consistency **统一判 22/30**，扣分理由也一致：
   「这些题的高分只证明读过卡片，不计入质量支撑」。
   → 这说明 22 分主要反映**出题器的判别力**，而不是卡片本身的质量。
2. **`style-1` 要求「与 2 份通用回答混排盲辨」，套件里却一份对照样本都没有**——
   「正确挑出」这一半**从未被执行**。标准轮 7 张卡的 style **全部 20/20**，
   没有一次真正的盲辨发生过；严格轮降到 12~16，是主动把未实测的部分扣掉。

修法（缺陷 #82）：consistency 题改**迁移型**并打 `discriminative=low` + `leakage` 字段；
`init` 随套件生成 `style-decoys.md`（2 份通用回答 + 盲排操作）；
`scores.template.json` 的 `style.note` 强制先声明盲排状态。三处都由回归测试守住。

## 四、人工复核裁定（我就是那个"人"）

触发门禁后由人工复核。裁定如下，理由是**证据形态**而不是分数高低：

> **对外声明采用第 2 轮（严格 rubric）的分数作为质量下限：
> 7 张卡在严格判据下为 76–86 / B。**

理由：
- 严格轮**每条扣分都引用了卡片或作答的原文**，并逐卡实跑了 `verify-quotes` 把数字写进判据；
- 标准轮自己写明了多处限制（"style 未做盲排"、"consistency 题为复述题"），
  却仍然给出满分——**它给的是"没找到扣分理由"，不是"经得起挑"**；
- 同一批卡、同一批作答，两轮差 14–24 分，差距集中在上述两处系统性偏差上。

**同时必须声明的反向边界**（不许只报好消息）：
- 严格轮的 style 分（12–16）**同样未经真盲排**，扣的是"没测到"而不是"测出来差"；
  对照样本现已随套件生成，**这一维需重测后才能给出有意义的数**。
- 严格轮的 consistency 22/30 有一部分是**出题器背的**，不是卡片背的；#82 修复后需重测。

## 五、顺带抓出的 4 处卡级真缺陷（缺陷 #83，已修）

严格轮要求「扣分必须引用原文」，评分 Agent 因此把卡片里自称"可复跑/可核"的字样逐条实跑了一遍，
抓到 4 处**建卡自验没抓到**的问题：

| 卡 | 问题 | 实跑证据 | 处置 |
|---|---|---|---|
| chunchi-structure | 自定「引语一律繁体逐字」，正文却给简体转述加「」 | `verify-quotes` 15 条命中 13，2 条判「全篇未找到」 | 两处转述去掉引号并注明"非底稿引语"，现 15/15 |
| zhiren-five-looks | 正文可复跑命令 `grep -c "使人視"` 注「→ 2」 | 实跑返回 **1**（grep -c 数行数，两处落在同一行） | 改 `grep -o … \| wc -l` 并留勘误注 |
| zai-de-bu-zai-xian | R 段 §17 标「周紀二」、§109 标「周紀五」 | 语料中【第17段】在第142行、**早于**第302行的 `=周紀二=` 分界；§109（赧王二十三年，前292）晚于 §117/§118 却标更早的卷次，同卡自相矛盾 | §17 改周紀一、§109 改周紀四 |
| zengguofan-xiushen | frontmatter「候选 9 条」 | 正文明细 6 全过 + 降级1 + 丢弃2 + 合并1 = **10** | 改 10，并写明"账目须平" |

**这条教训要写进纪律**：Phase 2 的建卡自验把这些卡记成了「verify-quotes 全命中 / 静态自验通过」，
而 Phase 4b 的**独立**评分逐条抓出 4 处——**建卡者自己的自验不等于独立核验**。
现已把"卡片里凡自称可复跑/可核的命令与计数必须能被机械复算"写进
`t_cards_quotes_all_verifiable` + `t_card_selfcheck_commands_recomputable` 两条守卫。

## 六、诚实边界（本文结论能用到哪里）

1. **style 维两轮都不可用作质量证据**（当时无对照样本）。对照样本已生成，重测待做。
2. 答题者与 4 名（2×2 轮）评分者**都是同族 LLM**。同族互评偏宽松是已知偏差；
   跨模型复评、人类复评**均未做**，不做跨模型外推。
3. **edge_honesty 是唯一两轮都高的一维**（严格轮 6/7 拿满分 20，仅 chunchi 的 16）：
   7 张卡在「素材从未覆盖的领域」上都明确声明了边界并区分推断与结论。
   这一维的结论可以单独采信——它也是唯一由**人工出题**驱动的一维。
4. chunchi 是 7 张卡里唯一在严格轮掉到 edge_honesty 16 的，原因是它在推断层多给了三条政策建议；
   已记为该卡的改进项，未改卡（那三条属推断而非素材结论，改卡会掩盖问题）。
5. 本文所有分数对应**修复 #83 之前**的卡片状态（#83 的 4 处已在评分后立即修掉）。
   修复后未重测，**不声称修完就变好**。

## 七、可复跑命令

    cd books/tongjian-wei-bundle/eval/fidelity/<slug>
    # 两轮评分与答题原件
    ls answers.json answers.anon.json scores-1.json scores-2.json style-decoys.md
    cd ../../../..   # 回仓库根
    python3 scripts/td.py eval-kit check \
        --answers books/tongjian-wei-bundle/eval/fidelity/<slug>/answers.json \
        --scores  books/tongjian-wei-bundle/eval/fidelity/<slug>/scores-1.json \
                  books/tongjian-wei-bundle/eval/fidelity/<slug>/scores-2.json \
        --subject <slug> \
        --out     books/tongjian-wei-bundle/eval/fidelity/<slug>/FIDELITY.json
    # 期望输出：分差门禁 needs_human_review（分差 >10），产物写为 FIDELITY.rejected.json
