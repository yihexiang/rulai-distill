# CLAIMS · 对外声称台账（P0-4）

> **这份台账的用途**：本项目最高频的病是「**声称 ≠ 实际**」——
> 文档里写一个数字，没有任何东西会红。本文与 README/GUIDE 的每个对外数字一一对应，
> 每条给出**可复跑的证据**与**最近核验日期**。
>
> 机器核验：`python3 docs/verify_claims.py`（CI 的 docs-check 会跑）
> 回归守卫：`t_claims_have_evidence`
>
> **规则**：声称引用的测试名必须真实存在；`100` / `37` / `66`
> 三个占位数字必须与仓库现状相等。数字腐烂 → CI红。

## 当前事实（**这一节的数字是机器写进来的，别手改**）

<!-- facts:begin -->
```text
tests = 107
subcommands = 37
defects = 73
```
<!-- facts:end -->

| 量 | 值 | 怎么数的 |
|---|---|---|
| 回归项 | **107** | `tests/e2e.py` 的注册表条目数 |
| 子命令 | **37** | `td.py --help` 里 argparse 打印的 choices |
| 缺陷台账 | **-1** | `tdlib/defects.py` 的 `DEFECTS` 长度 |

正文里的数字由 `docs/verify_claims.py --sync` 从上面那段的实测值统一改写，
**人手填的数字一律腐烂**。默认（不加 `--sync`）只校验、不改写，所以 CI 里是纯检查。

## 对外声称

| 声称 | 证据 | 最近核验 |
|---|---|---|
| 端到端回归全绿，且**新机器 clone 后也全绿**（不靠跳过） | `t_no_external_fixture_deps` · `t_no_unregistered_tests` | 2026-10-10 |
| `gate` 默认要求交叉复核记录，单评分一律不判通过 | `t_gate_requires_cross_review` · `t_ci_artifact_gate` | 2026-10-10 |
| `verify-quotes` / `anchor` / `lint-quotes` 在**真实素材**上抓到过真问题 | `t_verify_quotes_misplaced_vs_fabricated` · `t_anchor_cjk_short_quotes` · `t_lint_quotes_technical_and_sectional` | 2026-10-10 |
| 工具链在**9 张真实卡**上实跑 `validate`，**error 0** | `t_real_sample_artifacts` · 逐卡 `td.py validate <发布根>`（见下表） | 2026-10-10 |
| 交叉复核已在 **6 张卡**上跑通（独立答题 Agent + 2 个独立评分 Agent） | `t_gate_requires_cross_review` · 逐张 `FIDELITY.json`（见下表） | 2026-10-10 |
| 独立性的边界是「**结构独立 ≠ 组织独立**」 | `t_gate_requires_cross_review` | 2026-10-10 |
| 引语核验只能证明「它检查过的那一面」 | `t_verify_quotes_lang_filter_not_silent` · `t_anchor_unanchored_not_fail` | 2026-10-10 |
| 长书分块的 token 节省：**区间 1.0×～34×**，短书/宽词几乎不省 | `t_token_savings_benchmark` · `benchmarks/token-savings/report-2026-10-10.md` | 2026-10-10 |
| 缺陷台账里**多数错在验证工具自身**，不在卡片内容 | `t_defect_ledger_stats` | 2026-10-10 |
| 缺陷数 / 分布 / 回归项数三者由测试强制相等 | `t_defect_ledger_stats` · `t_defect_regression_ledger` · `t_docs_no_drift` | 2026-10-10 |
| 回归测试**不得静默依赖作者工作区** | `t_no_external_fixture_deps` | 2026-10-10 |
| CI 的每一步都能在本地跑通（不必等CI 才发现） | `t_self_validate_clean_and_doc_structure` · `tests/ci_local.sh` | 2026-10-10 |
| 开放素材端到端建卡已闭环：論語卡（公版典籍）随包分发并通过 `validate` + `lint-quotes`，印证工具链能消化 25 万字节级公版语料（不止小样本） | `t_real_sample_artifacts` · `t_corpus_anchor_splits_by_structure` · `scale-evidence-open-material-2026-10-10.md` | 2026-10-10 |

## 逐卡证据（不是"12 张"，实测 9 张）

`validate` 必须在**发布根**上跑，不是单个技能目录——
单技能目录里那些 `../../README.md`、`../geju-yunshi/` 是合法的兄弟链接，
在发布根上才成立（这一条本身是 `t_dead_link_relative_within_root` 的判据）。

| 卡 | 发布根 | validate | 交叉复核 |
|---|---|---|---|
| `five-affairs-seven-questions`（书·孙子） | `examples/sample-bundle` | error 0 | **93 / A**（90/98，gap 8） |
| `musk-thinking`（人物·旧） | `musk-run/skills/musk-thinking` | error 0 | 未跑（历史单次 95/A **未交叉复核**） |
| `musk-decisions`（人物·新） | `musk-run2/skills/musk-decisions` | error 0 | **90 / A**（92/89，gap 3） |
| `two-kinds-of-procrastination`（视频·TED） | `video-run/skills/two-kinds-of-procrastination` | error 0 | 未跑（历史 93.5/S 为**自评**） |
| `problem-before-evidence`（视频） | `video-run/skills/problem-before-evidence` | error 0 | 未跑 |
| `bazi-paipan` | `guoxue-skills` | error 0 | **93 / A**（92/93，gap 1） |
| `geju-yunshi` | `guoxue-skills` | error 0 | **95 / A**（96/93，gap 3） |
| `quming-xue` | `guoxue-skills` | error 0 | **96 / A**（96/95，gap 1） |
| `zhouyi-yili` | `guoxue-skills` | error 0 | **96 / A**（97/97，gap 0） |
| `lunyu-conduct`（开放·論語） | `examples/open-bundle` | error 0 | 待补（建卡完成、`eval-kit init` 已出套件；独立交叉复核未跑） |

**交叉复核 6 张里有一处要单独说**：`zhouyi-yili` 两个评分者给出**完全相同**的总分。
那不构成两次独立证实——`eval-kit check` 会就"多个评分给相同分数"发提醒，
但**它不是否决项**（那条提醒防的是复制粘贴，不是真的独立一致）。

## 三条不能写进 README 的诚实边界

1. **6 张交叉复核 ≠ 6 类素材**。guoxue 四张同属国学、同一套语料规整方式；
   它们证明的是"流程在这类素材上跑得通"，**不是"这个方法对所有素材都成立"**。
2. **`musk-thinking` 的 95/A 是单次自评**，从未交叉复核。它不该和上面 6 张并排。
3. **卡片内容真错的只有 1 条**（台账里 `卡片内容真错` 那一类），
   其余全是工具自身的错。这**不是"卡片质量很好"的证据**——
   它只说明"我们检查的地方还没发现卡片错"，而检查面本身是有限的。

## 新增声称时必须做的事

1. 在上表加一行，**证据列填真实存在的测试名或可复跑命令**；
2. 若含数字，用 `100` / `37` / `66` 占位，**不要手填**；
3. 跑 `python3 docs/verify_claims.py`，红了就**改声称或改证据，不改脚本让它闭嘴**。