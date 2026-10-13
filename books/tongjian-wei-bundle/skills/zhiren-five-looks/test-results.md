# test-results · zhiren-five-looks 触发压力测试结果

> 状态：**Phase 4 待运行**（2026-10-13 建卡。本文件不填任何未实测的数字——没有跑过的测试不写通过率）
> 套件：同目录 `test-prompts.json`（suite_id `zhiren-five-looks-trigger-v1`，split_seed 42，train_ratio 0.6）
> 配比：should_trigger ×3 / should_not_trigger ×2（含 1 条跨卡诱饵 d02）/ should_trigger_sibling ×1 —— 合 `methodology/04-pressure-test.md` 的 3 / 2-3 / ≥1 要求
> 范围声明：本文件只记 Phase 4 触发压力测试。建卡时的静态自检（validate / anchor / lint-quotes / output-eval / verify-quotes）不属 Phase 4，已实跑通过，复跑命令见文末附录——**未通过项不会留在卡里，但 Phase 4 的通过率要等真跑出来才算**。

## 开跑前提（未满足前，跑出来的数不算数）

1. 同 bundle 的 `cai-de-two-column` 卡已建卡——两条跨卡用例（d02／x01）的期望答案是它；它不在场时这两条无法判对
2. 用 `cai-de-two-column` 建卡后的真实 frontmatter description 替换本套件 `skills_in_scope` 里的占位描述（当前该项已显式标注【占位描述·待建卡】）
3. 答题 Agent 必须是**干净上下文的独立 sub-agent**；候选技能清单只给 name + description，不给本文件、不给 SKILL.md 正文

## 待运行项与复跑命令

在仓库根目录执行（**必须用托管 Python**，`/usr/bin/python3` 是 3.9 会假失败）：

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill
SUITE=books/tongjian-wei-bundle/skills/zhiren-five-looks/test-prompts.json
OUT=books/tongjian-wei-bundle/skills/zhiren-five-looks

# 1) 固定种子切 train/validation（validation 在选版前保持隐藏）
$PY scripts/td.py trigger split "$SUITE" --seed 42 --ratio 0.6 --out "$OUT/trigger-split.json"

# 2) 盲测任务包（只含 prompt + 候选技能清单，剥掉 expect/why）
$PY scripts/td.py trigger prepare "$SUITE" --out "$OUT/eval-kit" --set train

# 3) 独立 sub-agent 答题：把 blind-tasks.json 的 skills_in_scope 与 cases 交给它，
#    回收作答后转成 JSON（{"case_id": "selected_skill 或 none"}，或 {"answers": {...}}）——score 只吃 JSON，不吃 jsonl

# 4) 机械判分（容错 0，输出 P/R/F1 + 诱饵通过率 + 兄弟混淆率）
$PY scripts/td.py trigger score "$SUITE" "$OUT/eval-kit/answers.json" --out "$OUT/trigger-eval.json"

# 5) 选版后只跑一次 validation（用未参与调优的保留用例）
$PY scripts/td.py trigger prepare "$SUITE" --out "$OUT/eval-kit" --set validation
#    → 再走 3)、4)
```

## 判读口径（开跑前写定，跑完不许改）

- 通过线：should_trigger 3/3 命中；should_not_trigger 全部忍住；sibling 用例（d02／x01）指向 `cai-de-two-column`
- 诱饵（should_not_trigger）**容错为 0**——被本卡抢答一条即整体未过
- 若 d02／x01 被 `cai-de-two-column` 反向抢答（该卡把采证题当打分题接），按 `methodology/04-pressure-test.md` 修复决策树处理：**两张卡的 B 段『易混淆辨析』都要重写，只改一张无效**
- 失败时先判断是测试设计问题还是技能设计问题；**禁止为了通过改答案**，改预期必须留独立理由

## 回归纪律

- 已看过的失败用例加入回归集；最终验收用**未参与调优的 validation 保留用例**，选完版只跑一次
- 报告必须记录：宿主／模型版本、实际运行条件、是否为独立 sub-agent（还是 fallback 自测）

## 附录 · 建卡时静态自检的复跑命令（非 Phase 4）

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill
CARD=books/tongjian-wei-bundle/skills/zhiren-five-looks/SKILL.md
CORPUS=corpus/anchored/src-01-tongjian-wei.md

$PY scripts/td.py validate "$CARD"                                  # error 0 / warn 0
$PY scripts/td.py anchor   "$CARD" --corpus "$CORPUS"               # 段号锚定 PASS
$PY scripts/td.py verify-quotes "$CARD" "$CORPUS"                   # 逐字存在性核验
$PY scripts/td.py lint-quotes  "$CARD" --corpus "$CORPUS"           # 用字/省略号体检
$PY scripts/td.py output-eval  "$CARD"                              # 六段结构体检
```


## Phase 4 实测结果（2026-10-13 已运行 · 不再「待运行」）

> 本文开头若仍写着「Phase 4 待运行」，**以本节为准**——那是建卡时的状态，Phase 4 已于当日跑完。
> 汇总报告见 `docs/fidelity-phase4b-2026-10-13.md`（含方法、裁定理由与诚实边界）。

### 4a · 触发压力测试（bundle 级，10 条用例）

本卡被正确触发 **1/1**；bundle 级诱饵 2/2、兄弟互诱 2/2、**兄弟混淆率 0.0**。

套件与原件：`books/tongjian-wei-bundle/eval/trigger-score.json`（P=R=F1=1.0，诱饵通过率 1.0，未作答 0）。
> 注：判分曾因 `trigger prepare` 产出 JSONL 而 `trigger score` 只收字典，把 10 条全对的答案整批判成「未作答」（缺陷 #81，已修并由 `t_trigger_score_accepts_list` 守住）。

### 4b · FIDELITY 双 Agent 独立质检（本卡）

| 轮次 | rubric | 总分 | 五维 |
|---|---|---|---|
| 第 1 轮 | 标准 `scoring-rubric.md` | **100** | 30/20/20/15/15 |
| 第 2 轮 | 严格 `scoring-rubric-strict.md` | **76** | 22/12/20/10/12 |

分差 **24** > 阈值 10 → `eval-kit check` 判定 `needs_human_review`，产物为
`eval/fidelity/zhiren-five-looks/FIDELITY.rejected.json`（**没过门禁，文件名即证据**）。

**人工复核裁定**：对外采用**严格轮 76 分（B）**作为本卡质量下限——严格轮每条扣分都引用了原文并实跑了
`verify-quotes`，标准轮虽写明多项限制却仍给满分（属"没找到扣分理由"，不是"经得起挑"）。

严格轮最重的一条扣分：source_transparency：卡片第161行自陈可复跑命令 `grep -c "使人視"` 注『→ 2』，实跑返回 1（缺陷 #83，已修）

**反向边界（必须一起读）**：
1. `style` 维两轮**都没做真盲排**（当时套件不生成对照样本，缺陷 #82）——该维分数不可作质量证据，
   对照样本已随 `style-decoys.md` 生成，**重测待做**；
2. 严格轮 consistency 的 22/30 有相当部分是**出题器背的**（题干逐字抄 description，持卡复述即满分），
   不全是卡片的问题；#82 修复后需重测；
3. 答题者与评分者均为**同族 LLM**，跨模型／人类复评未做，不外推。

### 4b 顺带抓出并已修的卡级缺陷（缺陷 #83）

见 `docs/fidelity-phase4b-2026-10-13.md` 第五节与 `CONSTRAINTS.md` #83 行。
本卡涉及的部分已在记录同时修掉，并由 `t_cards_quotes_all_verifiable` /
`t_card_selfcheck_commands_recomputable` 两条回归测试守住——**改完不重测，不声称变好**。
