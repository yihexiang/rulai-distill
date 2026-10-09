# sample-bundle · 一份完整的真实蒸馏产物

> 这不是模板演示，是**真的跑了一遍七阶段**的结果。所有原始回答逐字保存，可复核。
> 素材：《孙子兵法·計篇》（公有领域，维基文庫「十一家註孫子卷上」，2026-10-04 取回，注文已剥离）

## 产物清单

| 文件 | 内容 | 真实性 |
|---|---|---|
| `sources/sunzi-ji.txt` | 孫子正文（計篇第1段，500 余字） | 真实一手材料 |
| `SOURCES.md` | 素材清单 + 一手占比 1.00 + 覆盖度自检 | 真实 |
| `skills/five-affairs-seven-questions/SKILL.md` | 能力卡（五事七问 · 开局校准） | 真实蒸馏产物 |
| `skills/five-affairs-seven-questions/FIDELITY.json` | **交叉复核**报告（2 个独立评分者 90/98，分差 8 → 合并 **93/A**）→ `gate` 直接吃它 | 真实（eval-kit 产出） |
| `eval/answers.md` | 双 Agent 盲测答题**逐字原始输出** | 真实 |
| `eval/fidelity-report.md` | 第一轮**单评分** FIDELITY 报告的人类可读叙事（93/100 A）——**已被 FIDELITY.json 的交叉复核取代为门禁依据** | 真实 |
| `eval/style-decoys.md` | 风格辨识度的两个通用腔调对照 | 主 Agent 撰写（已披露作者） |
| `eval/trigger-answers.json` | 触发评测答题原始作答 + 判分事故记录 | 真实 |
| `eval/TRIGGER-REPORT.md` | 触发评测报告 6/7 | 真实 |
| `eval/NO-SKILL-COMPARISON.md` | E4 no-skill 对照实验 | 真实 |
| `test-suite.json` | 7 条触发用例（含 2 诱饵 + 1 组双向 cross-skill） | 真实 |
| `trigger-eval.json` | 触发判分结果（precision/recall/F1） | 真实 |

## 三份评测的真实结论

| 评测 | 结果 | 一句话 |
|---|---|---|
| **FIDELITY（双 Agent · 交叉复核）** | **93/100 A** | 2 个独立评分者 90/98（分差 8，≤10）→ 合并 93/A；边缘诚实度满分（19/20×2） |
| **触发压力测试** | 6/7，precision 1.0，F1 0.889 | 诱饵 100% 挡住；1 条 cross-skill 失败（如实保留） |
| **E4 no-skill 对照** | **边际增益** | 对照组自发做了三问式尽调，**基座模型本来就很强** |

## 三个真实缺陷（都是评测发现的，不是自查发现的）

**1. A1 段把虚构情境挂在真实出处上**（FIDELITY 判 0/2）

原卡写「案例：孙武自己（出处：同段）」，情境是「与强邻交战…一旦押错就是万劫不复」。
评分 Agent 核查发现：計篇第1段中「孫武」「吴王」「越」「試兵」「試劍」「威王」出现次数**全为 0**
——这段是论述文本，根本没有叙事案例。**已改**：A1 改为「原文自身的主张」，
并在段首写明「本素材不含叙事案例，故不复述任何战役情境」。

**2. 判分器把字符串 `"none"` 当成有效 slug**（真实盲测才暴露）

第一次判分诱饵通过率显示 0%、FP=2，与肉眼可见的作答明显矛盾。根因是
`answers.get(cid) or None` 只处理空值不处理字符串。已修 `evals.py::_norm_answer`，
并补了第 29 项回归测试。**合成测试里 answers 用 Python `None` 构造，永远走不到这条分支。**

**3. 卡片在僵局场景太重**（E4 对照发现）

对照组（无卡）直接给出「上小流量灰度 + 明天动」的姿态，而实验组（读卡）要求先走完五步校准，
在「讨论两周没人拍板」这个现场**更慢**。已改：E 段新增「3 分钟版」（三问 + 二元结论），
并写明完整五步适用于「首次做这类决策」。

## 可复现命令

```bash
# 校验
python3 scripts/td.py validate examples/sample-bundle
python3 scripts/td.py output-eval examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md

# FIDELITY 门槛（读**交叉复核**报告；2 个独立评分者，分差 8）
python3 scripts/td.py gate examples/sample-bundle/skills/five-affairs-seven-questions/FIDELITY.json --min B

# 触发评测（重跑判分）
python3 scripts/td.py trigger score examples/sample-bundle/test-suite.json \
        examples/sample-bundle/eval/trigger-answers.json

# 发布
python3 scripts/td.py compile examples/sample-bundle --out /tmp/td-sample
```

## 仍未做到的事（不粉饰）

| 项 | 状态 |
|---|---|
| 第二评分者交叉校验 | **已做**（eval-kit 跑通：独立答题子 Agent + 2 个独立评分子 Agent，90/98、分差 8 → 93/A）。⚠️ 这是**结构独立**（子 Agent 隔离）而非组织独立（无第二个人复评） |
| 跨技能混淆题 x-01 | **失败未修**。可能是对照技能 description 不可区分，也可能是题面分界不干净 |
| FIDELITY 复评 | **已复评**。卡片按第一轮评分建议改过（A1 去虚构 / 阈值抗漂移 / B 段补篇目），随后由 eval-kit 交叉复核重评为 93/A（见 `skills/five-affairs-seven-questions/FIDELITY.json`）。两轮同为 93 分**但依据不同**：第一轮扣在已修的 A1 段，重评轮扣在一致性与来源透明度 |
