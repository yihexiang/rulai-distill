# CAPABILITIES · 能力归属表

> 目的：**杜绝"未归属"状态**。每一项上游能力必须标明归属（vendored / 自研 / 声明不做），
> 并给出入口命令。`tests/e2e.py::t_upstream_coverage` 会核对本表与
> `tdlib/upstream.py::MAPPING` 的一致性——**表与代码漂移即红**。

## 一、继承自上游（kangarooking/cangjie-skill，MIT · vendored）

| # | 能力 | 上游实现 | 本包入口 | 契约产物 |
|---|---|---|---|---|
| 1 | 结构感知分块 | `build_chunks.py` | `td.py chunk` | `source-document`（normalized 版本化分层） |
| 2 | 词法索引（SQLite FTS5 + 中文 bigram + 邻接块） | `build_index.py` | `td.py lexindex` | — |
| 3 | token 计量 | `count_tokens.py` | `td.py count` | — |
| 4 | single/pack 形态决策 | `select_output_strategy.py` | `td.py strategy` | `output-decision` |
| 5 | pack 编译 | `compile_pack.py` | `td.py compile`（对应上游 tool 名 `compile`） | `registry-entry-v2` / `dependency-graph` |
| 6 | single 编译 | `compile_single.py` | `td.py compile --mode single`（tool 名 `compile-single`） | 同上 |
| 7 | 技能包校验 | `validate_skill_pack.py` | `td.py validate`（三方交叉互评） | — |
| 8 | 触发评测（切分/盲测/判分） | `run_trigger_evals.py` | `td.py trigger build/split/prepare/score`（tool 名 `trigger`） | `eval-suite` |
| 9 | 输出评测 | `run_output_evals.py` | `td.py output-eval` | — |
| 10 | 基准 | `benchmark.py` | `td.py bench` | — |
| 11 | 两版差异 | `diff_sources.py` | `td.py diff` | `change-set` |
| 12 | 影响面 | `impact_analysis.py` | `td.py impact` | — |
| 13 | 机械修复 | `repair_flow.py` | `td.py repair` | — |
| 14 | 结构化补丁 | `apply_skill_patch.py` | `td.py patch` | — |
| 15 | 重新校验 + 重编译 | `update_flow.py` | `td.py update` | — |
| 16 | 统一 CLI | `cangjie.py` | `td.py upstream run cli`（tool 名 `cli`） | — |

**算法层已全部继承；契约层（13 份 schema）已升级为权威契约**（v1.4.0）。

## 二、本包自研（上游没有的）

| 能力 | 入口 | 要解决的问题 |
|---|---|---|
| FIDELITY 出厂质检 + 发布门槛 | `gate` / `compile` | nuwa 的质检是人工评分卡，本包做成可执行门禁 |
| 交叉复核门禁（nuwa 第三铁律） | `cross-review` / `gate --scores` | 「2 个独立评分 agent、分差 >10 人工复核」原本只存在于散文；现由 `cross_review()` 强制，且 `gate` 见到 `needs_human_review` 一律拒绝放行（缺陷 #43） |
| 自测降级规则 | `gate --allow-fallback` | 自评自证必须被显式降级并留痕 |
| 引语机械核验 | `verify-quotes` | 人工抽查密度不可能达到 18/18 |
| 调研车道覆盖审计 | `research merge` | 防止「一手 100%」掩盖 2/6 路缺失 |
| 字幕获取（唯一联网） | `fetch-subtitle` | 默认 dry-run，marker 落在 --out 内 |
| 逐字稿生成 | `transcript` | SRT/VTT + 去重 + 成段 + 多集合并 |
| 人物认知植入卡 | `templates/PERSONA.md.template` + `validate` | 显式步骤禁令、六路调研骨架 |
| prompt 单文件编译 | `prompt` | 目标环境不支持 skill 目录加载时 |
| 写操作默认 dry-run | `repair` / `patch` / `update` | 蒸馏产物的价值在人工精修 |
| 并发写锁 | `compile`（WriterLock） | 两个进程同时发布会产生半个 target |
| run 级留痕 | `chunk` 的 `runs/` | 回答"这次分块是怎么来的" |
| 约束即测试 | `CONSTRAINTS.md` + **89** 项回归 | 不需要用户反复纠正（项数由 `t_docs_no_drift` 强制与代码一致） |
| 失败用例集 | `failure list/export` | 缺陷沉淀为可机校验的 failure-case |

## 三、明确声明不做

| 事项 | 原因 |
|---|---|
| 字幕**自动下载**的默认开启 | 唯一联网动作，必须显式 `--execute`；其余 30+ 命令全离线 |
| 修改 vendored 上游代码 | 改逻辑去上游提 PR；本包只在 `tdlib/` 做适配（见 PROVENANCE.md） |

## 四、覆盖度自检

`tests/e2e.py` 中的三条测试保证本表不腐烂：

- `t_upstream_coverage`：上游 16 类能力的 vendored 脚本必须全部存在
- `t_contract_list`：11 份契约映射必须全部存在
- `t_contract_ledger_no_silent_gap`：约束表不允许出现无状态条目
- `t_docs_no_drift`：**本表声明的回归项数必须等于 `tests/e2e.py` 里 `def t_*` 的实际个数**

## 五、CI（4 个 workflow，对齐仓颉数量）

按**职能**对齐而非按文件名照抄——仓颉的 `deploy-pages` / `update-star-history`
依赖它自己的 `website/`（Astro 站点），本包没有该目录，照抄等于造假。

| workflow | 管的风险 |
|---|---|
| `pipeline-check` | 代码回归（零依赖 + 完整依赖两轮）+ 红线扫描 |
| `contract-check` | 契约合规 + **vendored 上游 sha256 完整性** |
| `artifact-check` | 随包样本可核验（含 `verify-quotes` **防空集假绿**） |
| `docs-check` | 文档声明的数字与代码不漂移 + Markdown 死链/重复章节 |

> `verify-quotes` 对**空集**也会输出「✅ 全部引语核到」（0 引用 → 0 核验 → pass），
> 因此 `artifact-check` 不看退出码，而是断言 `quotes_checked >= 1 and verified == quotes_checked`。
