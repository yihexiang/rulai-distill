# test-results · zengguofan-xiushen

> 状态总览：**机械自验已实跑并通过**（validate / anchor / verify-quotes / lint-quotes，真实输出见下）；
> **Phase 4 独立评测未运行**——本卡尚未经独立答题 Agent 与独立评分 Agent 双跑，不宣称任何 FIDELITY 分数。

## 一、机械自验（已实跑，2026-10-13，托管 Python 3.13.12）

### 1. `td.py validate` — ✅ error 0 / warn 0

```
$ PY scripts/td.py validate examples/persona-bundle/skills/zengguofan-xiushen
🔍 校验：examples/persona-bundle/skills/zengguofan-xiushen
✅ 无问题
统计：技能卡 1 / 文档 0 · error 0 / warn 0
```

人物卡专项检查全部通过：认知植入首句在位；「我看问题的方式」无显式步骤（Step/第N步/编号列表均无）；信念及其来源／内在矛盾／我明确不懂的／我绝不会做的事四段齐全；一手来源合计权重已声明（1.0）。

### 2. `td.py anchor`（双语料，段号级锚定）— ✅ 判定 PASS

```
$ PY scripts/td.py anchor examples/persona-bundle/skills/zengguofan-xiushen/SKILL.md \
    --corpus corpus/anchored/src-08-zengguofan-jiashu.md \
               corpus/anchored/src-09-zengguofan-yuze-wuzhen.md
   引语 88 条：锚定命中 88，未标注段号 0
   判定明细：{'ANCHOR_HIT': 88}
   对账：{'seen': 88, 'anchor_hit': 88, 'unanchored': 0, 'anchor_partial': 0,
          'span_hit': 0, 'anchor_miss': 0, 'not_in_corpus': 0, 'too_short': 0}
   抽取：候选 91 = 认出 88 + 噪声 0 + 中文太短跳过 3（自检 True）
   其中短引语（<8 汉字、逐字见于语料、同行带 §N）已纳入核验并命中 1 条
✅ 判定 PASS：88 条带段号标注的引语全部锚定在声明的段号内
```

口径说明：88 条带 `src-XX §N` 标注的引语全部 ANCHOR_HIT（逐字见于所声明段落，5-gram 命中率 ≥60%）；无 SPAN_HIT／ANCHOR_MISS／NOT_IN_CORPUS；无 UNANCHORED。3 条因汉字数 <8 未纳入裁决的候选（"认知植入／角色扮演／素材来源"）均为卡片自用术语而非引语，其中 0 条逐字见于语料。1 条短引语（<8 汉字但逐字见于语料且同行带 §N）经非对称升级规则纳入核验并命中。

**建卡返工记录（anchor 真实抓到过 FAIL，非一次过）**：初稿有 1 条引语段号挂错——「子序的为人，我至今不能确定他的品味，但是见识却是博大精深」初版声明 §4，anchor 报 SPAN_HIT 并指出实际在 §3（子序其人出第3段述求学之方法，第4段是另一封信），已改；另 frontmatter `verification.note` 内 1 处「」无段号标注被记 UNANCHORED，已去除。二处修毕后复跑 PASS。

### 3. `td.py verify-quotes`（存在级核验）— ✅ 10/10 命中

```
$ cat corpus/anchored/src-08-zengguofan-jiashu.md > /tmp/zgf-merged-corpus.md
$ cat corpus/anchored/src-09-zengguofan-yuze-wuzhen.md >> /tmp/zgf-merged-corpus.md
$ PY scripts/td.py verify-quotes examples/persona-bundle/skills/zengguofan-xiushen/SKILL.md /tmp/zgf-merged-corpus.md
   引用 10 个（条目引用 0 + 时间戳 0 + 书类引用块 10）
   逐字引语核验 10 条 → 命中 10 条
✅ 全部引语在语料中核到
```

口径说明（三条限制，如实写）：① 该工具只接受**单份**语料，故将两份 anchored 语料拼接为临时合并语料（仅拼接、未改一字）后运行；② 它只认【第N条】/时间戳/带《》出处的书类引用块三种锚点，**不识别本卡的 `src-XX §N` 内联标注**——首跑即按"空集假绿"拦截退出（EXIT=1），修法是把表达 DNA 六维的 10 条样本句按仓库书类卡规范排为 `> 引语`＋`> —— 《书名》第N段` 引用块，使其进入核验；③ 因此它的覆盖面是 10 条样本句的**存在级**核验，**段号级**核验以 anchor 的 88/88 为准（后者更严：验"在被引用的那一段里"）。

### 4. `td.py lint-quotes`（加分项）— ✅ 干净

```
$ PY scripts/td.py lint-quotes examples/persona-bundle/skills/zengguofan-xiushen/SKILL.md \
    --corpus corpus/anchored/src-08-zengguofan-jiashu.md corpus/anchored/src-09-zengguofan-yuze-wuzhen.md
   检查引语 87 条
✅ 未发现用字不一致（简繁/异体）
```

### 5. `td.py output-eval` — 口径不适用（如实记录，不算通过也不算失败）

```
$ PY scripts/td.py output-eval examples/persona-bundle/skills/zengguofan-xiushen/SKILL.md
   规模：12168 字符 / 8849 tokens
   六段：缺 R, I, A1, A2, E, B
   引语 0 条
```

该输出面向**能力卡**六段结构（R/I/A1/A2/E/B）；人物卡按 `templates/PERSONA.md.template` 使用另一套结构，`validate` 对 `subject_type: person` 明确不走六段检查路径（其源码即明令人物卡不要求 E 段）。其"引语 0 条"同样因为它只认【第N条】格式——本卡引语核验以 anchor（88/88）与 verify-quotes（10/10）为准。

## 二、Phase 4 独立评测 — **待运行**（未运行，不虚构数字）

本卡尚未经过独立答题／评分双跑，**无 FIDELITY 分数、无等级、无交叉复核记录**。出题已完成（同目录 `questions.json`，5 题：3 已知立场＋1 超范围＋1 盲读，`needs_human_augmentation=false`，已人工出全）。复跑步骤：

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

# 1) 出题：用本目录已人工出好的 questions.json（勿用 eval-kit init 的种子题覆盖）
#    5 题配方见 references/persona-eval-preset.md（3 立场 + 1 超范围 + 1 盲读）

# 2) 答题：独立答题 Agent 持 SKILL.md 作答（不知被测哪维、不见作者记忆），
#    答案落 <card>/answers.json（schema: rulai-distill/eval-kit-answers@1）

# 3) 评分：独立评分 Agent（≠ 答题者）按 references/scoring-rubric.md 百分制打分，
#    一票否决条款（含 #79 第一人称编造）优先于一切分数；评分落 <card>/scores.json

# 4) 交叉复核与汇总（≥2 个不同评分者，分差 >10 人工复核）：
$PY scripts/td.py eval-kit check <card>/answers.json --scores <card>/scores.json \
    --subject zengguofan-xiushen --out <card>/FIDELITY.json

# 5) 门槛：人物旗舰卡目标 ≥95/A（路线图验收线）
$PY scripts/td.py gate <card>/FIDELITY.json --min B
```

未运行项清单（如实列明，均无数据）：独立答题（answers.json）、独立评分（scores.json）、交叉复核（cross-review）、FIDELITY.json、gate 判定、trigger 触发压力测试、eval-kit utility 的 no-skill 对照。

## 三、结论

机械层可复核性已达成本工具链在当时版本下的上限：validate error 0；anchor 段号级 88/88 PASS（含一次真实抓错并修错的返工记录）；verify-quotes 存在级 10/10；lint-quotes 干净。质量层（FIDELITY 五维）**未测**——Phase 4 跑完之前，本卡只应被称作"引语可机械复核的认知植入卡"，不应被称作"已验证高质量的卡"。
