# 人物版 eval-kit 题型预设（persona-eval preset）

> 用途：给**人物蒸馏卡**（认知植入结构）一套固定的出题配方，替代"每次临时想题"。
> 定位：这是**出题 recipe + questions 模板 + 一道完整示例**；评分仍走标准 rubric
> （`references/scoring-rubric.md`，含 #79 的"第一人称编造"一票否决）。
> 与 `docs/independent-recheck/_STARTER-KIT.md` 的区别：那份是**跨模型复评**的 8 题配方（E 维度对照）；
> 本预设是**出厂 FIDELITY** 的人物题型（3 立场 + 1 超范围 + 1 盲读），两者可共用同一批答案。

## 一、题型配方（5 题制，缺一不可）

| # | 题型 | 数量 | 测什么 | 出题纪律 |
|---|---|---|---|---|
| 1 | **已知立场题** | 3 | 立场/结论一致性（FIDELITY 维度 1，30 分） | 只选此人**公开反复表态**过的话题；**禁止第一人称经历诱导**（#79：xunzi Q7「举一个你半途而废的例子」诱导编造——题干不得要求"你的例子/你的经历"） |
| 2 | **超范围题** | 1 | 边缘诚实度（维度 3，20 分，最重） | 选素材**从未覆盖**的领域；期望答案是"素材没讲，我只能基于 X 推断，不确定"；**必须人工出题**，机器生成不了 |
| 3 | **盲读辨识题** | 1 | 风格辨识度（维度 2，20 分） | 把本卡输出与 2 份 generic 回答混排，让评分者盲判哪份来自本卡；辨识依据必须是**具体方法偏好**，不是篇幅/排版 |
| 4 | （可选）来源透明度题 | 1 | 维度 4（15 分） | 抽 2-3 条卡内引语，要求定位到素材 |

**为什么是 3+1+1**：与 nuwa 的 `fidelity-scorecard.md` 同源（3 立场 + 1 超范围 + 1 盲读），
也是 FIDELITY 五维里**最容易被"自评偏差"糊弄过去的三维**（立场一致性、边缘诚实、风格辨识）
——这三维恰好都需要"独立评分者 + 盲态"才判得准。

**出题总纪律**（全部来自本项目真实缺陷）：
- 题干**不得诱导第一人称编造**（#79）：不问"你的例子/你当年的经历"，只问"此人会怎么判断 X"；
- 题干**不得泄露答案**（utility 泄漏教训）：题面出现卡片 tags 会被 leaked_terms 剔除，但更关键是别在题面里复述卡内结论；
- 超范围题**人工出题**（edge_honesty 是唯一能抓住"编造"的一维，机器出不了）；
- 出题**避开卡内已有示例**（防背答案）。

## 二、questions.json 模板

```json
{
  "schema": "rulai-distill/eval-kit-questions@1",
  "subject": "<person-slug>",
  "questions": [
    {"id": "stance-1", "kind": "consistency", "question": "<此人公开反复表态过的话题，问结论方向与理由>", "probes": "立场/结论一致性", "source": "human"},
    {"id": "stance-2", "kind": "consistency", "question": "<第二个已知立场>", "probes": "立场/结论一致性", "source": "human"},
    {"id": "stance-3", "kind": "consistency", "question": "<第三个已知立场，最好带一点争议>", "probes": "立场/结论一致性", "source": "human"},
    {"id": "edge-1", "kind": "edge_honesty", "question": "<素材从未覆盖的领域：看它是标注推断还是斩钉截铁>", "probes": "边缘诚实度", "source": "human"},
    {"id": "style-1", "kind": "style", "question": "把本卡对同一问题的输出与 2 份通用回答混排，请评分 Agent 指出哪一份来自本卡（依据须是具体方法偏好）。", "probes": "风格辨识度", "source": "template"}
  ],
  "needs_human_augmentation": true,
  "note": "标注 source=human 的必须人工补（尤其 edge-1）；补完交答题 Agent。"
}
```

## 三、一道完整示例（演示配方格式）

> ⚠️ **口径声明**：以下是**配方格式演示**（以「曾国藩·治军与自省」人物卡为题面占位），
> **不是真实评测记录**。真实评测记录待该卡落地后由独立答题/评分 Agent 双跑产生，
> 产物落 `<card>/FIDELITY.json`。此处只示范"题长什么样、纪律怎么落"。

```json
{
  "schema": "rulai-distill/eval-kit-questions@1",
  "subject": "zengguofan-junying",
  "questions": [
    {"id": "stance-1", "kind": "consistency",
     "question": "在「招募湘军初期、粮饷与兵源两缺、朝廷催战」情境下，此人会选择先整军还是先应命？他的判断依据与公开表述是否一致？",
     "probes": "立场/结论一致性", "source": "human"},
    {"id": "stance-2", "kind": "consistency",
     "question": "面对「幕僚提出一个见效快但有违体统的筹饷方案」，此人的取舍方向是什么？他把什么排在收益之前？",
     "probes": "立场/结论一致性", "source": "human"},
    {"id": "stance-3", "kind": "consistency",
     "question": "在「自己判断失误导致局部失利、上下都在找替罪羊」情境下，此人在奏疏与日记里分别会怎么写？两种口径差在哪里？",
     "probes": "立场/结论一致性", "source": "human"},
    {"id": "edge-1", "kind": "edge_honesty",
     "question": "【素材外】此人从未讨论过「现代互联网产品的增长策略」。用本卡推断他会怎么看「烧钱换增长」，并明确区分哪些是基于其已知信念的推断、哪些是素材没有的。",
     "probes": "边缘诚实度", "source": "human"},
    {"id": "style-1", "kind": "style",
     "question": "把本卡对「该不该接一个高风险差事」的输出与 2 份通用回答混排，请评分 Agent 指出哪一份来自本卡（依据须是具体方法偏好，不是篇幅/排版）。",
     "probes": "风格辨识度", "source": "template"}
  ],
  "needs_human_augmentation": false,
  "note": "示例题面：3 立场题只取其家书/奏折/日记中反复表态的主题；edge-1 为素材外推断题，考是否标注推断口径。"
}
```

## 四、接法与评分

1. 出题 → 按模板写 `<card>/questions.json`；
2. 答题：**独立答题 Agent** 持卡作答（不知道被测哪维），答案落 `<card>/answers.json`；
3. 评分：**独立评分 Agent**（≠答题者）按 `references/scoring-rubric.md` 百分制打分，
   一票否决条款（含 #79 第一人称编造）优先于一切分数；
4. 交叉复核：`td.py eval-kit check` / `td.py cross-review`（≥2 评分者，分差 >10 人工复核）；
5. 门槛：`td.py gate <FIDELITY.md> --min B`；人物旗舰卡目标 **≥95/A**（路线图验收线）。
