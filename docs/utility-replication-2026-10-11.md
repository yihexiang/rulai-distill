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
3. **n=3 只覆盖 2 张卡**：其余 4 张（lunyu / five-affairs / hanfei / xunzi）仍为 n=1，未做重复实验。
   本报告不构成「所有卡都稳定复现」的证据。
4. **无增益（`none`）仍是合法结论**：本项目不做「有增益才好用」的对外宣称。
