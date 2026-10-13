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
