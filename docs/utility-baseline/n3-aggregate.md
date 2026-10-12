# 效用对照 n=3 重复实验 · 聚合汇总（2026-10-12）

> 机器可读版：`n3-aggregate.json`。逐 run 原始报告在 `docs/utility-baseline/<card>/run-N/utility-report.json`。

> 守卫：`tests/e2e.py` 的 `t_utility_n3_runs_complete` 钉住本文件结论——任何卡缺 run、报告结构非法、

> 或 `locator_citation` 在某一 with/without 侧偏离「with 全中 / without 全零」，e2e 即红。

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

## 四、边界（不夸大）

1. **同族模型**：with/without 两侧均由同一模型家族的不同会话产出，**不是跨模型因果证据**；
   重复实验只解决「单次会话的偶然性」，没解决「同族互评偏宽松」。
2. **机械信号 ≠ 有用**：四道信号只判「可机械判别的行文特征」，不覆盖结论正确性、说服力、
   以及用户实际是否因此做出更好的决定。
3. **`none` 仍是合法结论**：本轮 18 次无 `none` 只因为所选 6 张卡确实都新增了 `locator_citation`，
   不代表 `none` 不可能。
4. **n=3 覆盖 6 张卡**：tongjian/mengzi（2026-10-11）+ five-affairs/hanfei/xunzi/lunyu（2026-10-12）；
   余下 9 张既存卡（musk/guoxue/video 等）仍未做重复实验，不构成「所有卡都稳定复现」的证据。
5. **five-affairs 的增量实质≈citation grounding**：其 without 侧三次都命中 verbatim_quote/boundary_declared/
   card_term（3/4），with 侧只能再多加 locator_citation（净差恒 +1）。
