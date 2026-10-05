# 阶段 4 · 触发压力测试

> 目标：让技能包在真实部署中**该触发时触发、不该触发时忍住**、**兄弟技能之间不抢调用**。

## 核心问题

只测 positive case 的技能包，看起来永远很好——因为被测时只有一个技能候选。但实际部署时，Agent 面对的是**整包 N 个技能的 name + description 列表**，要自己选。

**真实故障不是"不触发"，而是"乱触发"。** 同一本书拆出 10+ 技能后，互相抢调用是最常见的真实故障，只测"完全无关的场景"发现不了。

## 测试套件结构

```json
{
  "suite_id": "<slug>-trigger-v1",
  "split_seed": 42,
  "cases": [
    {
      "case_id": "t01",
      "type": "should_trigger",
      "prompt": "<用户会说的话>",
      "expected_behavior": "应激活 <slug>",
      "notes": "判定依据"
    },
    {
      "case_id": "t02",
      "type": "should_not_trigger",
      "prompt": "<不该激活此技能的场景>",
      "expected_behavior": "不激活 <slug>",
      "notes": "该激活谁，或明确不激活任何技能"
    },
    {
      "case_id": "t03",
      "type": "should_trigger_sibling",
      "prompt": "<应该激活兄弟技能的 prompt>",
      "expected_behavior": "不激活 <slug>，应激活 <sibling-slug>",
      "notes": "跨技能混淆测试（硬性要求）"
    }
  ]
}
```

## 配比要求

| 类型 | 数量 | 备注 |
|---|---|---|
| `should_trigger` | 3 | 覆盖不同表达方式（直白/口语/隐含） |
| `should_not_trigger` | 2-3 | 至少 1 条是"看起来像但不适用" |
| `should_trigger_sibling` | ≥1 | **硬性要求**，无此条一律打回 |

**诱饵（should_not_trigger）容错为 0。**

## 盲测协议

1. **出题**：写下 test cases，出题者记录理由
2. **准备任务包**：`prepare` 只生成 prompt + 候选技能目录清单，**隐藏** `type` / `expected_behavior` / `notes`
3. **答题**：把整包所有技能的 name + description 给**干净上下文的独立 sub-agent**，让它做"该激活哪一个"的选择题
4. **判分**：对照 suite 判 precision / recall / F1 + 兄弟混淆率
5. **回归**：已看过的失败用例加入回归集；最终验收用**未参与调优的保留用例**

## 切分纪律

固定种子做 60/40 train/validation 切分，**validation 在选版前保持隐藏**。

```
split_seed 固定 → 保证不同机器上切分结果一致
```

## 修复决策树

失败时先判断是**测试设计问题**还是**技能设计问题**：

```
测试失败
├── 这个 case 是你为了"凑诱饵"而设计过狠的吗？
│   └── 是 → 修测试，但必须记录理由（不得无理由改答案）
├── 兄弟技能抢调用？
│   ├── 对应技能存在但没晋级 → 考虑晋级或合并
│   ├── 两个技能边界模糊 → 在 frontmatter 补"不适用" + 强化易混淆辨析段
│   └── 技能数量超预算 → 降级合并，减少独立技能数
└── 单纯触发描述不清？
    └── 改 A2 段的"语言信号"，把用户真实说法直接写进去
```

**禁止为了通过而改答案。** 修改预期答案必须留独立理由和审计记录。

## 记录

```bash
python3 scripts/td.py evalsplit <suite.json>       # 切分
python3 scripts/td.py evalprepare <suite.json> --skills a,b,c --out <dir>
python3 scripts/td.py evalscore <suite.json> --results <results.jsonl> --out <report.md>
```

报告必须记录：宿主/模型版本、实际运行条件、是否为独立 sub-agent（还是 fallback 自测）。
