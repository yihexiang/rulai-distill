# PIPELINE_STATE · 資治通鑑·周紀 book-bundle

> 状态件：记录本旗舰 bundle 的全链进度。每个 Phase 完成后更新对应行（含日期与证据）。
> 目标：证明"一本真书（≥10 万字公版书）→ ≥6 张能力卡 + 每卡评测证据"的端到端管线（路线图 A1 / D2-D4）。

## 总览

| 项 | 值 |
|---|---|
| 书 | 資治通鑑·周紀（`corpus/anchored/src-01-tongjian-wei.md`，170KB / 148 块 / 约 5.7 万字） |
| bundle 目录 | `books/tongjian-wei-bundle/` |
| 开始日期 | 2026-10-13 |
| 目标卡数 | ≥6（含既存 tongjian-decision-trace 的深化 + 新提取） |

## Phase 进度

| Phase | 内容 | 状态 | 证据 |
|---|---|---|---|
| 0 · 整书理解 | BOOK_OVERVIEW | ✅ 完成（2026-10-13） | `BOOK_OVERVIEW.md` |
| 0.5 · 语料规整 | corpus-anchor → 分块 + 索引 | ✅ 完成 | 148 块；`src-01-tongjian-wei.md.td`；`td.py index --grep` 可用 |
| 1 · 五路候选提取 | framework / principle / case / counter-example / glossary | ✅ 完成（2026-10-13） | `candidates/*.md`：framework 12 / principle 12 / case 10 主选+8 备选+3 史论 / counter-example 10+4 / glossary 15，均带【第N段】定位 |
| 1.5 · 三重验证 | 来源充分性 / 可执行性 / 任务效用 | ✅ 完成（2026-10-13） | `verified/framework.md`（12/12 过验、0 rejected、全建议 promoted）+ `verified/principle-and-counter.md`（26 过验：25 过 + 1 降级 E4）+ `rejected/*.md`（0 rejected，E4 降级三处修正要求登记在案） |
| 1.6 · 晋级门 | 五项独立判据 → promoted / router | ✅ 完成（2026-10-13） | 12 框架全绿 promoted；本 bundle 实建 6 张（见 Phase 2），其余 6 个框架记为 router 卡（`ROUTING.md`） |
| 2 · 能力构造 | RIA+EB 六段卡 | ✅ 完成（2026-10-13，6/6） | `skills/` 下 6 张卡，每张均实跑静态自验：validate error 0/warn 0、anchor PASS（41/67/43/57/60/68 条）、verify-quotes 全命中、lint-quotes 干净、output-eval 六段齐全 |
| 3 · Zettelkasten | depends-on / composes-with / contrasts-with | 🔄 部分 | 6 卡两两交叉 related_skills 已写（含跨卡诱饵双向分界）；依赖图待补 `ROUTING.md` 收口 |
| 4 · 压力测试 + FIDELITY | trigger（跨技能诱饵）+ 双 Agent 评测 | ⬜ | 每卡 `test-prompts.json`（3 触发 + 2-3 诱饵，含跨卡诱饵）已就绪；`test-results.md` 如实标「Phase 4 待运行」（前置：bundle.json 未建 + 盲测需独立答题 Agent + FIDELITY 需 ≥2 独立评分 Agent） |
| 5 · 形态决策 + 编译 | strategy → compile(single+pack) | ⬜ | `td.py strategy` / `compile` 输出 |
| 6 · 登记 | registry 条目 | ⬜ | `registry/<slug>/` |

## 验收标准（路线图 §三，全部机器可查）

1. 全卡 `td.py validate` error 0；
2. 引语锚定 0 挂错（`td.py anchor` / `verify-quotes`）；
3. ≥6 张卡，每卡带 `test-prompts.json` + `test-results.md`；
4. token 节省实测更新进 `benchmarks/` 报告；
5. 逐张复跑命令进 README。

## 已确认的语料事实（供提取 Agent 引用）

- 卷首「臣光曰」论礼/分/名（第3段）；智伯五贤一不仁（第3段）；赵襄子选晋阳（第3段）；
  段规"将欲败之必姑辅之"、任章"骄敌相亲"之策（第3段）；絺疵察韩魏必反（第3段）。
- 提取时必须给**段号定位**（【第N段】），否则三重验证的来源充分性不过。

## ⚠️ 工具偏差记录（2026-10-13，Phase 1）

提取子 Agent 的运行环境里 **Bash 被 SIGTERM、Grep 超时**，`td.py index --grep` 无法执行。
5 个 Agent 均改用 **Read 直读**语料取句（引语真实、段号来自【第N段】锚点），并已在各
`candidates/*.md` 文件头部如实注明。**两个下游后果**：
1. 候选文件里的引文为**可读性规整版**（剥离了维基文库 wikitext 标记 `-{于}-`/`〔〕`校记/`{{*|}}`/`<!-- -->`，汉字未改）——Phase 1.5 跑 `td.py verify-quotes`/`anchor` 时须**对回原始行**做逐字比对，不能直接拿候选文件的引文去核；
2. 段号 → chunk_id 映射未做（sidecar 已生成：`corpus/anchored/src-01-tongjian-wei.md.td`，148 块），三重验证如需 chunk 级定位需补一次映射。

**处理**：Phase 1.5 的三重验证必须以**原始语料行**为唯一真源重取支撑句，候选文件只当索引用。
