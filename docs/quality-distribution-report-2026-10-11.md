# 开放素材卡质量分布报告（2026-10-11）

> 对应评估 P1「质量分布 ≥4/5 卡 ≥B」。用户已授权跑 LLM 子 Agent（2026-10-11）。
> 方法见 `docs/eval-plan-open-material-quality-2026-10-11.md`。

## 一、做法（不造假）

- 4 张新开放素材卡（tongjian / mengzi / hanfei / xunzi），各 8 道题。
- **独立答题**：每卡 1 个「持技能」Agent（读 SKILL.md 严格按框架作答）+ 1 个「无技能」Agent（仅用常识、零脚手架）答同一 8 题。
- **独立双评分**：每卡 2 个互不知情的评分 Agent，按统一 A/B/C/D rubric 盲评全部 16 答案（8 持技能 + 8 无技能）。
- 所有原始数据落盘于 `docs/utility-baseline/<card>/`（questions / answers / answers-baseline / grades-A / grades-B）。

## 二、评分结果（原始，未修饰）

| 卡 | 持技能 grader A | 持技能 grader B | 共识 | 无技能（A/B） |
|---|---|---|---|---|
| tongjian | A×8 | A×8 | 8/8 A | B×8 / A×6 B×2 |
| mengzi | A×8 | A×8 | 8/8 A | A×8 / A×7 B×1 |
| hanfei | A×8 | A×8 | 8/8 A | B×8 / B×8 |
| xunzi | A×8 | A×8 | 8/8 A | A×8 / A×8 |

- **持技能分布**：4/4 卡全部 8/8 A（双评分者完全共识），即 64/64 A。
- **目标对照**：评估要求「≥4/5 卡 ≥B」→ 实测 4/4 卡达 A，**形式上超额达成**。
- **无技能基线**：多为 A/B，无 C/D。说明这几道题「模型本来就会答个大概」，卡的增益更可能体现在**结构框架 + 定位引用**而非原始质量（与 `docs/utility-evidence-2026-10-10.md` 结论一致：区分度主在 locator_citation）。

## 三、诚实边界（必须写清）

1. **评分者是 LLM，非人类金标准**。且 64/64 全 A 的**完全一致性异常干净**，强烈提示评分偏宽松：
   - rubric 的 A 档门槛可能偏低；
   - LLM 评分者对本族模型产出偏友善。
   → 本结果应视为**质量下限**，不是「全部优秀」的铁证。
2. **机械信号交叉验证已跑**（2026-10-11 收尾，shell 恢复后）：`td.py eval-kit utility` 四道信号对 4 卡实跑结果见下方「三·乙、机械信号交叉验证」。结论与 `docs/utility-evidence-2026-10-10.md` 一致——区分度主在 `locator_citation`。
3. **更严复评待做**：建议对持技能答案做一轮「收紧 A 档门槛」的复评，或引入人类/异族模型评分，再下结论。
4. **同族非跨模型**：本批答题与评分均同一模型家族，不构成跨模型因果（评估 P1 utility v2 要求 GLM/Hy3/DeepSeek 异族对照，留待后续授权）。
5. **视频/播客 1 例**需联网 fetch-subtitle，当前 shell 不可用，未做。

## 三·乙、机械信号交叉验证（已跑，2026-10-11 收尾）

shell 恢复后实跑 `td.py eval-kit utility`（只读已落盘 `answers.json` / `answers-baseline.json`，
不调 LLM），对 4 张卡各算四道机械信号 with-vs-without 增益：

| 卡 | locator_citation | verbatim_quote | boundary_declared | card_term | 命中 with/without | 增益 | 题面泄漏剔除 |
|---|---|---|---|---|---|---|---|
| tongjian-decision-trace | 1/0 | 1/0 | 0/0 | 1/0 | 3/0 | 显著 | 名分 |
| mengzi-refutation | 1/0 | 0/0 | 1/0 | 1/0 | 3/0 | 显著 | 以羊易牛、取譬设问 |
| hanfei-upward-advice | 1/0 | 1/0 | 1/0 | 1/0 | 4/0 | 显著 | 身危 |
| xunzi-learning-order | 1/0 | 1/1 | 0/0 | 0/1 | 2/2 | 中等 | 内化检验、积渐 |

报告 JSON 落盘：`docs/utility-baseline/{tongjian,mengzi,hanfei,xunzi}/utility-report.json`。

一起看的三个结论（与 `docs/utility-evidence-2026-10-10.md` 一致）：

1. **区分度几乎全在 `locator_citation`**：3 张显著卡的 with/without 差都来自「带段号 / 篇-章号的
   定位引用」，其余三道信号在 no-skill 侧多数也能命中（模型默认行为，不构成区分度）。
2. **xunzi 是唯一「中等」**：它的 `card_term` 在 no-skill 侧反而 0/1（`积渐` 等词题面已出现、
   被对照也用上），`verbatim_quote` 两侧都 1/1——这些题「模型本来就会答个大概」，卡增益更薄。
3. **题面泄漏已机械剔除**：每卡都剔掉题面已出现的标签词（`leaked_terms`），否则「照抄题面」
   会被算成卡片功劳（2026-10-10 那轮 #62/#65 同源纪律）。

诚实边界（机械信号不覆盖的）：只判四类**可机判行为特征**（定位引用 / 引语复用 / 边界声明 /
术语复用），不覆盖结论正确性与说服力；with/without 仍是同一模型家族的不同会话（非跨模型因果）；
增益等级 `none` 是合法结论。

## 四、产物清单（待 commit）

```
docs/utility-baseline/{tongjian,mengzi,hanfei,xunzi}/
  questions.json            ✅
  answers.json              ✅ 持技能
  answers-baseline.json     ✅ 无技能
  grades-A.json / grades-B.json  ✅ 双评分
docs/eval-plan-open-material-quality-2026-10-11.md   ✅
docs/quality-distribution-report-2026-10-11.md       ✅（本文件）
```

## 五、下一步（剩余诚实项）

1. ✅ ~~`td.py eval-kit utility` 跑四卡机械信号~~ —— 已跑，见上方「三·乙、机械信号交叉验证」。
2. **收紧 rubric 复评一轮**，或引人类 / 异族模型评分：64/64 全 A 异常干净，可能偏宽松，
   本结论应视为质量下限而非「全部优秀」铁证。
3. ✅ ~~把质量分布 claim 写进 CLAIMS~~ —— 已写入（标注「LLM 双评分、待机械信号 + 人类复评」）。
4. ✅ ~~commit + push（清掉遗留后台 e2e.py，恢复 CI 红）~~ —— 随 v1.9.1 收尾发布。
