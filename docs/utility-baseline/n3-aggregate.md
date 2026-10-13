# 效用对照 n=3 重复实验 · 聚合汇总（2026-10-12）

> 机器可读版：`n3-aggregate.json`。逐 run 原始报告在 `docs/utility-baseline/<card>/run-N/utility-report.json`。

> 守卫作用域（重要）：`tests/e2e.py` 的 `t_utility_n3_runs_complete` 只钉住**本仓 6 张典籍/文本卡**的
> 「locator_citation：with 全中 / without 全零」不变量——这对它们成立。**跨仓库常识领域卡 bazi-paipan
> 被刻意排除在该不变量外**（见第五节：其 without 侧也会引来源，不变量对它不成立），由
> `t_utility_n3_crossrepo_caveat` 单独钉住「诚实披露该边界」这条声明，防止把 none 结果藏成"稳定复现"。

## 一、总体结论

- **18/18 次会话正向增益，0 次 none**：6 张卡 × 3 run，没有一次出现负向或零增益。
- **`locator_citation`（定位引用）是唯一稳定区分信号**：18 次会话 with 侧 **18/18 命中**、
  without 侧 **0/18 命中**（即 0 次）。其余三道信号在 6 张卡上各有噪点，
  且 sometimes without 侧也会命中（最典型是 five-affairs 的 without 命中 3/4 信号）。
- **等级按卡分层**：hanfei / lunyu 多为 significant，five-affairs 稳定 moderate，xunzi 介于两者之间。

## 二、每卡 n=3 汇总

| 卡 | 标识 | significant | moderate | none | 结论 |
|---|---|---|---|---|---|
| tongjian | tongjian-decision-trace | 3 | 0 | 0 | 稳定显著 |
| mengzi | mengzi-refutation | 3 | 0 | 0 | 稳定显著 |
| five-affairs | five-affairs-seven-questions | 0 | 3 | 0 | 稳定中等（净增仅 locator_citation） |
| hanfei | hanfei-upward-advice | 3 | 0 | 0 | 稳定显著 |
| xunzi | xunzi-learning-order | 1 | 2 | 0 | 中等为主、1 次显著 |
| lunyu | lunyu-conduct | 2 | 1 | 0 | 显著为主、1 次中等 |
| bazi-paipan | bazi-paipan（**跨仓库** guoxue-skills） | 0 | 1 | 2 | ⚠️ 常识领域基线持平，多为 none（见第五节） |
| quming-xue | quming-xue（**跨仓库** guoxue-skills） | 0 | 2 | 1 | ⚠️ 常识领域基线持平（见第五节） |
| zhouyi-yili | zhouyi-yili（**跨仓库** guoxue-skills） | 0 | 2 | 1 | ⚠️ 常识领域基线基本持平（见第五节） |

## 三、逐 run 明细（18 行）

| 卡 | 会话 | with 命中 | without 命中 | 正向差 | 等级 |
|---|---|---|---|---|---|
| tongjian | run-1 | 3 | 0 | 3 | significant |
| tongjian | run-2 | 3 | 0 | 3 | significant |
| tongjian | run-3 | 4 | 0 | 4 | significant |
| mengzi | run-1 | 3 | 0 | 3 | significant |
| mengzi | run-2 | 4 | 1 | 3 | significant |
| mengzi | run-3 | 4 | 1 | 3 | significant |
| five-affairs | run-1 | 4 | 3 | 1 | moderate |
| five-affairs | run-2 | 4 | 3 | 1 | moderate |
| five-affairs | run-3 | 4 | 3 | 1 | moderate |
| hanfei | run-1 | 4 | 0 | 4 | significant |
| hanfei | run-2 | 4 | 0 | 4 | significant |
| hanfei | run-3 | 4 | 1 | 3 | significant |
| xunzi | run-1 | 2 | 2 | 1 | moderate |
| xunzi | run-2 | 2 | 1 | 1 | moderate |
| xunzi | run-3 | 3 | 1 | 2 | significant |
| lunyu | run-1 | 4 | 1 | 3 | significant |
| lunyu | run-2 | 4 | 0 | 4 | significant |
| lunyu | run-3 | 4 | 2 | 2 | moderate |
| bazi-paipan | run-1 | 3 | 3 | 1 | moderate |
| bazi-paipan | run-2 | 4 | 4 | 0 | none |
| bazi-paipan | run-3 | 3 | 4 | 0 | none |
| quming-xue | run-1 | 4 | 3 | 1 | moderate |
| quming-xue | run-2 | 3 | 3 | 0 | none |
| quming-xue | run-3 | 4 | 3 | 1 | moderate |
| zhouyi-yili | run-1 | 3 | 3 | 0 | none |
| zhouyi-yili | run-2 | 4 | 2 | 2 | moderate |
| zhouyi-yili | run-3 | 4 | 2 | 2 | moderate |

## 四、边界（不夸大）

1. **同族模型**：with/without 两侧均由同一模型家族的不同会话产出，**不是跨模型因果证据**；
   重复实验只解决「单次会话的偶然性」，没解决「同族互评偏宽松」。
2. **机械信号 ≠ 有用**：四道信号只判「可机械判别的行文特征」，不覆盖结论正确性、说服力、
   以及用户实际是否因此做出更好的决定。
3. **`none` 是合法结论，且已被实测证明**：本仓 6 张典籍卡 18 次无 `none`，但跨仓库的
   `bazi-paipan` 3 次里出现 **2 次 none + 1 次 moderate**（见第五节）——`none` 不是理论可能，是既成事实。
4. **n=3 覆盖口径**：本仓 6 张典籍/文本卡全部完成；跨仓库仅 `bazi-paipan` 完成试点（其余外部卡未做）。
   「locator_citation 唯一稳定区分信号」的结论**只对本仓典籍卡成立**，不外推到常识领域卡。
5. **five-affairs 的增量实质≈citation grounding**：其 without 侧三次都命中 verbatim_quote/boundary_declared/
   card_term（3/4），with 侧只能再多加 locator_citation（净差恒 +1）。

## 五、跨仓库卡的诚实发现（2026-10-12 新增，试点：bazi-paipan + quming-xue + zhouyi-yili）

三张卡均位于**独立仓库 `guoxue-skills/`**，是本项目首次做的**跨仓库 utility 对照**
（`td.py eval-kit utility --card` 指向兄弟仓库 SKILL.md，答案落本仓）。三张结果**一致**，且与 6 张本仓典籍卡**截然不同**：

| 卡 | run-1 | run-2 | run-3 | 合计 |
|---|---|---|---|---|
| bazi-paipan | +1 moderate | 0 none | 0 none | 1 moderate + 2 none |
| quming-xue | +1 moderate | 0 none | +1 moderate | 2 moderate + 1 none |
| zhouyi-yili | 0 none | +2 moderate | +2 moderate | 2 moderate + 1 none |

**共同根因**：八字/取名/周易都是**模型训练语料里充足的常识领域**。no-skill 基线（凭通用命理/易学知识）就能
引《渊海子平》《繫辭》、给出立春分界/五虎遁/喜用神主驱动/当位得中/子时两口径、并拒绝预测——四道机械信号几乎全中。
也就是说，`locator_citation` 在这里**基本不再是区分信号**（bazi/quming 的 with=without=1；zhouyi 因繁體引语+精确段号基线较难复现，run-2/3 才拉开 +2），卡在机械信号层面的边际增益趋零。

**这个发现的价值（不是失败，是校准）**：
1. 它证伪了「locator_citation 是普适区分信号」的过度外推——该信号只在**模型没有原文记忆的典籍/文本卡**上构成区分。
2. 它说明四道机械信号**测不到卡在常识领域的真实价值**：bazi-paipan 的真正价值是「可验证算对、可复核」
   （脚本 `paipan.py` + 交节时刻 trace），而这是机械行文信号不覆盖的维度（边界声明 2 已预警）。
3. 它把 P2「扩到普遍水平」的目标**重新定性**：对常识领域卡，utility 机械信号的预期结论就是「none」，
   这不等于卡没用，而等于**这套信号选错了尺子**。要衡量常识领域卡，需要换尺子（如算对率/可复现性），不是继续堆 n=3。

**因此**：`t_utility_n3_runs_complete` 的 locator 不变量**只覆盖 6 张本仓典籍卡**；bazi-paipan 由
`t_utility_n3_crossrepo_caveat` 单独钉住「已诚实披露此边界」，防止后续把 none 粉饰成稳定增益。
