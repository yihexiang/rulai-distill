# five-affairs 效用基线（no-skill vs with-skill）

本目录是 `five-affairs-seven-questions` 卡效用对照的**输入**与**可复跑起点**，对应
`docs/utility-evidence-2026-10-10.md` 的实验设计。

| 文件 | 是什么 |
|---|---|
| `questions.json` | 该题卡的 8 道种子题（来自 `td.py eval-kit init` 的 `build_questions`）。 |
| `answers.json` | **给了卡片**的答题回传（独立答题 Agent `answerer-with-fa-1` 产出，只给 SKILL.md）。 |
| `answers-baseline.json` | **没给卡片**的同题库答题回传（独立答题 Agent `answerer-baseline-fa-1` 产出，只给题库）。 |

## 复算

```bash
python3 scripts/td.py eval-kit utility \
  --card examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md \
  --with  docs/utility-baseline/five-affairs/answers.json \
  --without docs/utility-baseline/five-affairs/answers-baseline.json \
  --questions docs/utility-baseline/five-affairs/questions.json \
  --out  docs/utility-evidence-five-affairs.json
```

`--questions` 会让判据先剔除题面已出现的标签（防「照抄题面即算命中」），
剔除项写进产出 JSON 的 `leaked_terms` 字段。

## 说明

- `lunyu` 卡的基线答案文件**未随仓保存**（只留了 `docs/utility-evidence-lunyu.json`
  结论快照）；若要重跑 lunyu 效用对照，需重新生成其 `with` / `without` 两份答案。
- 本目录的答案是**单次会话**产出（n=1），不构成统计重复实验；重复实验（每卡 ≥3 次）
  与跨模型 without 侧仍属未做项。
