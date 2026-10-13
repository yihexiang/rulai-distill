# parity · rulai-distill ↔ cangjie 2.5.0 引擎对齐表（2026-10-13）

> 依据：`scripts/tdlib/upstream.py` 的 `MAPPING`（td.py 子命令 → vendored 上游脚本）+ `scripts/vendor/cangjie/` 实盘清单 + `scripts/vendor/PROVENANCE.md`（v2.5.0，2026-10-04 取回）。
> 防腐烂：`tests/e2e.py` 的 `t_parity_table_matches_upstream_mapping` 逐行比对本表与 `MAPPING`——任何一侧增删而另一侧没同步，e2e 即红。
> 结论口径：**「封装」= vendored 直通 + 本包入口；「自研」= 上游没有、本包实现；「不做」= 有明确理由**。每行必须有归属，不允许"既没做也没说"。

## 一、总览

- **16 类上游能力全部 vendored 且有 `td.py` 入口**，版本对应 cangjie v2.5.0（+ 2026-09-13 补丁期 scripts）。
- 契约锁定：`scripts/vendor/VENDOR.sha256` + `contract-check` CI 守；`td.py contract list` 可查。
- 差的不是能力，是**旗舰级真实长书的端到端证据**（A1，见 D2-D4 book-bundle）与**发布链细节补齐**（A2 的 BUILD_INFO，本轮补）。

## 二、16 类能力逐行 parity

| td.py 子命令 | cangjie 出处（vendored 脚本） | 能力 | rulai 归属 | 决定 |
|---|---|---|---|---|
| chunk | `build_chunks.py` | 结构感知分块 + 规范化 + 版本化缓存 | vendored 直通（`tdlib/chunking.py` 适配 + runs/ 留痕） | 封装 |
| lexindex | `build_index.py` | SQLite FTS5 词法索引 + 邻接块扩展 | vendored 直通 | 封装 |
| count | `count_tokens.py` | token 计量（需 tiktoken） | vendored 直通 | 封装 |
| strategy | `select_output_strategy.py` | single/pack 形态决策 | vendored 直通 | 封装 |
| validate | `validate_skill_pack.py` | 技能包静态校验（需 PyYAML） | vendored 直通 | 封装 |
| compile | `compile_pack.py` | pack 编译（需 PyYAML） | vendored 直通 + 本包 `tdlib/publish.py` 收口（WriterLock / published_hashes / snapshot / rollback / 原子替换） | 封装 + 增强 |
| compile-single | `compile_single.py` | single 编译（需 PyYAML） | vendored 直通 | 封装 |
| trigger | `run_trigger_evals.py` | 触发压力评测 | vendored 直通（Agent 作答、脚本判分、容错 0） | 封装 |
| output-eval | `run_output_evals.py` | 产物机械体检 | vendored 直通 | 封装 |
| bench | `benchmark.py` | 重复计时基准 | vendored 直通 | 封装 |
| diff | `diff_sources.py` | 两版产物差异 | vendored 直通 | 封装 |
| impact | `impact_analysis.py` | 改动影响面 | vendored 直通 | 封装 |
| repair | `repair_flow.py` | 机械修复（默认 dry-run） | vendored 直通 | 封装 |
| patch | `apply_skill_patch.py` | 结构化补丁（默认 dry-run） | vendored 直通 | 封装 |
| update | `update_flow.py` | 重新校验 + 重编译（需 PyYAML） | vendored 直通 | 封装 |
| cli | `cangjie.py` | 上游统一 CLI（doctor/status 等） | vendored 直通 | 封装 |

**上游公共原语**（`cangjie_common.py`，非独立子命令）：版本化缓存键 / `new_run_id()`+`runs/<run_id>/` / `WriterLock`（O_EXCL）/ `atomic_publish` / `snapshot_dir`。rulai 侧对应：`tdlib/chunking.py`（runs/ 留痕）、`tdlib/publish.py`（WriterLock / published_hashes / snapshot / rollback）——**上游原语已在本包侧落地，不是只写在文档里**。

**本包自研层**（上游没有的部分）：`fetch-subtitle`（字幕管线，唯一联网命令）、`transcript`、`research`（六路调研 + 车道覆盖审计）、`corpus-anchor` / `anchor` / `verify-quotes` / `lint-quotes` / `overlap` / `audit-coverage`（核验族）、`gate`（FIDELITY 门槛）、`eval-kit` / `cross-review`（评测族）、`prompt`（prompt 编译）、`contract`（契约层）。

## 三、A1-A4 差距项逐条（路线图 §一）

| # | cangjie 有什么 | rulai 现状（2026-10-13 核验） | 决定 |
|---|---|---|---|
| A1 | 旗舰书样例 `books/naval-almanack-skill`：一本真书 → ≥6 卡 + PIPELINE_STATE / BOOK_OVERVIEW / candidates(5类) / verified / rejected / 每卡 test-prompts + test-results | 本仓只有小样例（sample-bundle 1 卡 + open-bundle 5 卡单片） | **做**：D2-D4 以 `corpus/anchored/src-01-tongjian-wei.md`（170KB）跑旗舰 book-bundle |
| A2 | 发布链细节：per-run workdir / 写锁 / staging / 手改检测（三选一保护）/ 原子发布 / 快照回滚 / BUILD_INFO / harness 包 | per-run workdir（`chunking.py` runs/）、WriterLock、published_hashes 手改检测、原子发布、snapshot/rollback **均已落地**；**BUILD_INFO 本轮补进 `tools/make_release.sh`**；harness 包（DeepSeek Harness 形态）**不做**——rulai 按"职能对齐"用 `install.sh`（9 Agent）+ zip/sha256 + GitHub Release，不照搬 cangjie 自建站点分发 | 封装（已有）+ 补 BUILD_INFO + harness 不做（理由：避免为对标造假页，路线图 §四同） |
| A3 | 持续演进机制（版本化、补丁、Release） | vendored 已同步 v2.5.0；**无"跟新版"例行机制** | **做**：VENDOR bump SOP 写进 `GUIDE.md`（fetch → sha256 diff → contract-check → 全量回归 → 更新 PROVENANCE） |
| A4 | 多平台分发（Harness 包 / ZIP+SHA256 / 网站 / star 史） | `install.sh` 覆盖 9 个 Agent + `make_release`（zip+sha256，缺陷 #76 收口）+ GitHub Release；网站不做 | 已有 + 网站不做（职能对齐声明，做法正确）；只差"能力包"分发形态 → 后置 |

## 四、验收与防腐烂

1. 本表 16 行工具与 `upstream.py` 的 `MAPPING` **键集合一致**（守卫 `t_parity_table_matches_upstream_mapping` 强制）。
2. 每行"决定"∈ {封装, 封装 + 增强, 自研, 不做}；"不做"必须带理由。
3. A1 的 book-bundle 验收标准见 `docs/` 下该 bundle 的 PIPELINE_STATE（validate error 0 / 引语锚定 0 挂错 / ≥6 卡各带 test-prompts + test-results）。
