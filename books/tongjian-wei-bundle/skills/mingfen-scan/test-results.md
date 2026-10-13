# mingfen-scan · 测试结果

> **状态：Phase 4 待运行。** 本文不含任何 Phase 4 触发评测的结果数字——建卡时未执行 trigger 评测，也不预填。
> 题库：同目录 `test-prompts.json`（3 条 should_trigger / 3 条 should_not_trigger，含 1 条跨卡诱饵 `chunchi-structure` + 1 条兄弟卡诱饵 `cai-de-two-column` + 1 条一般性诱饵）。

## 一、Phase 4 复跑命令（触发评测）

> 前提：`books/tongjian-wei-bundle/bundle.json` 已建立且 `skills` 列表含本卡（`trigger build` 从 bundle.json 读 skills 列表生成骨架，**prompt 为空**，需按 `test-prompts.json` 的口径补全：should_trigger 的 prompt 填 should_trigger、诱饵的 prompt 填 should_not_trigger、跨卡诱饵标 `sibling_target`）。
> 必须用托管 Python（`/usr/bin/python3` 是 3.9，会假失败）。

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill
B=books/tongjian-wei-bundle
C=books/tongjian-wei-bundle/skills/mingfen-scan/SKILL.md

# 1. 从 bundle 生成评测套件骨架（case_id/prompt/expected/sibling_target）
$PY scripts/td.py trigger build $B --out $B/eval-suite.json

# 2. 切分 train/validation（validation 选版前保持隐藏，只跑一次）
$PY scripts/td.py trigger split $B/eval-suite.json

# 3. 生成盲测任务包（剥掉 expect/why）
$PY scripts/td.py trigger prepare $B/eval-suite.json --out $B/blind.jsonl

# 4. 生成答题纸：把 skills_in_scope 全部给被测 Agent 作答，选择填进 actual，存为 answers.json
$PY scripts/td.py trigger record $B/eval-suite.json --out $B/answers.json

# 5. 机械判分（容错 0）
$PY scripts/td.py trigger score $B/eval-suite.json $B/answers.json
```

判分口径（`score` 的输出项）：通过率 / precision / recall / F1 / **诱饵通过率** / **兄弟混淆率**。
本卡的合格线：诱饵（sn-01~sn-03）0 响应；兄弟混淆 0；should_trigger 3 条全中。
若诱饵被响应 → 改 description 的『不做/不适用』段；若兄弟混淆 → 本卡与 `chunchi-structure` 两卡的 B 段『易混淆辨析』都要重写（只改一张无效）。

## 二、建卡时已做的机械自验（非 Phase 4，实跑输出）

以下为建卡过程中**真实执行**的输出（托管 Python 3.13.12，仓库根目录）：

```text
$ python3 scripts/td.py anchor <card> --corpus corpus/anchored/src-01-tongjian-wei.md
   引语 41 条：锚定命中 41，未标注段号 0
   判定明细：{'ANCHOR_HIT': 41}
✅ 判定 PASS：41 条带段号标注的引语全部锚定在声明的段号内

$ python3 scripts/td.py verify-quotes <card> corpus/anchored/src-01-tongjian-wei.md
   引用 14 个（条目引用 0 + 时间戳 0 + 书类引用块 14）
   逐字引语核验 14 条 → 命中 14 条
✅ 全部引语在语料中核到

$ python3 scripts/td.py lint-quotes <card> --corpus corpus/anchored/src-01-tongjian-wei.md
   检查引语 38 条
✅ 未发现用字不一致（简繁/异体）

$ python3 scripts/td.py output-eval <card>
   规模：9120 字符 / 6637 tokens
   六段：齐全

$ python3 scripts/td.py validate books/tongjian-wei-bundle/skills/mingfen-scan
✅ 无问题
统计：技能卡 1 / 文档 0 · error 0 / warn 0
```

自验中发现并已修复的两处引语问题（留痕，不是结果数字）：
1. §76 引语内层原用『』而语料原文为「」，`verify-quotes` 严格匹配不过 → 拆为三条同行标注引语（「韓、燕皆稱王，趙武靈王獨不肯，曰：」／「無其實，敢處其名乎？」／「令國人謂己曰君。」）；
2. 自造术语原用「」被引语提取器当作待核引语（1 条 ANCHOR_MISS + 3 条 NOT_IN_CORPUS）→ 全部改为『』（与 `tongjian-decision-trace` 的房子惯例一致：『』为自造术语，「」只给逐字引语）。

## 三、题库设计说明

| id | 类型 | 考点 |
|---|---|---|
| st-01 | should_trigger | 组织架构 + 品牌授权复合变动 → 三层归位 |
| st-02 | should_trigger | 合作方升格 + 破例／立例判断 |
| st-03 | should_trigger | 名实分离（§76 原型场景） |
| sn-01 | should_not_trigger（跨卡诱饵） | 应归 `chunchi-structure`：屏障连锁传导，通篇无名分动作 |
| sn-02 | should_not_trigger（兄弟卡诱饵） | 应归 `cai-de-two-column`：给人打分，不给变动定位 |
| sn-03 | should_not_trigger（一般性） | 书摘需求，不触发任何能力 |

## 四、Phase 4 未覆盖事项（如实声明）

- 未运行任何 Agent 作答与判分；上文第二节的输出是**建卡自验**，不是触发评测结果。
- `trigger build` 依赖的 `books/tongjian-wei-bundle/bundle.json` 建卡时尚未建立（并行建卡中），故 `trigger build` 本身也**未实跑**；命令按 `scripts/td.py` 实际签名写出，可原样复跑。
- 引语可复算性：全部 41 条引语的段号与字形可按第一节之外的命令复算（见第二节），语料随仓库分发（`corpus/anchored/src-01-tongjian-wei.md`，文件头含取源 URL、抓取日期与许可）。


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
| 第 2 轮 | 严格 `scoring-rubric-strict.md` | **84** | 22/16/20/13/13 |

分差 **16** > 阈值 10 → `eval-kit check` 判定 `needs_human_review`，产物为
`eval/fidelity/mingfen-scan/FIDELITY.rejected.json`（**没过门禁，文件名即证据**）。

**人工复核裁定**：对外采用**严格轮 84 分（B）**作为本卡质量下限——严格轮每条扣分都引用了原文并实跑了
`verify-quotes`，标准轮虽写明多项限制却仍给满分（属"没找到扣分理由"，不是"经得起挑"）。

严格轮最重的一条扣分：consistency-x 漏了 Step 3 的『名与实是否被分开定价』与 Step 4 完成标准（链上位点＋一行处置＋日期＋可观测信号）

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
