# PROVENANCE · 内置上游代码的来源与授权

本目录包含**原样取回**的第三方开源实现。rulai-skill 不修改这些文件，
只在自己的 `scripts/tdlib/` 里做适配与增强。

---

## kangarooking/cangjie-skill

- 来源：https://github.com/kangarooking/cangjie-skill
- 授权：MIT（完整文本见同目录 `LICENSE`）
- 取回时间：2026-10-04
- 取回方式：`raw.githubusercontent.com` 拉取 `scripts/*.py`（17 个）+ `schemas/**`（13 个）+ `LICENSE`
- 版本对应：v2.5.0 时期的 scripts 目录

| 文件 | 在 rulai-skill 中的定位 |
|---|---|
| `cangjie_common.py` | 上游公共原语：版本化缓存键、run_id/workdir、WriterLock、atomic_publish、snapshot |
| `cangjie.py` | 上游统一 CLI |
| `build_chunks.py` | 结构感知分块（参考实现，本包 `td.py chunk` 的深度来源） |
| `build_index.py` | SQLite FTS5 词法索引 + 中文 bigram + 邻接块扩展 |
| `count_tokens.py` | token 计量（discovery / per-task / corpus） |
| `select_output_strategy.py` | single-first 形态决策器 |
| `compile_single.py` / `compile_pack.py` | 单卡 / 整包编译 |
| `validate_skill_pack.py` | 技能包静态校验 |
| `run_trigger_evals.py` / `run_output_evals.py` / `benchmark.py` | 触发评测 / 输出评测 / 基准 |
| `diff_sources.py` / `impact_analysis.py` / `repair_flow.py` / `update_flow.py` / `apply_skill_patch.py` | 增量维护五件套 |
| `schemas/**`（13 个） | 上游契约：capability / capability-bundle / chunk / source-document / source-manifest / change-set / dependency-graph / eval-suite / failure-case / output-decision / registry-entry ×3。**本包自研 Schema 与之并存**，命名空间隔离（上游在 `vendor/`，本包在 `schemas/`） |

### 契约层：从"参考"升级为"权威"（v1.4.0）

早期把 `schemas/` 当参考资料放在一边，本包另起一套 `rulai-skill/*` 契约——**这是错的**：
契约的价值恰恰在于只有一套，另起一套等于把分块器、编译器、registry 拆成互不认的孤岛。

现在 `scripts/tdlib/contracts.py` 把这 13 份 schema 作为**权威契约**：
- 产物**按它们产出**（source-document / source-manifest / change-set / registry-entry-v2）；
- 写出前**自校验，不合规直接拒绝落盘**（实测当场抓出 4 处我自己的不合规）；
- `td.py contract list|check <name> <file>` 可单独校验；
- 校验优先 `jsonschema`，缺失时降级到内置子集校验器（覆盖 required/enum/const/pattern/type）
  并**显式输出 mode**——因为降级与完整校验可能给出不同结论，这一点必须让使用者看见。

`registry-entry-v2` 是 `additionalProperties: false`，装不下本包自有的 FIDELITY 明细，
因此旁挂到 `registry/_td-meta.json`，**不污染契约条目**。

### 为什么原样保留而不是重写

v1.1.0 曾把上述能力重新实现一遍。核证后发现上游在四处**确实更深**，重写是变浅：

1. `deterministic_cache_key(stage, implementation_version, stage_schema_version, input_hashes, params)`
   —— 缓存键含**实现版本与契约版本**。v1.1.0 只用 `(source_sha256, max_chars)`，
   **改了分块算法仍会命中旧缓存**（真实缺陷，v1.2.0 已按上游设计修正）。
2. `build_index` 用 **SQLite FTS5 + 中文字符 bigram**，查询返回**邻接块**（上游注释原文：
   "防断章取义"）。v1.1.0 的 JSON 标题树只能按路径 `--grep`。
3. `new_run_id()` + `runs/<run_id>/` **每次运行独立留痕**。v1.1.0 只有发布前快照。
4. `WriterLock`（`O_EXCL` 锁文件）**防并发写同一 target**。v1.1.0 无保护。

结论：**契约化与跨版本溯源是 cangjie 质量的主要来源**。trace-distilin 自研层定位为
「零依赖统一入口 + 上游没有的部分（FIDELITY 门槛、字幕管线、六路调研、冲突标记、prompt 编译）」。

---

## alchaincyf/nuwa-skill

- 来源：https://github.com/alchaincyf/nuwa-skill
- 授权：MIT
- 状态：**未 vendored 代码**。其 `srt_to_transcript.py` 与 `merge_research.py` 的能力
  由本包重新实现（`scripts/tdlib/transcript.py`、`scripts/tdlib/research.py`），
  原因：nuwa 的字幕下载脚本依赖固定 `/tmp` 路径且存在 marker 从未写入的缺陷；
  合并器需要与本包的一手占比统计、FIDELITY 维度 4 联动。
- 归属：见 `references/media-pipeline.md` 与 `README.md` 第二节的血缘表。

---

## 修改上游代码的流程

1. 上游逻辑有 bug → 先在其仓库提 issue/PR
2. 需要在本包内适配 → 在 `scripts/tdlib/` 写包装层，**不要直接改 `vendor/` 下的文件**
3. 上游升级 → 重新拉取覆盖 `vendor/cangjie/`，跑 `python3 tests/e2e.py` 验证 20 项仍全绿
