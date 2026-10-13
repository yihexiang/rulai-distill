# ROUTING · tongjian-wei-bundle 卡间路由与能力图谱

> 本 bundle 从《資治通鑑·周紀》提取 12 个过验框架，**实建 6 张 promoted 卡**（≥6 目标达成），
> 其余 6 个框架记为 **router 卡**（有明确独立意图、暂不单发，挂在本路由表下）。
> 路由的意义：多卡共存时最大的真实故障是**互相抢调用**——本表把「什么时候用哪张」写死。

## 一、6 张 promoted 卡（随 bundle 发布）

| slug | 标题 | 框架 | 一句话边界 |
|---|---|---|---|
| `mingfen-scan` | 名分三层扫描 | F01 | 变动**动了什么秩序/名分**（礼-分-名） |
| `cai-de-two-column` | 才德两栏 | F02 | **该不该把重任托给某人**（才德分栏） |
| `zhiren-five-looks` | 知人五视 | F04 | **怎么观察/验证一个人**（场景行为） |
| `zai-de-bu-zai-xian` | 在德不在险 | F03 | **韧性/基本面查账**（不数天险） |
| `chunchi-structure` | 唇齿结构 | F05 | **多强博弈的传导链**（谁是谁的屏障） |
| `jiao-di-cycle` | 骄敌循环 | F08 | **强弱转化**（将欲败之必姑辅之） |

## 二、卡间关系（Zettelkasten 三关系）

```
mingfen-scan ──composes── cai-de-two-column      （先看秩序是否被破坏，再看托付给谁）
mingfen-scan ──contrasts── chunchi-structure     （秩序变动 vs 博弈传导）
cai-de-two-column ──composes── zhiren-five-looks （先采证后打分：五视的实例是两栏的输入）
cai-de-two-column ──contrasts── zhiren-five-looks （评估结论 vs 观察方法）
zai-de-bu-zai-xian ──contrasts── mingfen-scan    （韧性查账 vs 秩序判读）
chunchi-structure ──composes── jiao-di-cycle     （传导链定位后，选强弱转化策略）
chunchi-structure ──contrasts── jiao-di-cycle    （看结构 vs 看转化）
```

## 三、6 个 router 卡（不单发，挂本表）

| 框架 | 标题 | 为什么不单发 | 触发时路由到 |
|---|---|---|---|
| F06 兴亡征兆扫描 | 组织兴亡五类微兆 | 与 F01/F07 高度交叠（trigger 边界需先厘清，三重验证官已注记） | 先问「是秩序问题还是征兆问题」→ mingfen-scan 或转 F07 |
| F07 坏消息上传通道诊断 | 信息通道健康度 | 属组织诊断，与 F06 同源 | 症状为「报喜不报忧」时用（卡待建） |
| F09 情报三问与反间处置 | 情报可信度三问 | 场景较窄（情报/举报场景） | 卡待建 |
| F10 批亢捣虚 | 间接路线（攻其必救） | 军事/竞争策略，与 F05 部分交叠 | 卡待建 |
| F11 时机四查 | 顺逆/窗口/归因/意志 | 与 F10 组合价值更大 | 卡待建 |
| F12 继承安排专项审计 | 继嗣/权位安排审计 | 场景具体（继承/交班） | 卡待建 |

**router 卡的处置原则**（路线图纪律）：宁可少晋级几个独立技能，也不要制造互相抢调用的技能包。
这 6 个框架的候选（含段号与引文）都在 `verified/framework.md`，需要时按同流程建卡。

## 四、与 bundle 外既有卡的关系

- `tongjian-decision-trace`（open-bundle，同语料）：它回答「**一项举措的勢—人—後果怎么追踪**」；
  本 bundle 的 6 卡回答「**用什么镜片看**」。`zhiren-five-looks`/`cai-de-two-column` 的诱饵测试已引用它做跨技能分界。
- 共同纪律：全部卡引语经 `td.py anchor`/`verify-quotes` 锚定到 `corpus/anchored/src-01-tongjian-wei.md` 的【第N段】。

## 五、已知缺口（诚实声明）

1. `mingfen-scan` 与 `zhiren-five-looks` 缺 `SOURCES.md`（规范 §6 要求，其余 4 张已有）——待补；
2. F06⑤/F12⑤ 两处框架内容引用未列入段号定位的段落（第66/78段），建对应卡时须补锚；
3. E4（反例候选）有单字引文失配（「燕雀顏色不變」应为「燕雀顏不變」）+ 一处语料外推断，已降级登记，未进任何卡；
4. bundle.json（Phase 5 编译入口）未建；Phase 4 触发/盲测/FIDELITY 均待运行（命令在各卡 test-results.md）。
