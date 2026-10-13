# test-results · cai-de-two-column（才德两栏 · 可寄重任者的分栏评估）

> 状态件：如实记录本卡「已跑」与「待跑」的边界。**Phase 4 尚未运行，本文件不包含任何 Phase 4 结果数字**——
> 触发通过率、precision/recall、FIDELITY 总分一律留空到真跑之后，不预估、不填占位数。

| 阶段 | 内容 | 状态 | 证据 |
|---|---|---|---|
| 建卡自验（静态） | validate / anchor / lint-quotes / output-eval | ✅ 已跑（2026-10-13，托管 Python 3.13.12） | 下方「已跑」节的实跑输出 |
| Phase 4 · 压力测试 | trigger（跨技能诱饵 + 兄弟混淆）+ 双 Agent 评测 | ⬜ **待运行** | 下方「待跑」节的复跑命令；前置条件未齐（bundle.json 未建），见「已知边界」 |
| Phase 4 · FIDELITY | eval-kit 独立答题 + 双评分 + 分差门禁 | ⬜ **待运行** | 同上；eval-kit init 已试跑通过（生成 7 道种子题到 /tmp），答题与评分未做 |

## 已跑：建卡静态自验（2026-10-13）

统一用托管 Python（`/usr/bin/python3` 是 3.9，会假失败）：

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill
```

### 1) validate —— error 0 / warn 0

```
$ $PY scripts/td.py validate books/tongjian-wei-bundle/skills/cai-de-two-column
🔍 校验：books/tongjian-wei-bundle/skills/cai-de-two-column
✅ 无问题
统计：技能卡 1 / 文档 0 · error 0 / warn 0
```

### 2) anchor —— PASS，67 条带段号引语全部锚定命中，0 挂错

```
$ $PY scripts/td.py anchor books/tongjian-wei-bundle/skills/cai-de-two-column/SKILL.md \
      --corpus corpus/anchored/src-01-tongjian-wei.md
...
✅ 判定 PASS：67 条带段号标注的引语全部锚定在声明的段号内；另有 25 条无 §N 标注、不可定位（未核验）
```

- 判定明细（`--json-out` 导出复核）：`{'UNANCHORED': 25, 'ANCHOR_HIT': 67}`，`partial: []`，`failures: []`。
- 25 条 UNANCHORED 经逐条人工核对，均为**作者自造短语**（如「若其以才行不仁，谁能制之」「无人能制」）或 **A2 语言信号里的用户原话**，不是语料引语，不判失败（与 verify-quotes / lint-quotes「无出处即跳过」同口径）。
- 另做过一次**字节级复核**（不走显示层，直接比 Unicode 码点）：卡片中带 `§N「…」` 前缀式标注的 **58 条引语全部为对应【第N段】语料的精确子串**（0 失配；其余 9 条为 <8 字短引语或并列／后缀式标注，由 anchor 的短引语通道核验命中）。复核用一次性 Python 脚本对语料原串做 `in` 判断，未落盘。

### 3) lint-quotes —— 干净

```
$ $PY scripts/td.py lint-quotes books/tongjian-wei-bundle/skills/cai-de-two-column/SKILL.md \
      --corpus corpus/anchored/src-01-tongjian-wei.md
   检查引语 80 条
✅ 未发现用字不一致（简繁/异体）
```

### 4) output-eval —— 通过，六段齐全

```
$ $PY scripts/td.py output-eval books/tongjian-wei-bundle/skills/cai-de-two-column/SKILL.md
输出评测 · SKILL.md
   规模：11005 字符 / 8080 tokens
   六段：齐全
   引语 1 条
```

## 待跑：Phase 4 压力测试 + FIDELITY（复跑命令）

> 以下命令**均未执行出结果**。触发测试与 FIDELITY 需要：① 本卡登记进 `books/tongjian-wei-bundle/bundle.json`（当前该文件未建）；② 独立答题 Agent 与 ≥2 个不同标识的评分 Agent。两者都不属于建卡子 Agent 的职责范围，故整体留空。

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

# ── 0) 前置：把本卡登记进 bundle.json（trigger build 读它；未建则命令报错）
#    books/tongjian-wei-bundle/bundle.json → skills: [{ "slug": "cai-de-two-column", "description": ... }]

# ── 1) 触发测试（bundle 级；本卡 test-prompts.json 的 prompt 在此汇入套件）
$PY scripts/td.py trigger build books/tongjian-wei-bundle
$PY scripts/td.py trigger split books/tongjian-wei-bundle/eval-suite.json
$PY scripts/td.py trigger record books/tongjian-wei-bundle/eval-suite.json
#    （把 skills_in_scope 全部给被测 Agent 做选择题，作答填进 answers.json）
$PY scripts/td.py trigger score books/tongjian-wei-bundle/eval-suite.json answers.json

# ── 2) 独立评测套件（双 Agent 答题 + 双评分；init 已试跑通过，见下）
$PY scripts/td.py eval-kit init books/tongjian-wei-bundle/skills/cai-de-two-column/SKILL.md \
      --out books/tongjian-wei-bundle/skills/cai-de-two-column/eval-kit
#    （独立答题 Agent 填 answers.json；source=human 的题尤其 edge_honesty 必须人工补）
$PY scripts/td.py eval-kit check books/tongjian-wei-bundle/skills/cai-de-two-column/eval-kit/answers.json \
      books/tongjian-wei-bundle/skills/cai-de-two-column/eval-kit/scores-1.json \
      books/tongjian-wei-bundle/skills/cai-de-two-column/eval-kit/scores-2.json \
      --subject cai-de-two-column
```

判读口径（跑完后按此填写，不许先填）：

- `trigger score`：通过率 / precision / recall / F1 / **诱饵通过率** / **兄弟混淆率**；容错 0。
  本卡的预期考点：`no-trigger-1`（新来的经理怎么判断靠不靠谱）必须判给 `zhiren-five-looks` 而不是本卡——
  这是本卡与知人五视的分界题（观察 vs 分栏评估）；`no-trigger-2` 必须判给 `tongjian-decision-trace`。
- `eval-kit check`：评分者 ≥2 个不同标识、分差门禁、总分 /100 与等级；不过则产出 `.rejected.json`，不得据此宣称质量。

eval-kit init 试跑记录（2026-10-13，输出到 /tmp，未入包）：

```
$ $PY scripts/td.py eval-kit init books/tongjian-wei-bundle/skills/cai-de-two-column/SKILL.md --out /tmp/eval-kit-cai-de
✅ ['questions.json', 'answers.template.json', 'scores.template.json', 'README.md'] → /tmp/eval-kit-cai-de（7 道种子题）
```

## 卡级题库（test-prompts.json）与 Phase 4 的对应

| 文件条目 | 类型 | 预期 |
|---|---|---|
| trigger-1（技术合伙人数据动手脚，给多少权限） | should_trigger | 走两栏打分，定档 + 问谁能制之 + 三选一处置 |
| trigger-2（业绩最好但口碑差的销售主管提不提） | should_trigger | 同上；「口碑」须落到可指名事件才进德栏 |
| trigger-3（两个联合创始人定谁做 CEO） | should_trigger | 两人各列两栏、分别定档后排序 |
| no-trigger-1（新来的经理怎么判断靠不靠谱） | sibling → `zhiren-five-looks` | **不触发本卡**：观察/采证题，非分栏评估题 |
| no-trigger-2（破格提拔后团队议论纷纷） | sibling → `tongjian-decision-trace` | **不触发本卡**：读已发生举措的连锁反应 |
| no-trigger-3（智伯之亡反映什么历史规律） | decoy | **不触发本卡**：历史阐释题；本卡不做历史点评 |

## 已知边界（如实披露）

1. **bundle.json 未建**：`books/tongjian-wei-bundle/` 下尚无 bundle.json，`trigger build` 暂不可跑；validate 对本卡目录单独跑不受影响（已过）。
2. **25 条无 §N 引语**：均为作者自造短语或用户原话（语言信号），不声称来自语料；anchor 按 UNANCHORED 如实计数，未充作已核验引语。
3. **语料不随技能发布**：`source_locator` 指向仓库内 `corpus/anchored/src-01-tongjian-wei.md`（随本仓库分发），读者 clone 后可用上面命令原样复算；取源与清洗见同目录 SOURCES.md。
4. **本卡未覆盖**：《資治通鑑》周紀五之后全部卷次、后世注疏考异、其他史源（《史記》《戰國策》等仅在语料校记中被引书名）；不据记忆引用未收内容。
