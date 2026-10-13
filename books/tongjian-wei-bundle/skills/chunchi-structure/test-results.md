# 测试结果 · chunchi-structure（唇齿结构）

> 本文件如实记录该卡的核验状态。**凡未运行的，一律标「待运行」，不填数字、不填结论。**

## 卡片信息

| 项 | 值 |
|---|---|
| slug | `chunchi-structure` |
| 标题 | 唇齿结构 · 多强博弈的连锁传导与前史类比 |
| 框架来源 | F05（`books/tongjian-wei-bundle/verified/framework.md`，三关全过、段号核对无失配、晋级 promoted） |
| 语料 | `corpus/anchored/src-01-tongjian-wei.md`（第3、128、142、143段，共 147 个【第N段】块） |
| 建卡日期 | 2026-10-13 |

## 一、已运行：建卡自验（阶段 2/3 静态核验，实跑）

以下四条命令由建卡子 Agent 在本机实跑，输出为真实结果（托管 Python 3.13.12）：

| 命令 | 结果 | 实跑输出要点 |
|---|---|---|
| `td.py validate <card>/SKILL.md` | ✅ 通过 | 技能卡 1 / 文档 0 · **error 0 / warn 0** |
| `td.py anchor <card>/SKILL.md --corpus corpus/anchored/src-01-tongjian-wei.md` | ✅ PASS | 引语 69 条：**锚定命中 60**，未标注段号 9（UNANCHORED，不判失败），挂错 0；其中短引语（<8 汉字、逐字见于语料、带 §N）纳入核验并命中 15 条 |
| `td.py lint-quotes <card>/SKILL.md --corpus ...` | ✅ 通过 | 检查引语 54 条，**未发现用字不一致（简繁/异体）**，无省略号、无归属可疑 |
| `td.py output-eval <card>/SKILL.md` | ✅ 通过 | 六段齐全；11303 字符 / 8398 tokens |

**关于 9 条 UNANCHORED 的说明**（anchor 工具如实列出、不判失败）：2 条在 frontmatter description 里作情境框定（第5、6行），1 条是本卡自造术语「崩解速率 vs 动员速率」（第136行），6 条是 A2 段「语言信号」的用户口语原话（第192-197行，语言信号框，按工具口径跳过）。它们不是来源引语，无需挂段号。

## 二、待运行：Phase 4 触发压力测试 + FIDELITY 出厂质检

**状态：Phase 4 待运行。本文件不含任何 Phase 4 数字。**

题库已按 `methodology/04-pressure-test.md` 配比备好（见同目录 `test-prompts.json`）：should_trigger 3 条、should_not_trigger 3 条（含 2 条跨卡诱饵，其中 x01 指向 `jiao-di-cycle`）。**盲测与评分尚未执行**，因此：

- 触发命中率 / 诱饵容错 / 兄弟混淆率：**待运行**
- FIDELITY 五维得分与等级：**待运行**

**前置条件（未满足，故不运行）**：

1. 盲测需要**干净上下文的独立答题 Agent**，且要给它整包技能的 name + description 列表做选择题（不是判断题）；
2. FIDELITY 需要**与答题 Agent 独立的 2 个评分 Agent**（铁律：禁止自评自证）；
3. 跨卡诱饵 x01 的对手卡 `jiao-di-cycle`（F08 骄敌循环）尚未建成，真实抢调用测试要等该卡存在后才能跑——在此之前跑出来的「不触发」只证明了半个边界。

## 三、复跑命令

在仓库根目录执行（**必须用托管 Python**，`/usr/bin/python3` 是 3.9 会假失败）：

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

# 1) 建卡自验四件套（阶段 2/3，已运行并通过——变更卡片后必须重跑）
CARD=books/tongjian-wei-bundle/skills/chunchi-structure/SKILL.md
$PY scripts/td.py validate "$CARD"
$PY scripts/td.py anchor  "$CARD" --corpus corpus/anchored/src-01-tongjian-wei.md
$PY scripts/td.py lint-quotes "$CARD" --corpus corpus/anchored/src-01-tongjian-wei.md
$PY scripts/td.py output-eval "$CARD"

# 2) Phase 4a 触发压力测试（待运行；题库已按契约格式备好，split/prepare/record 已实测可跑）
S=books/tongjian-wei-bundle/skills/chunchi-structure/test-prompts.json
$PY scripts/td.py trigger split "$S" --seed 42 --out <split.json>      # 固定种子切 train/validation
$PY scripts/td.py trigger prepare "$S" --out <盲测输出目录>              # 生成不含 expect/why 的盲测任务包
$PY scripts/td.py trigger record "$S" --out <答卷.md>                    # 生成待答问卷（候选技能全量注入）
# ↑ 到此为止都是机械步骤（已实测通过）。接下来需要**干净上下文的独立答题 Agent**：
#   把 skills_in_scope 全部 name+description 给它做选择题，作答写入 answers.json
$PY scripts/td.py trigger score "$S" answers.json --out <report.json>   # 机械判分（P/R/F1 + 诱饵容错 0）

# 3) Phase 4b FIDELITY 出厂质检（待运行）
CARD=books/tongjian-wei-bundle/skills/chunchi-structure/SKILL.md
$PY scripts/td.py eval-kit init "$CARD" --out <套件目录>
$PY scripts/td.py eval-kit check <套件目录> --answers answers.json \
    --scores scores-1.json scores-2.json --out FIDELITY.json
$PY scripts/td.py gate FIDELITY.json
```

**语料核验复算**（建卡时对 anchored 语料的全库检索确认，147 段、四条叙事段号归属，可用下面的脚本原样复算）：

```bash
$PY - <<'EOF'
import re
text = open("corpus/anchored/src-01-tongjian-wei.md", encoding="utf-8").read()
parts = re.split(r"【第(\d+)段】", text)
blocks = {int(parts[i]): parts[i+1] for i in range(1, len(parts), 2)}
print("总段数:", len(blocks))
marks = {3: "脣亡則齒寒", 128: "夫楚國，援也", 142: "扞蔽", 143: "貪暴之國"}
for seg, kw in marks.items():
    print(f"第{seg}段含「{kw}」:", kw in blocks[seg])
EOF
```

## 四、已知缺口（如实登记）

- `SOURCES.md` 未在本任务交付范围内（本任务约定只交付 SKILL.md / test-prompts.json / test-results.md 三个文件）；若后续要满足 `docs/card-authoring-spec.md` §6 的发布要求，需补取源页面 URL、抓取日期、清洗方式与「本卡明确不覆盖」清单。
- `jiao-di-cycle` 卡未建成：frontmatter 的 `composes_with` / `contrasts_with` 与跨卡诱饵 x01 目前指向一个尚不存在的 slug——这是**计划关系**，不是已发布关系；该卡建成后需重跑 validate 与 Phase 4a。
- 语料实际路径为仓库根 `corpus/anchored/src-01-tongjian-wei.md`（任务书中所写 `books/tongjian-wei-bundle/corpus/...` 不存在）；卡片 frontmatter 的 `source_locator` 按真实路径书写。
