# 触发压力测试报告 · sample-bundle

> 被测：`five-affairs-seven-questions`（+ 一个对照技能 `cost-of-reversibility`）
> 答题者：独立 Agent `trigger-taker`，**只读** `eval/blind/blind-tasks.json`，
> 不知道 expect、不读任何技能文件、不知道自己在被测。
> 判分：`td.py trigger score`，机械判分，容错 0。

## 结果

通过 **6/7**（86%）→ **fail**

| 指标 | 值 |
|---|---|
| precision | 1.0 |
| recall | 0.8 |
| F1 | 0.889 |
| 诱饵通过率 | 100%（2 条）|
| 兄弟混淆率 | 0% |
| TP / FP / FN | 4 / 0 / 1 |

## 逐条

| id | 期望 | 实际 | 结果 | 类型 |
|---|---|---|---|---|
| t-01 | five-affairs-seven-questions | five-affairs-seven-questions | ✅ | trigger |
| t-02 | five-affairs-seven-questions | five-affairs-seven-questions | ✅ | trigger |
| t-03 | five-affairs-seven-questions | five-affairs-seven-questions | ✅ | trigger |
| d-01 | null | null | ✅ | decoy |
| d-02 | null | null | ✅ | decoy |
| x-01 | cost-of-reversibility | null | ❌ | trigger |
| x-02 | five-affairs-seven-questions | five-affairs-seven-questions | ✅ | sibling |

## 唯一失败项的诚实分析（x-01）

`x-01`「这个功能先上哪个版本比较稳，我已经想好了要做哪些功能」——期望判给
`cost-of-reversibility`（问的是投入规模/顺序），实际被判为 `none`。

**这项失败是真的，不解释、不掩盖。** 两种可能：

1. `cost-of-reversibility` 的 description 写得不够可区分（「投入规模/止损线」与「上哪个版本」字面距离远）；
2. `x-01` 这个 prompt 本身对「版本先后」与「可逆性」的分界不够干净——它字面问的是「先上哪个版本」，
   而不是「错了能不能收回」，被测 Agent 按字面理解判 none 也说得通。

**下一步该做什么**：先修 (1)——把对照技能的 description 写窄（「决定投入规模与先后顺序，
前提是方向已定、要决定分几批投」），再重跑 validation 集。如果仍不过，那是 (2) 的问题，改题面。

## 本次评测暴露的工具缺陷（已修）

第一次判分时诱饵通过率显示 **0%**、FP=2，与肉眼可见的作答明显矛盾。原因是判分器
把 Agent 返回的字符串 `"none"` 当成了有效 slug（`answers.get(cid) or None` 只处理空值，
不处理字符串）。已修：`tdlib/evals.py` 新增 `_norm_answer()`，把 `none/null/n-a/无/不适用`
统一归一化为 `None`。

**这个 bug 只有真实盲测才会暴露**——合成测试里 answers 是我用 Python `None` 构造的，永远走不到这条分支。
