# 效用 n=3 扩展计划（P2）：从「展示件」扩到「普遍水平」

> 目标：把 E 维效用证据从已完成的 6 张卡扩到全部 14 张卡，并补**跨模型 without 侧**，使结论从「展示件」升级为「普遍水平」。
> 状态：**计划 + 同族 n=3 自跑可行，跨模型阻塞**。截至 2026-10-12，已完成 n=3 的卡片 = 6 张。

> ⚠️ **2026-10-12 重要更正（口径）**：原以为「余下 8 张既存卡」在本仓库内，经核查**不存在**——
> 本仓库（`examples/`）只发 **6 张**已建卡（开放素材 5 + five-affairs）。README 所称「14 张真实卡」是**跨仓库计数**：
> guoxue×4 在独立仓库 `guoxue-skills/`；musk-thinking 在 `musk-run/`；musk-decisions 在 `musk-run2/`；
> 视频 1 张 `super-communicator` 在 `video-run/`。**第 2 张视频卡无实体**。故真实「实体卡」= 本仓 6 + 外部 7 = 13，
> 且 README「14 张」未披露跨仓库事实，构成「声称≠实际」披露缺口（见 defects #80 讨论）。
> 因此 P2「全量铺开 8 张」须改为**跨仓库操作**，或先把外部卡导入本仓。

## 一、已完成 vs 待做（诚实计数）

| 分组 | 卡片 | 位置 | n=3 状态 |
|---|---|---|---|
| 开放素材 5 + five-affairs | tongjian / mengzi / five-affairs / hanfei / xunzi / lunyu | **本仓库 examples/** | ✅ 已完成（2026-10-11~10-12，各 3 run，共 18 份报告） |
| guoxue×4 | bazi-paipan / geju-yunshi / quming-xue / zhouyi-yili | **独立仓库 guoxue-skills/** | ⬜ 待做（跨仓库） |
| musk×2 | musk-thinking（`musk-run`）/ musk-decisions（`musk-run2`） | **兄弟目录** | ⬜ 待做（跨仓库） |
| 视频×1（第 2 张无实体） | super-communicator（`video-run`） | **兄弟目录** | ⬜ 待做（跨仓库） |

> 注：用户表述为「余下 9 张」，对应项目口径的「既存 9 张」（five-affairs/musk×2/video×2/guoxue×4）。
> 其中 five-affairs 已于 2026-10-12 完成 n=3；musk-mental-models 与第 2 张视频卡**从未建实体**，实际外部可补 n=3 的卡 = 7 张。

## 二、同族 n=3（可行，可由本项目自跑）

每张待做卡复用已验证的方法论（`docs/utility-replication-2026-10-11.md` + `docs/utility-baseline/`），**跨仓库操作**：`--card` 指向兄弟仓库的 SKILL.md（如 `../guoxue-skills/skills/bazi-paipan/SKILL.md`），题目与答案仍落在本仓库 `docs/utility-baseline/<card>/`（随本仓入库），答题 Agent 须能读取兄弟仓库的 SKILL.md + 底稿。步骤：

1. 建 `docs/utility-baseline/<card>/questions.json`：8 题，题型对齐既有（一致性 / 边界 / 来源 / 反例），不泄露答案。
2. 派发 3 次独立会话 ×（with-skill + no-skill baseline）= **每卡 6 个答案文件**，answerer 留痕（`llm-subagent@日期 持技能答题(卡名, run-N)`），禁用 ASCII 双引号。
3. 每 run 跑 `python3 scripts/td.py eval-kit utility --card <兄弟仓库SKILL.md> --with --without --questions --subject --out run-N/utility-report.json`。
4. 数据进 `docs/utility-baseline/n3-aggregate.md` + `.json`，并触发 `tests/e2e.py` 的 `t_utility_n3_runs_complete` 守卫更新（守卫的 6 卡列表需扩为 13 实体卡）。

**工作量**：7 张外部卡 × 3 run × 2 文件 = **42 个答案文件**（非原估的 48；musk-mental-models 与第 2 张视频卡无实体，不计入）。需派发 ~42 个独立答题 Agent。是否现在全量铺开，见文末待确认项。

## 三、跨模型 without 侧（阻塞 · 需外部资源）

当前 6 卡的 without 侧均由**同模型家族**产出，只能证明「同族增强」，不能证明「跨模型增益」。要补这一侧：

- 需要**另一个模型家族**的访问权限（同族互评偏宽松的残余风险，只能靠异族消除）。
- 产物落点：复用 `docs/independent-recheck/<card>/<model>/`（reviewer_type=cross_model），或新增 `docs/utility-baseline/<card>/cross-model/` 对照目录。
- 当前**无外部模型访问权限**，此项阻塞，待用户提供。

## 四、完成后需同步的声明

- `docs/utility-replication-2026-10-11.md` 第四节边界改为「n=3 覆盖 13 张实体卡（6 本仓 + 7 外部）」。
- `n3-aggregate` 守卫与摘要表扩到 13 卡 × 3 run = 39 行（守卫的卡列表需从 6 扩到 13）。
- README 诚实边界：E 维从「展示件（6/13）」改为「普遍水平（13/13）」——但**跨模型增益仍仅同族证据**，除非 P1#2 完成；且 7 张外部卡的 n=3 是在兄弟仓库跑的，须注明。

## 五、诚实边界（本计划自带）

- 当前 E 证据是 **6/13 的展示件**，不构成「所有卡都稳定复现」的证据；7 张外部卡 + 跨模型未做。
- 同族 n=3 只解决「单次会话偶然性」，不解决「同族偏宽松」；后者完全依赖 P1#2 的跨模型复评。
- 外部卡 n=3 在兄弟仓库跑、答案落本仓；实际铺开后须登记缺陷台账（如发现新编造/降级）并补 e2e 守卫钉住「声明=实际」。

---

## 待确认项（执行前需用户决定）

1. **P2 同族 n=3 跨仓库铺开方式**：是「就地跑（指向兄弟仓库 SKILL.md，答案落本仓）」还是「先把 7 张外部卡导入本仓再跑」？用户已选「全量铺开 7 张」，待定的是操作形态。
2. **跨模型 without 侧 / P1#2**：用户已有异族 LLM，可走 `docs/independent-recheck/_STARTER-KIT.md` 自助复评；本计划第三节与之合并，不再单独依赖「项目自有异族模型」。
