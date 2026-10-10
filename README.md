# rulai-distill · 蒸馏工厂 v1.6.0

把书籍 / 长视频 / 播客 / 访谈 / 人物素材，蒸馏成**可执行、可验证、可追溯**的 Agent Skills。

[English](./README.en.md) · [安装与使用指南](./GUIDE.md) · [能力清单](./CAPABILITIES.md)

[![pipeline-check](https://github.com/yihexiang/rulai-distill/actions/workflows/pipeline-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/pipeline-check.yml)
[![Artifact checks](https://github.com/yihexiang/rulai-distill/actions/workflows/artifact-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/artifact-check.yml)
[![Docs freshness](https://github.com/yihexiang/rulai-distill/actions/workflows/docs-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/docs-check.yml)
[![Contract & vendor](https://github.com/yihexiang/rulai-distill/actions/workflows/contract-check.yml/badge.svg)](https://github.com/yihexiang/rulai-distill/actions/workflows/contract-check.yml)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)
![regression](https://img.shields.io/badge/regression-103%20passing-brightgreen)

> ### 别的蒸馏技能解决「生成」，这个解决「证明」。
> **不打分不发版，而且不由自己打分。**

---

## ⚡ 30 秒上手

```bash
git clone https://github.com/yihexiang/rulai-distill.git && cd rulai-distill
./install.sh                # 装进所有检测到的 Agent 目录（--list 先看、--copy 只复制）
python3 scripts/td.py doctor   # 零依赖自检：能力矩阵 + 缺失的可选依赖
```

零第三方依赖，**Python ≥ 3.10** 即可（不装 PyYAML / tiktoken / jsonschema 也能跑，自动降级）。
`SKILL.md` 遵循 [Agent Skills 开放标准](https://agentskills.io/specification)，
同一个目录能被 Claude Code / Codex / Cursor / Gemini CLI / Copilot / OpenCode / Hermes / WorkBuddy 直接读取。

装完对 Agent 说一句「把这本书蒸馏成技能」就会触发。

---

## 为什么值得试：三件大多数技能不做的事

### 1️⃣ 门禁是**机器执行的**，不是文档里的口号

```
validate   →  结构 / 死链 / 完成标准 / 失败模式        （0 error 才继续）
verify-quotes  →  每条引语逐字回语料       （验「存在」）
anchor     →  引语是否真在它声明的 §N 段里  （验「归属」）
lint-quotes→  简繁混用 / 省略号 / 归属可疑  （验「为什么核不到」）
gate       →  默认要求 ≥2 个独立评分者交叉复核，否则**拒绝放行**
```

`compile` 读到低于门槛的 FIDELITY 直接拒发；自测模式（fallback-self）默认**不算通过**；
失败产物自带 `verdict=fail`，改个文件名也**照样过不了** `gate`。

### 2️⃣ 独立性是**结构化的**：答题 ≠ 评分 ≠ 作者

`td.py eval-kit` 把独立质检变成一组有格式的 JSON + 一条命令：

| 角色 | 谁来做 | 约束 |
|---|---|---|
| 出题 | 人工 + 种子题 | `edge_honesty`（唯一能抓「编造」的一维）机器生成不了，**必须人工出题** |
| 答题 | 独立 Agent | 只给卡片、不给作者记忆；标识不得与作者相同 |
| 评分 | **≥2 个**独立 Agent | 互相看不到对方结论；同名评分者不算两个人 |
| 汇总 | `eval-kit check` | 分差 >10 判人工复核；空集/单评分**一律不判通过** |

### 3️⃣ 缺陷有**台账**，而台账由测试强制相等

本项目把自己的 70 个缺陷全部登记在 `CONSTRAINTS.md`，并逐条写成可机校验的 failure-case
（`td.py failure list`）：每条都带「当时怎么错的 / 应该是什么 / 严重级 / 对应回归测试」。
**台账行数、分布数字、回归项数三者由测试强制相等——数字写错即 CI 红。**

其中 54 条是**验证/度量工具自身**的错（占 78%）——这个比例本身就是结论：
**错得最多的往往不是东西，是尺子。**

---

## 🧪 真实战绩（每一条都能自己复算）

| 产物 | 素材类型 | 分数 | 怎么来的 |
|---|---|---|---|
| `five-affairs-seven-questions` | 书籍（《孙子兵法·計篇》） | **93 / A** | 独立答题 Agent + 2 个独立评分 Agent（90 / 98，分差 8）；报告随包：`examples/sample-bundle/skills/five-affairs-seven-questions/FIDELITY.json` |
| `musk-decisions` | 人物（三份长访谈 44,630 词） | **90 / A** | 同上（92 / 89，分差 3）；**替代旧的 60/C 单评分结论** |
| `bazi-paipan` | 排盘（八字四柱） | **93 / A** | 同上（92 / 93，分差 1） |
| `geju-yunshi` | 格局与运势（描述性） | **95 / A** | 同上（96 / 93，分差 3） |
| `quming-xue` | 取名（依喜用神） | **96 / A** | 同上（96 / 95，分差 1） |
| `zhouyi-yili` | 周易义理（处境分析） | **96 / A** | 同上（97 / 97，分差 0）——⚠️ 两个评分者**总分完全相同**，不构成两次独立证实 |
| 9 张真实卡（八字 / 姓名学 / 周易 / 视频 / 人物 / 书 …） | 混合 | — | `validate` + `output-eval` + `lint-quotes` 实跑：**error 0、零崩溃、零假红** |

**这些数字的边界，写在明处**：独立性是**结构独立**（子 Agent 隔离）而非组织独立（没有第二个人复评）；
`musk-decisions` 只测了 3 道人工题；样本卡是精修展示件，**不能代表开放素材的普遍水平**；
guoxue 那四张同属国学、同一套语料规整方式，**四张通过不等于四类素材被验证过**。
逐条证据与最近核验日期见 [`docs/CLAIMS.md`](./docs/CLAIMS.md)（机器核验：`python3 docs/verify_claims.py`）。

### 开放素材臂（P0-2 · 2026-10-10 新增）

上面 9 张卡覆盖**封闭 / 半封闭素材**（节选书、人物访谈、TED 视频）。P0-2 补齐了
"**大规模公有领域文本**"这一类，证明工具链不只吃小样本，也能吃 25 万字节级的公版典籍：

| 角色 | 内容 | 状态 |
|---|---|---|
| 抓取—规整—切片 | 4 套公版典籍：資治通鑑（魏紀）/ 孟子 / 韓非子 / 論語，合计 **252,492 字节原始 / 90,288 净字符 / 226 抓取段** | `fetch_wikisource` → `corpus-anchor` 实跑，无崩溃 |
| 端到端建卡 | `lunyu-conduct`（論語 → 言行识人框架） | `validate` + `lint-quotes` 通过；`eval-kit init` 已出质检套件 |
| 独立交叉复核 | `lunyu-conduct` | **待补**（独立答题 Agent 落盘可靠性问题，见下） |
| 其余 3 套语料 | 通鉴 / 孟子 / 韓非子 | 抓取—规整—切片就绪，建卡为下一增量 |

逐条规模证据与已知边界见 [`docs/scale-evidence-open-material-2026-10-10.md`](./docs/scale-evidence-open-material-2026-10-10.md)
（与本仓库同工作区）。

**开放素材臂的边界（同样写在明处）**：

- **切片粒度依赖标题**：`corpus-anchor` 按 markdown 标题切，韓非子 / 論語正文用传统编号
  （章 / `一之一`）而非标题，切片退化为 3 块。这**不影响建卡**（建卡读锚定后的细粒度段号），
  但意味着 P0-3 的 token 节省基准（取自有标题语料）对"无标题长正文"偏低。
- **开放素材尚未独立交叉复核**：`lunyu-conduct` 已建卡但独立答题 + 双评分未跑——
  所以"工具链能吃大语料"**不等于**"大语料上的卡片质量已被独立证实"。这正是上面
  "6 张交叉复核 ≠ 6 类素材"的同一条边界在开放素材上的延伸。

---

## 🚦 项目状态：beta，请先读这一段

**流程可靠性已验证，但产出的卡片尚未达到可发布质量。** 这两件事必须分开说，因为证据强度完全不同。

| 维度 | 状态 | 证据 |
|---|---|---|
| **机械可靠性** | ✅ 可信 | 103 项回归全绿；`gate` 默认要求交叉复核记录（实测生效）；`verify-quotes`/`anchor`/`lint-quotes` 均在真实素材上抓到过真问题；工具链在 **9 张真实卡**上实跑零崩溃、零假红 |
| **产出正确性** | ⚠️ **已跑通闭环，仍强依赖素材** | `eval-kit` 已在 **6 张卡**上跑通**真实交叉复核**（独立答题 Agent + 2 个独立评分 Agent）：样本卡 `five-affairs` **93/A**、`musk-decisions` **90/A**，guoxue 四张 **93/95/96/96（A）**。⚠️ 这些是**结构独立**而非组织独立；样本卡是精修展示件，**不能代表开放素材的普遍水平** |

具体地说，这个项目目前**做不到**的事：

1. **不能保证卡片里的引语挂对了地方。** 2026-10-05 的实测里，独立评分 Agent 抓出一处编造引用
   （把《暗黑破坏神》的一个 boss 名当成方法论证据），而当时的三层机械核验（validate、引语存在性、回归）**全部放行**。
   现在多了 `anchor`（段号锚定）与 `lint-quotes`（用字体检），但**核验能力的边界始终要由实测来划**。
2. **独立性只在「结构」层面成立，不是「组织」层面。** 这条已被真实跑通（`eval-kit`：独立答题子 Agent +
   2 个独立评分子 Agent），但它仍是同一台机器上的子 Agent —— **没有第二个人复评**，
   且子 Agent 落盘在长任务下仍不稳定（历史实测派 4 次仅 1 次可靠落盘）。
3. **开放素材上的卡片尚未独立交叉复核。** `eval-kit` 只在 **6 张**封闭 / 半封闭卡上跑通交叉复核
   （其中 `musk-decisions` 仅测 3 道人工题）；开放公版素材（`lunyu-conduct` 論語）已端到端建卡并通过
   `validate` / `lint-quotes`，但独立答题 + 双评分**尚未跑**（子 Agent 落盘可靠性问题）。
   **9 张真实卡**（封闭 / 半封闭）+ 1 张开放素材卡跑工具链零崩溃，但那证明的是「工具能跑」，
   **不是「卡片都好」**。

**它现在适合当什么用**：流程骨架与门禁参考 —— 校验、门禁、快照、回滚、契约化产物这一层是扎实的，可以直接复用。
**不适合当什么用**：「喂素材就得到高质量卡片」的自动机。

之所以把这段放在最前面，是因为这个项目自己的方法论要求这样：
`gate` 拒绝过一份 60 分的报告，而那份报告的作者（也就是我）想把它写得更漂亮。**诚实标注分数比分数好看重要。**

---

## 🗺️ 七阶段管线

| 阶段 | 做什么 | 产物 |
|---|---|---|
| 0 | 全景理解（Adler 分析）+ 长内容分块 | `BOOK_OVERVIEW.md` + `*.td/` |
| 1 | 五路并行提取 | 候选单元池 |
| 1.5 | 三重验证（来源 / 可执行 / 效用） | 幸存单元 |
| 1.6 | 晋级门（五独立） | `promoted` / `router` |
| 2 | RIA++ 能力构造 / 人物认知植入 | 能力卡 / 人物卡 |
| 3 | Zettelkasten 链接（含易混淆辨析） | 关系图 |
| 4 | 触发压力测试 + FIDELITY 质检 | 测试套件 / `FIDELITY.md` |
| 5 | 形态决策 → 编译 → 原子发布 | `out/` + `BUILD_MANIFEST.json` |
| 6 | 登记、diff / impact / patch / 持续演进 | `registry/<slug>.json` |

---

## 📦 完整流程（复制即用）

```bash
# 0. 自检（零依赖也能跑）
python3 scripts/td.py doctor

# 1. 建 bundle，按 templates/CAPABILITY.md.template 写卡
python3 scripts/td.py init books/my-book
vim books/my-book/skills/*.md

# 2. 长内容分块（>5 万字必做）
python3 scripts/td.py chunk book.md --max-chars 4000
python3 scripts/td.py index book.md.td --grep "关键词"

# 3. 视频/播客：取字幕（默认 dry-run）→ 逐字稿 → 分块
python3 scripts/td.py fetch-subtitle "<URL>" --out subs/ --execute
python3 scripts/td.py transcript subs/<id>.srt
python3 scripts/td.py chunk talk.transcript.md --source-id transcript

# 4. 人物：六路调研（骨架 + 冲突标记 + 一手占比）
python3 scripts/td.py research init books/my-person --person "某人"
python3 scripts/td.py research merge books/my-person/references/research/*.md \
        --out books/my-person/references/research-merged.md

# 5. 校验与质检（三门禁）
python3 scripts/td.py validate books/my-book
python3 scripts/td.py lint-quotes books/my-book/skills/x/SKILL.md --corpus corpus/src-01.md
python3 scripts/td.py eval-kit init books/my-book/skills/x/SKILL.md --out kit/
#    → 独立答题 Agent 填 answers.json；2 个独立评分 Agent 各填 scores-*.json
python3 scripts/td.py eval-kit check --answers kit/answers.json \
        --scores kit/scores-1.json kit/scores-2.json --out FIDELITY.json
python3 scripts/td.py gate FIDELITY.json --min B

# 6. 发布与回滚（原子 + 快照 + 手改检测）
python3 scripts/td.py compile books/my-book --out ~/.workbuddy/skills/my-book --with-reports
python3 scripts/td.py rollback ~/.workbuddy/skills/my-book --to latest
```

**回归测试**：`python3 tests/e2e.py`（103 项，覆盖全部命令与 vendored 上游实跑）

> 📖 命令速查见 [`references/command-cheatsheet.md`](./references/command-cheatsheet.md)（37 个子命令）；
> 第一次用请看 [`GUIDE.md`](./GUIDE.md) —— 完整流程 + 真实输出 + 故障排查表。

---

## 🔗 与三个来源技能的能力对齐

`rulai-distill` 融合了三个开源项目的长处，并把它们的**契约**升格为权威标准。

| 能力 | 来源 | rulai-distill v1.6.0 |
|---|---|---|
| 结构感知分块 + 缓存 | cangjie `build_chunks` | **上游内置** `td.py upstream run chunk`；本包 `td.py chunk` 兜底 |
| SQLite FTS5 词法索引 + 邻接块 | cangjie `build_index` | **上游内置** `td.py upstream run lexindex` |
| 版本化缓存键 / run 级留痕 / 并发写锁 | cangjie `cangjie_common` | v1.2.0 已按上游设计对齐（本包 `chunking` / `publish`） |
| token 计量（发现/单任务/语料） | cangjie `count_tokens` | `td.py count` |
| 输出形态决策 single/pack | cangjie `select_output_strategy` | `td.py strategy` |
| 原子发布 / 快照 / 回滚 / 手改检测 | cangjie `compile_pack` / `compile_single` | `td.py compile --mode pack\|single` / `snapshot` / `rollback` |
| 增量维护 diff/impact/repair/update/patch | cangjie 五个演进脚本 | `td.py diff` `impact` `repair` `patch` `update`（默认 dry-run） |
| 触发评测 | cangjie `run_trigger_evals` | `td.py trigger build/record/score`（Agent 作答、脚本判分，零网络） |
| 输出评测 | cangjie `run_output_evals` | `td.py output-eval` |
| 基准 | cangjie `benchmark` | `td.py bench` |
| 静态校验 | cangjie + yeadon + nuwa 三方 | `td.py validate`（结构 + 死链 + 步骤禁令 + 来源占比 + 交叉引用） |
| 字幕获取 | nuwa `download_subtitles.sh` | `td.py fetch-subtitle`（唯一联网命令，**默认 dry-run**） |
| 字幕 → 带时间戳逐字稿 | nuwa `srt_to_transcript` | `td.py transcript`（SRT/VTT、去重成段、多集合并，**离线**） |
| 六路人物调研 | nuwa 六路 research 结构 | `td.py research init`（骨架 + 检索提示 + 覆盖度自检） |
| 多路调研合并去重 | nuwa `merge_research` | `td.py research merge`（去重 + **冲突标记** + 一手占比统计） |
| FIDELITY 出厂质检 | nuwa `fidelity-scorecard` | `templates/FIDELITY.md.template` + `td.py gate`（**非双 Agent 默认不放行**） |
| 认知植入结构 / 步骤禁令 | yeadon | `extractors/persona-extractor.md` + `validate` 机械检测 |
| 单文件 prompt 编译 | yeadon `compile-prompt` | `td.py prompt --mode entry\|inline\|cards` |

**关于上游代码**：`scripts/vendor/cangjie/` 是 kangarooking/cangjie-skill 的 **MIT 原件**
（17 个脚本 + LICENSE，取回时间与逐文件用途见 `scripts/vendor/PROVENANCE.md`），**未做任何修改**。
本包自研层（`scripts/tdlib/`）定位为「零依赖统一入口 + 上游没有的部分」：
FIDELITY 门槛、独立评测闭环（eval-kit）、引语三层核验、字幕管线、六路调研、冲突标记、prompt 编译。

**主动增强的部分**

| 增强 | 说明 |
|---|---|
| 零第三方依赖 | 内置最小 YAML 解析器 + 字符级 token 估算；PyYAML / tiktoken 缺失时自动降级 |
| FIDELITY 写进发布 | `compile` 读到低于门槛直接拒发；自测模式（fallback-self）默认**不算通过** |
| 独立质检闭环 | `eval-kit`：题库 / 答题 / 双评分 / 分差门禁全流程化，产出 `gate` 可直接消费的 JSON |
| 引语三层核验 | 存在性（verify-quotes）→ 段号归属（anchor）→ 用字体检（lint-quotes） |
| 冲突标记 | 调研合并遇到互相矛盾的一手材料不静默取先到 |
| 写操作默认 dry-run | `repair` / `patch` / `update` 不加 `--apply` 不落盘 |
| 一屏能力矩阵 | `td.py doctor` 直接打印与三个来源的对应关系 |

---

## 📁 目录结构

```
rulai-distill/
├── SKILL.md                  ← Agent 加载的入口（渐进式披露）
├── GUIDE.md                  ← 安装与完整流程（第一次用看这个）
├── CAPABILITIES.md           ← 16 类上游能力逐项归属 + 自研清单 + 声明不做
├── CONSTRAINTS.md            ← 70 条自身缺陷台账（每条对应回归测试）
├── methodology/              ← 00 全景 / 01 提取 / 02 三重验证 / 03 晋级门 / 04 压力测试 / 05 FIDELITY
├── extractors/               ← framework / principle / case / counter-example / glossary / persona
├── templates/                ← CAPABILITY / PERSONA / FIDELITY / TEST-SUITE / BOOK_OVERVIEW
├── schemas/                  ← 本包补充：bundle / fidelity / testsuite / transcript
├── scripts/vendor/cangjie/schemas/  ← **权威契约**（上游 13 份，MIT）
├── references/               ← scoring-rubric / command-cheatsheet / failure-modes / media-pipeline
├── examples/
│   ├── sample-bundle/        ← 一份**真的跑完七阶段**的产物（含交叉复核报告）
│   └── walkthrough.md        ← 真实跑通记录
├── scripts/
│   ├── td.py                 ← 薄 CLI（37 个子命令）
│   ├── tdlib/                ← util / chunking / transcript / fetch / research / validate
│   │                            / fidelity / evalkit / anchor / lintquotes / strategy / publish
│   │                            / evals / evolve / promptc / upstream
│   └── vendor/cangjie/       ← 上游 MIT 原件 + PROVENANCE.md（不改）
└── tests/e2e.py              ← 端到端回归（103 项，双解释器各跑一遍）
```

---

## 📜 诚实声明

1. **语义提取由 Agent 完成，不由脚本完成**。`td.py` 只做确定性文件操作。
2. **FIDELITY 分数不是自证**。无独立 sub-agent 能力时标 `fallback-self`，
   `gate` **默认拒绝**（需显式 `--allow-fallback`），且按 80% 折算、维度 2 作废。
3. **唯一联网的命令是 `fetch-subtitle`，且默认 dry-run**。其余 36 个子命令纯本地。
   已有本地字幕时完全不需要联网。
4. **`--force` 发布是技术债**。manifest 会留 `forced: true`，事后可审计。
5. **触发评测不做 LLM 调用**（本包零网络）：Agent 作答、脚本判分，容错 0。
6. **token 节省已量化，但**是**区间而不是倍数**。实测（tiktoken `cl100k_base`，
   3 本素材，见 [`benchmarks/token-savings/report-2026-10-10.md`](./benchmarks/token-savings/report-2026-10-10.md)）：
   分块检索相对整本灌入省 **1/1.0 ～ 1/34**。
   **下端 1.0× 不是噪声**：书短（5 块）或关键词宽（命中 4/5 块）时，
   「检索」退化成「通读」，一点也省不下。**「用分块处理长书」的前提是
   「书足够长 ∧ 你知道自己在找什么」，两条缺一不可。**
   另外「省 token」与「读对内容」是两件事——关键词定位错块，省下的会以读错的形式还回去。
   复跑：`python3 benchmarks/token-savings/measure.py --corpus <书> --sweep`
   （未装 `tiktoken` 时它明确报"未运行"并退出码 2，不用字数估算顶替）。
7. **不把「核验过」说成「没问题」**。工具只能证明它检查过的那一面：
   `verify-quotes` 验存在、`anchor` 验段号、`lint-quotes` 验用字，
   三者都过 ≠ 卡片正确，只等于**这三类错没被检出**。

---

## ⚖️ 许可

MIT。vendored 上游代码保留原许可与版权声明（见 `scripts/vendor/PROVENANCE.md` 与 `NOTICE`）。

> ⚠️ **不要把技能目录建在工作区里再 `git init`** —— 真实素材目录里是**受著作权约束的
> 访谈逐字稿与字幕**，会被一起传上去。
