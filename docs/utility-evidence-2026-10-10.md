# rulai-distill · 效用证据（no-skill vs with-skill · 2026-10-10）

> 回答一个此前**始终没有证据**的问题：**「用了这张卡」比「不用这张卡」强在哪？**
> 本项目此前只能证明「卡片的引语没造假、结构齐全、两个评分者打 A」——那证明的是**卡片质量**，
> 不是**这张卡有用**。A 分可能只来自卡片写得好看。
>
> **机制**：`td.py eval-kit utility --card <卡> --with <有卡答案> --without <无卡答案> --questions <题库>`
> （实现见 `scripts/tdlib/evalkit.py` 的 `utility()`；回归 `t_evalkit_utility_baseline`）。

## 一、实验设计

| 项 | 设置 |
|---|---|
| 同题库 | 两卡均用各自 `eval-kit` 的 8 道种子题（with / without **同题**，不换题） |
| with 侧 | 独立答题 Agent，**只给 SKILL.md**（answerer-openbundle-1 / answerer-with-fa-1） |
| without 侧 | 独立答题 Agent，**明确不给卡片**，只给题库（answerer-baseline-1 / answerer-baseline-fa-1） |
| 判据 | **四道机械信号**（下表），不用评分者的主观效用分 |
| 产出 | `docs/utility-evidence-lunyu.json` · `docs/utility-evidence-five-affairs.json`（命令可复跑） |

### 为什么判据必须是机械信号

评分者打「有用/没用」与卡片 FIDELITY 的 A 分**不独立**——同一批人看同一张卡，
容易把「卡片质量」当成「这张卡有用」（#72/#73 的同一条教训：把一个角色干的事记成另一个角色的功劳）。
所以只判可机判的行为特征：

| 信号 | 含义 | 为什么要它 |
|---|---|---|
| `locator_citation` | 答案带段号/篇-章号定位引用 | 别人的机器能复核，读者能溯源 |
| `verbatim_quote` | 答案逐字复用 R 段引语 | 专有内容，不是通用表述 |
| `boundary_declared` | 对素材外问题明确声明「素材没讲/未覆盖」 | 边缘诚实度 |
| `card_term` | 复用卡片 frontmatter 的能力标签 | 术语层面的对齐 |

## 二、结果（两卡实跑）

| 卡 | with 命中 | without 命中 | 正向差 | 增益等级 |
|---|---:|---:|---:|---|
| `lunyu-conduct`（开放·論語） | 3 / 4 | 1 / 4 | **+2** | **显著增益** |
| `five-affairs-seven-questions`（书·孙子） | 4 / 4 | 3 / 4 | +1 | 中等增益 |

逐信号（1 = 命中）：

| 卡 | 信号 | with | without | 区分度 |
|---|---|:--:|:--:|---|
| lunyu | locator_citation | 1 | 0 | **有** |
| lunyu | verbatim_quote | 1 | 0 | **有** |
| lunyu | boundary_declared | 1 | 1 | 无 |
| lunyu | card_term | 0 | 0 | 无（剔除泄漏词后双双归零） |
| five-affairs | locator_citation | 1 | 0 | **有** |
| five-affairs | verbatim_quote | 1 | 1 | 无（孙武名句，通用模型也说得出来） |
| five-affairs | boundary_declared | 1 | 1 | 无 |
| five-affairs | card_term | 1 | 1 | 无 |

## 三、三条必须一起读的发现

1. **区分度几乎全部集中在「定位引用」这一道信号。** 两张卡的 without 侧都带了
   `boundary_declared`（如实声明素材没讲）——**这是模型的默认行为，不是卡片的功劳**。
   `card_term` 在 lunyu 上剔除泄漏词后双双归零（with=0/without=0）。
   **诚实的读法**：目前只能说「有卡时答案更可能带可复核的定位引用」，
   不能说「有卡时判断更正确、更有说服力」——那两件事本实验没测，也测不了。

2. **题面泄漏会虚增对照组的命中，必须剔除。** 题库 description 里往往已写了卡片的能力标签，
   答题者照抄题面就算「命中术语」。lunyu 实测：剔除前 with=4/without=2（中等增益），
   剔除 7 个泄漏词（君子/小人/言行/识人/自我修养/处境判断/論語）后 with=3/without=1（显著增益）。
   剔除的词记进报告的 `leaked_terms` 字段——**剔除本身也留痕**，否则等于悄悄放宽判据。

3. **「名句类引语」的区分度低。** five-affairs 的 R 段是《孙子》名句（「知之者勝，不知者勝」），
   without 侧也能逐字说出——**引语复用信号只对「不常被背诵的专有引语」有效**。

## 四、增益等级判据（可复算）

- `significant`：正向差 ≥2 且 with 命中 ≥3 且 without ≤1
- `moderate`：正向差 ≥1
- `none`：正向差 ≤0 —— **合法结论，不许虚报**（`t_evalkit_utility_baseline` 的负向探针钉住）

## 五、边界（引用本报告时必须一起引用）

- 只覆盖**机械可判的行为特征**，**不覆盖**结论正确性、说服力、专业判断。
- with / without 由**同一模型家族的不同会话**产出，**不是跨模型因果证据**。
- 每卡各 1 次 with / 1 次 without，**单次会话对照**；不构成统计意义上的重复实验。
- `none` 与 `moderate` 都是合法结论；本项目不做「有增益才好用」的对外宣称。

## 六、下一步（未做，如实列出）

- 重复实验：每卡 ≥3 次独立会话对照，报中位数与方差（当前 n=1）。
- 跨模型对照：至少一个不同模型家族跑 without 侧（当前同家族）。
- 信号改进：`boundary_declared` 区分度为零，需换成更严的判据（如「声明 + 给出替代路径」才算命中）。

## 七、产出 JSON 字段说明（供复算与审计）

`utility()` 对每个对照产出一份 JSON（`docs/utility-evidence-*.json`），字段含义：

- `subject`：被评测卡片标识。
- `card`：卡片 SKILL.md 路径。
- `signals`：参与判定的信号名列表（当前 4 道：`locator_citation` / `verbatim_quote` / `boundary_declared` / `card_term`）。
- `with` / `without`：有卡 / 无卡答案在各信号上的命中（布尔）。
- `delta`：每个信号 `with − without`（0 表示无区分度）。
- `counts`：`with` / `without` 命中的信号数，以及 `delta` 为正向的信号总数。
- `leaked_terms`：题库题面已出现、已从 `card_term` 判据中剔除的标签（留痕，防「照抄题面即算命中」）。
- `gain`：`significant` / `moderate` / `none`（none 合法，负向探针钉住不许虚报）。
- `boundary`：必须随结论一起引用的四条边界声明（机械信号不覆盖结论正确性、非跨模型因果、n=1、none 合法）。
- `errors`：判定前的校验错误（空集 / 无答题者等）；非空则 `gain = invalid`。

> 历史上曾用 `verdict` / `with_hits` 等字段名，现已统一为 `gain` 与 `with`+`without`；读取旧快照若遇到未知字段，以本 schema 为准。
