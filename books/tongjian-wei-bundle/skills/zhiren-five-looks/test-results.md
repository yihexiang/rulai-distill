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
