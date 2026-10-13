# test-results · jiao-di-cycle

> 状态件：如实记录本卡的测试进度。**Phase 4（触发压力测试 + 双 Agent 评测）尚未运行**，
> 本文件不写任何得分、通过率、F1 数字——那些要等 Phase 4 真跑出来才能记。
> 建卡时已完成的机械自验（有实跑输出）单独列在下方，与 Phase 4 分开，不冒充评测结果。

## 状态总览

| 项 | 状态 | 说明 |
|---|---|---|
| 建卡机械自验（validate / anchor / lint-quotes / output-eval / verify-quotes） | ✅ 已跑（2026-10-13，建卡当天） | 命令与真实输出见下；属**作者自验**，不是 Phase 4 评测 |
| 题库（`test-prompts.json`） | ✅ 已写 | 3 should_trigger + 3 should_not_trigger（含 1 条跨卡诱饵指向 chunchi-structure） |
| Phase 4 · trigger 压力测试（跨技能诱饵 + 判分） | ⬜ **待运行** | 需 bundle.json（Phase 5 compile 产物），当前不存在，见复跑命令 |
| Phase 4 · eval-kit 双 Agent 评测 + FIDELITY | ⬜ **待运行** | 需 `eval-kit init` 生成答题/评分模板并人工补齐题库，见复跑命令 |
| FIDELITY.json | ⬜ 未产出 | Phase 4 跑完且通过才写；**不预填** |

## 建卡时已跑的机械自验（真实输出，非 Phase 4）

执行环境：托管 Python `/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3`，
仓库根 `/Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill`。

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

$PY scripts/td.py validate books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md
# → 校验：books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md
#   ✅ 无问题
#   统计：技能卡 1 / 文档 0 · error 0 / warn 0

$PY scripts/td.py anchor books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md \
    --corpus corpus/anchored/src-01-tongjian-wei.md
# → ✅ 判定 PASS：68 条带段号标注的引语全部锚定在声明的段号内；
#   另有 19 条无 §N 标注、不可定位（未核验）——多为 A2 语言信号等用户口话引文，非语料引语

$PY scripts/td.py lint-quotes books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md \
    --corpus corpus/anchored/src-01-tongjian-wei.md
# → ✅ 未发现用字不一致（简繁/异体）

$PY scripts/td.py verify-quotes books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md \
    corpus/anchored/src-01-tongjian-wei.md
# → 引用 14 个（书类引用块 14）；逐字引语核验 14 条 → 命中 14 条
#   ✅ 全部引语在语料中核到

$PY scripts/td.py output-eval books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md
# → 规模：11484 字符 / 8612 tokens；六段：齐全；引语 0 条（该命令只统计特定形状，核验以 anchor/verify-quotes 为准）
```

以上五项全部实跑通过（exit 0）。**这不是 Phase 4 的成绩**——它只证明卡的结构、引语与段号可机械复核，
不证明卡在真实提问下会被正确触发、不证明跨技能诱饵能守住。

## Phase 4 待运行项与复跑命令

### 4.1 trigger 压力测试（本卡题库的直接判分）

当前 `books/tongjian-wei-bundle/bundle.json` 不存在（Phase 5 compile 才生成），
`td.py trigger build` 直接跑会报「文件不存在」。复跑路径（按序）：

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

# 1) 先有 bundle.json（Phase 5 产物；若 Phase 5 未到，可先用 td.py compile 预演，或手动按 schema 构造）
$PY scripts/td.py compile books/tongjian-wei-bundle        # 产物含 bundle.json

# 2) 从 bundle 生成触发测试套件骨架
$PY scripts/td.py trigger build books/tongjian-wei-bundle --out books/tongjian-wei-bundle/skills/jiao-di-cycle/trigger-suite

# 3) 把本卡 test-prompts.json 的 6 条题（3 should_trigger + 3 should_not_trigger）并入套件
#    （snt-1 是跨卡诱饵，必须保留——它测的是本卡与 chunchi-structure 的触发边界）

# 4) 盲测 + 机械判分（容错 0，输出 P/R/F1）
$PY scripts/td.py trigger prepare books/tongjian-wei-bundle --out <盲测包>
$PY scripts/td.py trigger score   <盲测包>
```

**判定门槛**（Phase 4 出数后才填，现在不预设）：3 条 should_trigger 全部触发、3 条 should_not_trigger
全部不触发，尤其 snt-1（跨卡诱饵）不得被本卡接走。

### 4.2 eval-kit 双 Agent 评测 + FIDELITY

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

# 1) 生成本卡评测套件（题库/答题模板/评分模板/工作流说明）
$PY scripts/td.py eval-kit init books/tongjian-wei-bundle/skills/jiao-di-cycle/SKILL.md \
    --out books/tongjian-wei-bundle/skills/jiao-di-cycle/eval-kit

# 2) 人工补齐题库：至少覆盖三类——consistency（用卡 vs 不用卡的结论差异）、
#    cross-skill（与 chunchi-structure 的分界，对应 test-prompts.json 的 snt-1）、
#    edge_honesty（素材外问题，底稿只到周紀，不得拿史料权威包装编造）

# 3) 双 Agent 答题 + 评分 + 交叉复核
$PY scripts/td.py eval-kit check books/tongjian-wei-bundle/skills/jiao-di-cycle/eval-kit

# 4) 同题对照（no-skill vs with-skill 的机械增益）
$PY scripts/td.py eval-kit utility books/tongjian-wei-bundle/skills/jiao-di-cycle/eval-kit

# 5) 通过后才写 FIDELITY.json（当前未产出，不预填）
```

## 已知风险（Phase 4 重点盯）

1. **跨卡诱饵 snt-1**：本卡与 `chunchi-structure` 共用第 3 段智伯叙事（张孟谈「脣亡則齒寒」），
   语言信号可能互相抢——这是本卡最可能被误触发的一条，判分时优先看它。
2. **snt-2 占断题**：测的是素材诚实度——本卡不得给出任何「择日/吉凶」结论，
   也不得把《資治通鑑》的权威性挪用到占断上。
3. **st-1/st-2 的『让不让』提问**：用户问的是二元问题，本卡的正确行为是先判循环再输出三选一
   （顶/予/待）——若答成简单的『让』或『不让』，说明 E 段没被执行到位， consistency 维度应扣分。
