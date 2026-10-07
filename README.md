# rulai-distill · 蒸馏工厂 v1.6.0

把书籍 / 长视频 / 播客 / 访谈 / 人物素材，蒸馏成**可执行、可验证、可追溯**的 Agent Skills。

> 📌 **2026-10-05 改名**：`rulai-skill` → **`rulai-distill`**（原仓库名已被同名佛学项目占用）。
> 本次共改名 88 处：技能名、13 份 schema 的 id、LICENSE 版权行、NOTICE、
> README / CONSTRAINTS / OPEN-SOURCE-ASSESSMENT 正文，以及三处目录。
> **旧运行产物（`musk-run/`、`musk-run2/`、`video-run/`）里的 `"schema": "rulai-skill/…"`
> 是当时的真实记录，故意保留不改**——它们烤出来时这个项目就叫那个名字。

---

## ⚠️ 项目状态：beta，请先读这一段

**流程可靠性已验证，但产出的卡片尚未达到可发布质量。** 这两件事必须分开说，
因为它们的证据强度完全不同。

| 维度 | 状态 | 证据 |
|---|---|---|
| **机械可靠性** | ✅ 可信 | 66 项回归全绿；`gate` 因评测模式拒绝放行（实测生效）；`overlap` 能抓到 100% 重叠；`anchor` 能抓到挂错段号的引语 |
| **产出正确性** | ❌ **尚不可信** | 最近一次独立评分 **60/100（C 级）**，其中含一处**编造引语**；且因答题者与卡片作者未隔离，该分数本身也有折扣 |

具体地说，这个项目目前**做不到**的事：

1. **不能保证卡片里的引语挂对了地方。** 2026-10-05 的实测里，
   独立评分 Agent 抓出一处编造引用（把《暗黑破坏神》的一个 boss 名当成方法论证据），
   而当时的三层机械核验（validate、引语存在性、回归）**全部放行**。
2. **不能保证卡片作者与评分者分离。** FIDELITY 的核心是「答题 Agent ≠ 卡片作者」，
   但子 Agent 落盘在本环境下不稳定，独立答题两次失败，实际降级为自评。
3. **样本量只有 3**（书籍 / 人物 / 视频各一次），任何"全链路已验证"的说法都偏早。

**它现在适合当什么用**：流程骨架与门禁参考 —— 校验、门禁、快照、回滚、
契约化产物这一层是扎实的，可以直接复用。
**不适合当什么用**："喂素材就得到高质量卡片"的自动机。

之所以把这段放在最前面，是因为这个项目自己的方法论要求这样：
`gate` 拒绝过一份 60 分的报告，而那份报告的作者（也就是我）想把它写得更漂亮。
诚实标注分数比分数好看重要。

---

**v1.6.0 完成三类素材全链路**：书籍（孙子）与人物（马斯克）已有完整产物；
音视频链路后半段（字幕→逐字稿→分块→检索→出卡→引语核验）已跑通，
并因此补上**时间戳型引语核验**（此前视频卡片完全无法自检）。
抓取步骤在本机被网络环境阻塞（YouTube 不可达），已给出分类诊断，见 `../video-run/P3-VIDEO-PIPELINE.md`。

**v1.5.0 完成能力归一**：新增 `CAPABILITIES.md`（16 类上游能力逐项归属 + 自研 13 项 + 声明不做 2 项），
并把 `eval-suite` / `dependency-graph` / `failure-case` 三份剩余契约接入生产链路——
15 个自身缺陷已写成可机校验的 `failure-case`（`td.py failure list`）。

**v1.4.0 完成契约归一**：上游 13 份 schema 从"参考"升级为**权威契约**——本包产物直接按它们产出，
不合规就拒绝落盘。`source-document` / `source-manifest` / `change-set` / `registry-entry-v2`
四份已实跑合规，并由 `tests/e2e.py` 的 5 条 C3 测试持续保证。

**v1.2.0 把 cangjie 的实现原样内置（vendored）**：核证发现其契约深度与跨版本溯源确实
是质量主因，重写是变浅的——缓存键含实现版本、SQLite FTS5 词法索引、run 级留痕、
并发写锁，这四点现已全部对齐。同时恢复了字幕获取（唯一联网命令，默认 dry-run）。

---

## 一、它解决什么问题

大多数蒸馏技能解决了「生成」，没解决「证明」。产物看起来像样，但没人知道它是否忠于原文、
是否会编造、是否会和邻近技能抢调用。

rulai-distill 把**出厂质检**写进流水线：不打分不发版，不由自己打分。

---

## 二、与三个来源技能的能力对齐

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
| 静态校验 | cangjie `validate_skill_pack` + yeadon + nuwa 三方 | `td.py validate`（结构 + 死链 + 步骤禁令 + 来源占比 + 交叉引用） |
| 字幕获取 | nuwa `download_subtitles.sh` | `td.py fetch-subtitle`（唯一联网命令，**默认 dry-run**；修了上游 marker 从未写入的缺陷） |
| 字幕 → 带时间戳逐字稿 | nuwa `srt_to_transcript` | `td.py transcript`（SRT/VTT、去重成段、多集合并，**离线**） |
| 六路人物调研 | nuwa 六路 research 结构 | `td.py research init`（骨架 + 检索提示 + 覆盖度自检） |
| 多路调研合并去重 | nuwa `merge_research` | `td.py research merge`（去重 + **冲突标记** + 一手占比统计） |
| FIDELITY 出厂质检 | nuwa `fidelity-scorecard` | `templates/FIDELITY.md.template` + `td.py gate`（**非双 Agent 默认不放行**） |
| 认知植入结构 / 步骤禁令 | yeadon | `extractors/persona-extractor.md` + `validate` 机械检测 |
| 单文件 prompt 编译 | yeadon `compile-prompt` | `td.py prompt --mode entry\|inline\|cards` |

**关于上游代码**：`scripts/vendor/cangjie/` 是 kangarooking/cangjie-skill 的 **MIT 原件**
（17 个脚本 + LICENSE，取回时间与逐文件用途见 `scripts/vendor/PROVENANCE.md`），**未做任何修改**。
本包自研层（`scripts/tdlib/`）定位为「零依赖统一入口 + 上游没有的部分」：
FIDELITY 门槛、字幕管线、六路调研、冲突标记、prompt 编译。

用 `td.py upstream list` 看当前可用的上游能力与依赖状态，`td.py upstream run <tool> …` 直通执行。

**主动增强的部分**

| 增强 | 说明 |
|---|---|
| 零第三方依赖 | 内置最小 YAML 解析器 + 字符级 token 估算；PyYAML / tiktoken 缺失时自动降级 |
| FIDELITY 写进发布 | `compile` 读到低于门槛直接拒发；自测模式（fallback-self）默认**不算通过** |
| 冲突标记 | 调研合并遇到互相矛盾的一手材料不静默取先到 |
| 写操作默认 dry-run | `repair` / `patch` / `update` 不加 `--apply` 不落盘 |
| 一屏能力矩阵 | `td.py doctor` 直接打印与三个来源的对应关系 |

---

## 三、安装

> 📖 **第一次用请看 [`GUIDE.md`](./GUIDE.md)** —— 里面有完整流程、真实输出、命令速查与故障排查表。
> 本文只讲原理，GUIDE 讲怎么动手。

### 用作 WorkBuddy / Claude Code 技能

```bash
git clone https://github.com/yihexiang/rulai-distill.git \
  ~/.workbuddy/skills/rulai-distill      # Claude Code 换成 ~/.claude/skills/
```

装完即生效：说「把这本书蒸馏成技能」就会触发。**零依赖，Python ≥ 3.10 即可**，
不装 PyYAML / tiktoken / jsonschema 也能跑（自动降级）。

想要改动后还能一条命令同步：

```bash
rsync -a --delete rulai-distill/ ~/.workbuddy/skills/rulai-distill/
```

> ⚠️ **不要**把技能目录建在工作区里再`git init`——`musk-run/`、`musk-run2/`、`video-run/`
> 三个素材目录里是**受著作权约束的访谈逐字稿与字幕**，会被一起传上去。

### 只当命令行工具用

```bash
git clone https://github.com/yihexiang/rulai-distill.git && cd rulai-distill
python3 scripts/td.py doctor        # 自检：打印能力矩阵与缺失的可选依赖
python3 tests/e2e.py                # 跑 66 项回归
```

`scripts/td.py` 是纯本地、零网络、零依赖可跑的薄CLI，任何 Python ≥ 3.10 都能直接用。

---

## 四、快速开始

```bash
# 0. 自检（零依赖也能跑）
python3 scripts/td.py doctor

# 1. 建 bundle
python3 scripts/td.py init books/my-book
vim books/my-book/skills/*.md          # 按 templates/CAPABILITY.md.template 写

# 2. 长内容分块（>5 万字必做）
python3 scripts/td.py chunk book.md --max-chars 4000
python3 scripts/td.py index book.md.td --grep "关键词"

# 3. 视频/播客：取字幕（默认 dry-run）→ 逐字稿 → 分块
python3 scripts/td.py fetch-subtitle "<URL>" --out subs/ --execute
python3 scripts/td.py transcript subs/<id>.srt
python3 scripts/td.py chunk talk.transcript.md --source-id transcript

# 4. 人物：六路调研
python3 scripts/td.py research init books/my-person --person "某人"
python3 scripts/td.py research merge books/my-person/references/research/*.md \
        --out books/my-person/references/research-merged.md

# 5. 校验与质检
python3 scripts/td.py validate books/my-book
python3 scripts/td.py gate books/my-book/skills/x/FIDELITY.md --min B
python3 scripts/td.py strategy books/my-book

# 6. 发布与回滚
python3 scripts/td.py compile books/my-book --out ~/.workbuddy/skills/my-book
python3 scripts/td.py rollback ~/.workbuddy/skills/my-book --to latest

# 7. 触发测试（Agent 作答 → 脚本判分）
python3 scripts/td.py trigger build books/my-book --out suite.json
python3 scripts/td.py trigger record suite.json --out sheet.md
python3 scripts/td.py trigger score suite.json answers.json
```

**回归测试**：`python3 tests/e2e.py`（66 项，覆盖全部命令与 vendored 上游实跑）

---

## 五、七阶段管线

| 阶段 | 做什么 | 产物 |
|---|---|---|
| 0 | 全景理解（Adler 分析）+ 长内容分块 | `BOOK_OVERVIEW.md` + `*.td/` |
| 1 | 五路并行提取 | 候选单元池 |
| 1.5 | 三重验证（来源/可执行/效用） | 幸存单元 |
| 1.6 | 晋级门（五独立） | `promoted` / `router` |
| 2 | RIA++ 能力构造 / 人物认知植入 | 能力卡 / 人物卡 |
| 3 | Zettelkasten 链接（含易混淆辨析） | 关系图 |
| 4 | 触发压力测试 + FIDELITY 质检 | 测试套件 / `FIDELITY.md` |
| 5 | 形态决策 → 编译 → 原子发布 | `out/` + `BUILD_MANIFEST.json` |
| 6 | 登记、diff/impact/patch/持续演进 | `registry/<slug>.json` |

---

## 六、目录结构

```
rulai-distill/
├── SKILL.md                  ← Agent 加载的入口（渐进式披露）
├── methodology/              ← 00 全景 / 01 提取 / 02 三重验证 / 03 晋级门 / 04 压力测试 / 05 FIDELITY
├── extractors/               ← framework / principle / case / counter-example / glossary / persona
├── templates/                ← CAPABILITY / PERSONA / FIDELITY / TEST-SUITE / BOOK_OVERVIEW
├── schemas/                  ← 本包补充：bundle / fidelity / testsuite / transcript
├── scripts/vendor/cangjie/schemas/  ← **权威契约**（上游 13 份，MIT）
├── references/               ← scoring-rubric / trigger-playbook / failure-modes / media-pipeline
├── examples/walkthrough.md   ← 真实跑通记录
├── scripts/
│   ├── td.py                 ← 薄 CLI（25 个子命令）
│   ├── tdlib/                ← util / chunking / transcript / fetch / research / validate
│   │                            / fidelity / strategy / publish / evals / evolve / promptc / upstream
│   └── vendor/cangjie/       ← 上游 MIT 原件 + PROVENANCE.md（不改）
└── tests/e2e.py              ← 端到端回归（66 项，双解释器各跑一遍）
```

---

## 七、诚实声明

1. **语义提取由 Agent 完成，不由脚本完成**。`td.py` 只做确定性文件操作。
2. **FIDELITY 分数不是自证**。无独立 sub-agent 能力时标 `fallback-self`，
   `gate` **默认拒绝**（需显式 `--allow-fallback`），且按 80% 折算、维度 2 作废。
3. **唯一联网的命令是 `fetch-subtitle`，且默认 dry-run**。其余 24 个子命令纯本地。
   已有本地字幕时完全不需要联网。
4. **`--force` 发布是技术债**。manifest 会留 `forced: true`，事后可审计。
5. **触发评测不做 LLM 调用**（本包零网络）：Agent 作答、脚本判分，容错 0。
6. **未实测项**：长书场景的实际 token 节省量需真实跑一本 15 万字的书才能量化，
   目前只有分块机制与实测的分块行为数据。
