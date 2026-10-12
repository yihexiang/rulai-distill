# 效用 n=3 扩展计划（P2）：从「展示件」扩到「普遍水平」

> 目标：把 E 维效用证据从已完成的 6 张卡扩到全部 14 张卡，并补**跨模型 without 侧**，使结论从「展示件」升级为「普遍水平」。
> 状态：**计划 + 同族 n=3 自跑可行，跨模型阻塞**。截至 2026-10-12，已完成 n=3 的卡片 = 6 张。

## 一、已完成 vs 待做（诚实计数）

| 分组 | 卡片 | n=3 状态 |
|---|---|---|
| 开放素材 5 + five-affairs | tongjian / mengzi / five-affairs / hanfei / xunzi / lunyu | ✅ 已完成（2026-10-11~10-12，各 3 run，共 18 份报告） |
| 既存 9（扣除 five-affairs） | musk-decisions / musk-mental-models / video-X×2 / guoxue×4 | ⬜ **待做 8 张** |

> 注：用户表述为「余下 9 张」，对应项目口径的「既存 9 张」（five-affairs/musk×2/video×2/guoxue×4）。其中 five-affairs 已于 2026-10-12 完成 n=3，故**实际待做 = 8 张**（musk×2 + video×2 + guoxue×4）。若坚持「9 张」口径，则 five-affairs 属重复覆盖，无新增工作量。

## 二、同族 n=3（可行，可由本项目自跑）

每张待做卡复用已验证的方法论（`docs/utility-replication-2026-10-11.md` + `docs/utility-baseline/`），步骤：

1. 建 `docs/utility-baseline/<card>/questions.json`：8 题，题型对齐既有（一致性 / 边界 / 来源 / 反例），不泄露答案。
2. 派发 3 次独立会话 ×（with-skill + no-skill baseline）= **每卡 6 个答案文件**，answerer 留痕（`llm-subagent@日期 持技能答题(卡名, run-N)`），禁用 ASCII 双引号。
3. 每 run 跑 `python3 scripts/td.py eval-kit utility --card <SKILL.md> --with --without --questions --subject --out run-N/utility-report.json`。
4. 数据进 `docs/utility-baseline/n3-aggregate.md` + `.json`，并触发 `tests/e2e.py` 的 `t_utility_n3_runs_complete` 守卫更新。

**工作量**：8 卡 × 3 run × 2 文件 = **48 个答案文件**（同前 6 卡的 18 份，规模约 2.7 倍）。需派发 ~48 个独立答题 Agent。是否现在全量铺开，见文末待确认项。

## 三、跨模型 without 侧（阻塞 · 需外部资源）

当前 6 卡的 without 侧均由**同模型家族**产出，只能证明「同族增强」，不能证明「跨模型增益」。要补这一侧：

- 需要**另一个模型家族**的访问权限（同族互评偏宽松的残余风险，只能靠异族消除）。
- 产物落点：复用 `docs/independent-recheck/<card>/<model>/`（reviewer_type=cross_model），或新增 `docs/utility-baseline/<card>/cross-model/` 对照目录。
- 当前**无外部模型访问权限**，此项阻塞，待用户提供。

## 四、完成后需同步的声明

- `docs/utility-replication-2026-10-11.md` 第四节边界改为「n=3 覆盖 14 张卡」。
- `n3-aggregate` 守卫与摘要表扩到 14 卡 × 3 run = 42 行。
- README 诚实边界：E 维从「展示件（6/14）」改为「普遍水平（14/14）」——但**跨模型增益仍仅同族证据**，除非第三节完成。

## 五、诚实边界（本计划自带）

- 当前 E 证据是 **6/14 的展示件**，不构成「所有卡都稳定复现」的证据；余下 8 张 + 跨模型未做。
- 同族 n=3 只解决「单次会话偶然性」，不解决「同族偏宽松」；后者完全依赖第三节的跨模型复评。
- 本计划不声称已执行；实际铺开后须登记缺陷台账（如发现新编造/降级）并补 e2e 守卫钉住「声明=实际」。

---

## 待确认项（执行前需用户决定）

1. **同族 n=3 是否现在全量铺开 8 张**（48 个 Agent 派发，token 较重）？还是先做 1-2 张 pilot 验证编排仍顺、再决定是否铺开？
2. **跨模型 without 侧**：是否有可用的另一模型家族访问权限？如有，提供后本计划第三节方可执行。
