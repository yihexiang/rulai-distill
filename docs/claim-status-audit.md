# claim-level 存量审计（来源状态 · 2026-10-10）

> 由 `t_validate_claim_status` 的同一判据扫出（`CLAIM_STATUS_SEC_RE` / `CLAIM_STATUS_TAG_RE`）。
> 规则：**声明了区块必须逐条标注**（缺→error）；**未声明**→warn 并登记于此。

| 卡 | 论断条数 | 状态 | 首个问题 |
|---|---|---|---|
| `rulai-distill/examples/open-bundle/skills/lunyu-conduct/SKILL.md` | 7 | 已声明 ✓ |  |
| `rulai-distill/examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md` | 6 | 已声明 ✓ |  |
| `guoxue-skills/skills/bazi-paipan/SKILL.md` | — | 缺区块（warn） |  |
| `guoxue-skills/skills/geju-yunshi/SKILL.md` | — | 缺区块（warn） |  |
| `guoxue-skills/skills/quming-xue/SKILL.md` | — | 缺区块（warn） |  |
| `guoxue-skills/skills/zhouyi-yili/SKILL.md` | — | 缺区块（warn） |  |
| `musk-run/skills/musk-thinking/SKILL.md` | — | 缺区块（warn） |  |
| `musk-run2/skills/musk-decisions/SKILL.md` | — | 缺区块（warn） |  |
| `video-run/skills/problem-before-evidence/SKILL.md` | — | 缺区块（warn） |  |
| `video-run/skills/two-kinds-of-procrastination/SKILL.md` | — | 缺区块（warn） |  |
| `bazi-run/dist/bazi-paipan/SKILL.md` | — | 缺区块（warn） |  |
| `quming-run/build/skills/quming-xue/SKILL.md` | — | 缺区块（warn） |  |
| `quming-run/build.td_snapshots/20261008-231254/data/skills/quming-xue/SKILL.md` | — | 缺区块（warn） |  |
| `quming-run/build.td_snapshots/20261008-231407/data/skills/quming-xue/SKILL.md` | — | 缺区块（warn） |  |
| `yijing-run/build/skills/zhouyi-yili/SKILL.md` | — | 缺区块（warn） |  |
| `yijing-run/build.td_snapshots/20261009-020349/data/skills/zhouyi-yili/SKILL.md` | — | 缺区块（warn） |  |
| `yijing-run/build.td_snapshots/20261009-095246/data/skills/zhouyi-yili/SKILL.md` | — | 缺区块（warn） |  |
| `yijing-run/dist/zhouyi-yili/SKILL.md` | — | 缺区块（warn） |  |

**结论**：16 张卡未声明（warn，不阻断发布）。
