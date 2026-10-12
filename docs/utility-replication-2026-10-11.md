# 效用对照的**重复实验**（n=3）— 2026-10-11

> 这份报告回答复评（2026-10-11）第 4 项的一半：**「n≥3」的重复实验**。
> 此前 `utility-evidence-2026-10-10.md` 的每卡对照只有 **1 次会话（n=1）**，不构成统计重复。
> 本轮对**同一张卡、同一个题库**跑了 **3 次独立会话**，看「显著增益」的结论是否可复现。

## 一、实验设计

- **对象**：`tongjian-decision-trace`（資治通鑑）、`mengzi-refutation`（孟子）两张开放卡。
- **题库**：沿用既有 `docs/utility-baseline/<card>/questions.json`，三轮会话题目**逐字相同**（已复制到 `run-2/` `run-3/`）。
- **两组**：`with`（给卡片）/ `without`（**不给卡片**，只给题库，且明确禁止其打开任何 SKILL.md 或既有答案）。
- **判据**：四道机械信号——`locator_citation` 定位引用 / `verbatim_quote` 引语复用 / `boundary_declared` 边界声明 / `card_term` 术语复用。
- **泄漏剔除**：题面已出现的卡片术语（`名分` / `以羊易牛`、`取譬设问`）由 `--questions` 自动剔除，不算卡片功劳。
- **命令**（可复跑）：

```bash
# 例：tongjian 第 2 次会话
python3 scripts/td.py eval-kit utility \
  --card examples/open-bundle/skills/tongjian-decision-trace/SKILL.md \
  --with   docs/utility-baseline/tongjian/run-2/answers.json \
  --without docs/utility-baseline/tongjian/run-2/answers-baseline.json \
  --questions docs/utility-baseline/tongjian/run-2/questions.json \
  --subject tongjian-decision-trace \
  --out docs/utility-baseline/tongjian/run-2/utility-report.json
```

## 二、结果：6/6 次会话均为显著增益

| 卡 | 会话 | with 命中 | without 命中 | 正向差 | 等级 |
|---|---|---|---|---|---|
| `tongjian-decision-trace` | run-1 | 3 | 0 | 3 | significant |
| `tongjian-decision-trace` | run-2 | 3 | 0 | 3 | significant |
| `tongjian-decision-trace` | run-3 | 4 | 0 | 4 | significant |
| `mengzi-refutation` | run-1 | 3 | 0 | 3 | significant |
| `mengzi-refutation` | run-2 | 4 | 1 | 3 | significant |
| `mengzi-refutation` | run-3 | 4 | 1 | 3 | significant |

**结论：两张卡各自 3/3 次独立会话复现了「显著增益」——结论在同族模型内是稳定的，不再是单次会话的偶发现象。**

## 三、本轮新发现（必须一起读的三条）

1. **`card_term`（术语复用）不是可靠的区分信号。**
   `mengzi` 的 run-2 / run-3 里，**没有拿到卡片**的对照组也命中了 `card_term=1`——
   因为题面本身出现了「取譬设问」「以羊易牛」，虽然这两个词已被 `leaked_terms` 剔除，
   但对照模型仍会用邻近术语作答。这与早前 `utility-evidence-2026-10-10.md` 里
   「`card_term` 在 no-skill 侧也会命中」的判断一致，本轮在**第二张卡上再次复现**。

2. **`boundary_declared`（边界声明）在 with 侧也不稳定。**
   `tongjian` 三次会话里只有 run-3 命中，run-1 / run-2 都没命中；
   `mengzi` 三次都命中。说明这道信号更依赖**题目是否正好问到边界**，而不是卡片本身。

3. **稳定复现的其实只有两道信号**：`locator_citation`（定位引用）与 `verbatim_quote`（引语复用）——
   `without` 侧在 6 次会话里**一次都没命中**。这和首份证据的结论一致：**区分度仍然集中在「定位引用」**。

## 四、边界（不夸大）

1. **同族模型**：with/without 两侧均由同一模型家族的不同会话产出，**不是跨模型因果证据**。
   重复实验解决的是「单次会话的偶然性」，**没有解决「同族互评偏宽松」**。
2. **机械信号 ≠ 有用**：四道信号只判「可机械判别的行文特征」，
   不覆盖结论正确性、说服力、以及用户实际是否因此做出更好的决定。
3. **n=3 现已覆盖 6 张卡**：tongjian / mengzi（2026-10-11）+ five-affairs / hanfei / xunzi / lunyu（2026-10-12 补做）。
   余下 9 张既存卡（five-affairs 之外的 sample-bundle 待定，以及 musks/guoxue/video 等）仍未做重复实验；
   本报告**仍不构成「所有卡都稳定复现」的证据**——只证明这 6 张开放素材卡在同族模型内可复现。
4. **无增益（`none`）仍是合法结论**：本项目不做「有增益才好用」的对外宣称。
   本轮 12 次会话无一出现 `none`，但这只因为所选 6 张卡确实都新增了 `locator_citation`；
   **它不构成「none 不会发生」的证据**，只能说明本批卡在该信号上都有增量。

## 五、补做：剩余 4 张卡的 n=3（2026-10-12）

> 把第四节第 3 条里列为「未做」的 4 张卡（lunyu / five-affairs / hanfei / xunzi）补齐 n=3 重复实验，
> 方法完全沿用第一节：同卡、同题库、三次独立会话，run-1/run-2/run-3 题目逐字相同（已复制到各 `run-N/` 目录）。
> five-affairs / hanfei / xunzi 的 run-1 来自此前顶层基线答案（已归档进 `run-1/`），lunyu 三 run 均为本轮新建
> （其基线答案此前未随仓保存，本轮先重建题库再派发独立会话）。

### 5.1 结果：12/12 次会话均为正向增益

| 卡 | 会话 | with 命中 | without 命中 | 正向差 | 等级 |
|---|---|---|---|---|---|
| `five-affairs-seven-questions` | run-1 | 4 | 3 | 1 | moderate |
| `five-affairs-seven-questions` | run-2 | 4 | 3 | 1 | moderate |
| `five-affairs-seven-questions` | run-3 | 4 | 3 | 1 | moderate |
| `hanfei-upward-advice` | run-1 | 4 | 0 | 4 | significant |
| `hanfei-upward-advice` | run-2 | 4 | 0 | 4 | significant |
| `hanfei-upward-advice` | run-3 | 4 | 1 | 3 | significant |
| `xunzi-learning-order` | run-1 | 2 | 2 | 1 | moderate |
| `xunzi-learning-order` | run-2 | 2 | 1 | 1 | moderate |
| `xunzi-learning-order` | run-3 | 3 | 1 | 2 | significant |
| `lunyu-conduct` | run-1 | 4 | 1 | 3 | significant |
| `lunyu-conduct` | run-2 | 4 | 0 | 4 | significant |
| `lunyu-conduct` | run-3 | 4 | 2 | 2 | moderate |

**结论：4 张卡各 3/3 次会话均复现正向增益，没有一次出现负向或零增益。**
但等级分化明显——`hanfei` / `lunyu` 多为 significant，`five-affairs` 稳定停在 moderate，`xunzi` 介于两者之间。

### 5.2 本轮巩固的三条发现

1. **`locator_citation`（定位引用）是全 6 卡唯一稳定区分信号。**
   在 6 张卡 × 3 run = **18 次会话**里，`locator_citation` 的 with 侧 **18/18 命中**、without 侧 **18/18 零命中**。
   这与第三节第 3 条在 tongjian/mengzi 上的结论完全一致，现已扩到全部 6 张开放素材卡。
   其余三道信号（verbatim_quote / boundary_declared / card_term）在 6 张卡上各自有噪点，
   **有时 without 侧也会命中**（最典型是 five-affairs 的 without 侧命中 3/4 信号）。

2. **`five-affairs` 的增量实质上只有「定位引用」。**
   它的 without 侧在三次会话里都命中了 verbatim_quote / boundary_declared / card_term（3/4），
   所以 with 侧只能再多加一个 locator_citation（净差恒为 +1，稳定 moderate）。
   **诚实结论：five-affairs 对该题库的边际价值≈ citation grounding，其余机械特征模型不靠卡片也能产出。**

3. **等级按卡分层，不按 run 抖动太多。**
   five-affairs 三次全 moderate、hanfei 三次全 significant、xunzi 两次 moderate 一次 significant、lunyu 两次 significant 一次 moderate——
   同一张卡的 run 间等级基本稳定，说明等级主要由「卡本身的信号结构」决定，而非会话偶然。

### 5.3 与第四节边界的衔接

- 第四节第 3 条已改为「n=3 现已覆盖 6 张卡」，并保留「不构成所有卡稳定复现的证据」的限制。
- 第四节第 4 条补充：本轮 12 次无 `none` 只是因为所选卡都新增了 locator_citation，不代表 `none` 不可能。
- 同族模型、机械信号≠有用 两条边界（第四节 1、2）对 4 张新卡同样成立，未变。

### 5.4 聚合汇总与防漂移守卫

- 6 卡 × 3 run = **18 行**的完整明细、每卡 n=3 汇总、以及「locator_citation 恒为唯一区分信号」结论，已汇总到
  `docs/utility-baseline/n3-aggregate.md`（机器可读版 `n3-aggregate.json`）。
- 新增 e2e 守卫 `t_utility_n3_runs_complete`：钉住 6 张卡 run-1/2/3 结构完整、每份 `utility-report.json`
  信号齐全且 gain 合法，并强制 locator_citation 在 18 次会话中 with 全中 / without 全零。
  任何卡缺 run、报告结构非法、或 without 侧也命中 locator_citation（「唯一稳定区分信号」结论被破坏），e2e 即红。
