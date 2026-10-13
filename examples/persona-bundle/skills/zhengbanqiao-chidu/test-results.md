# test-results · zhengbanqiao-chidu

> 全部命令在仓库根 `/Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill` 下执行，
> 用托管 Python：`/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3`
> （系统 `/usr/bin/python3` 是 3.9.6，跑不了本项目）。
> 以下输出为 **2026-10-14 实跑结果**，不是建卡时的估计。

## 一、机械自验（实测）

| 命令 | 结果 |
|---|---|
| `td.py validate` | **error 0 / warn 0** |
| `td.py anchor`（单 corpus src-12） | **84 条候选引语，锚定命中 71，未标注段号 12；NOT_IN_CORPUS 0 → PASS** |
| `td.py lint-quotes` | 检查 71 条；**未发现用字不一致（简繁/异体）**；无省略号节引 |

`anchor` 实测输出（节选）：

```
引语 84 条：锚定命中 71，未标注段号 12
判定明细：{'ANCHOR_HIT': 71, 'UNANCHORED': 12, 'ANCHOR_PARTIAL': 1}
抽取：候选 123 = 认出 84 + 噪声 1 + 中文太短跳过 38（自检 True）
   其中短引语（<8 汉字、逐字见于语料、同行带 §N）已纳入核验并命中 13 条
✅ 判定 PASS：71 条带段号标注的引语全部锚定在声明的段号内；
   另有 12 条无 §N 标注、不可定位（未核验，不判失败）
```

12 条无 §N 标注的引语是**本卡的规则表述/举例**（如「得志澤加於民」「明理作個好人」「最重農夫」），
非逐字引语，按规则「无出处即跳过」，与 verify-quotes / lint-quotes 同口径，不判失败。
其中若干（如「得志澤加於民」§1014、「明理作個好人」§1028）实跑确认命中语料对应段。

复跑命令：

```bash
P=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
CARD=examples/persona-bundle/skills/zhengbanqiao-chidu/SKILL.md

$P scripts/td.py validate $CARD
$P scripts/td.py anchor $CARD \
    --corpus corpus/anchored/src-12-zhengbanqiao.md
$P scripts/td.py lint-quotes $CARD
```

## 二、`verify-quotes` 对本卡**不适用**——这条必须写清楚，不能 silent

实测：

```
$P scripts/td.py verify-quotes $CARD corpus/anchored/src-12-zhengbanqiao.md
   引用 0 个（条目引用 0 + 时间戳 0 + 书类引用块 0）
   逐字引语核验 0 条 → 命中 0 条
❌ ⚠️ 空集假绿：卡片里含引语（「」/引号），但没有任何可识别的定位标记
```

**原因不是卡片没引语，是工具不认这种写法。** `verify-quotes` 认三种定位形态：
`【第N条】`、`[HH:MM:SS]` 时间戳、以及 `>` 引用块 + `—— 《书名》` 出处行。
本卡用行内 `（src-12 §N）` 标注（单语料也统一用此形态，便于与王阳明/曾国藩卡的跨卡口径一致），三种形态都不匹配。

**本卡的核验改由 `anchor` 承担，且判据更强**：

| 工具 | 验什么 | 本卡 |
|---|---|---|
| `verify-quotes` | 引语在语料里**存在**吗 | ❌ 不适用（格式不认，返回 0 条） |
| `anchor` | 引语在**它声明的那一段**里吗 | ✅ 71/71 PASS，支持行内 `src-XX §N` |

只验"存在"不验"归属"正是 C10 要防的；`anchor` 验的是更强的那一层。
**但"0 条核验"绝不能被当成"0 条问题"**——所以这里显式写明，并已登记为缺陷 **#84**。

## 三、表达 DNA 量化（实测）

```bash
$P benchmarks/expression-dna/measure.py \
   --corpus corpus/anchored/src-12-zhengbanqiao.md --speaker-only 余
```

实测（`--speaker-only 余`，只取 64 段／2,407 段正文，12,903 字）：

| 指标 | 值 |
|---|---|
| 说话人过滤 | `余`（只取 64 段，12,903 字） |
| 句均长 | **18.8 字**（标准差 10.3，最长 77 字，共 653 句） |
| 转折词密度 | **5.43 次/千字**（然×36、雖×9、但×5、獨×5、顧×4、第×8） |
| 确定性比值 | **0.57**（绝对 2.33／存疑 4.11，每千字）→ 判「我不确定」型 |
| 自称密度 | 4.5 次/千字（多以「愚兄」自呼，半师半友对弟弟说话） |
| 高频二元 Top4 | 板橋×45、乾隆×23、鄭燮×14、畫竹×12 |
| 幽默 | **机械不可判**（脚本明示 `machine_judgable: false`），人工判为**自嘲/戏谑型**（自嘲自己的无用与矛盾） |

三人对照（同一脚本、同一口径）：

```bash
$P benchmarks/expression-dna/measure.py --corpus corpus/anchored/src-10-chuanxilu.md --speaker-only 先生曰
$P benchmarks/expression-dna/measure.py --corpus corpus/anchored/src-12-zhengbanqiao.md --speaker-only 余
$P benchmarks/expression-dna/measure.py --corpus corpus/anchored/src-08-zengguofan-jiashu.md \
      corpus/anchored/src-09-zengguofan-yuze-wuzhen.md --merge
```

| 人 | 语料 | 字数 | 句均长 | 转折/千字 | 确定性比值 | 自称/千字 |
|---|---|---:|---:|---:|---:|---:|
| 王阳明 | src-10（过滤「先生曰」） | 43,790 | 19.8 | 7.22 | **3.07** | 3.06 |
| 郑板桥 | src-12（过滤「余」） | 12,903 | 18.8 | 5.43 | **0.57** | 4.50 |
| 曾国藩 | src-08+src-09 合并 | 4,138 | 22.9 | 4.59 | 2.62 | **11.12** |

> 曾国藩单份 2,627 字低于脚本阈值（3,000），脚本按纪律**拒绝给数**（`insufficient_sample`）；
> 上表取两语料 `--merge` 后的 4,138 字。这不是缺陷，是脚本的设计行为——小样本上给句长与词频就是假精确。

## 四、建卡过程中被工具抓出并已修的问题（留痕）

建卡自验不是一次通过的，`anchor` 抓到真问题（本次修复详见下方「本轮修复」）：

| 轮次 | 工具 | 抓到什么 | 怎么修 |
|---|---|---|---|
| 首轮 | `anchor` | **2 条 `NOT_IN_CORPUS`**：「杜詩有人陸詩無人」(§1053)、「盆鱼笼鸟，其钜细仁忍何如也」(§1032) | 前者是**改写非连续串**，改为连续原文「杜詩之有人，誠有人也」并正确挂 §1022；后者是**简体+缺叹号**，改为繁体「盆魚籠鳥，其鉅細仁忍何如也！」 |
| 首轮 | `anchor` | **段号错位**：语料经 corpus-anchor 重排后段号偏移（如 §1014 置产段实为 §1015、§1006 教读段实为 §1007） | 全卡段号以重排后实际 `【第N段】` 为准，逐条重标 |
| 首轮 | `anchor` | **简化字混用**：「盆鱼笼鸟」等 | 统一为繁体原字形 |
| 首轮 | `validate` | 段级归属声明须可机械复算 | 所有引语逐字抄繁体原文 + 行内 `src-12 §N`，anchor 71/71 复算 |
| 本轮 | `validate` | 人物卡须过手来源权重声明 | 补「一手来源合计权重：1.0」 |

> 这一节是**故意留着的**：它说明"建卡自验全绿"通常不是一次就绿的。
> 同一教训见缺陷 #83（随包卡自陈与实跑不符）、#84（verify-quotes 空集假绿）。

## 五、FIDELITY / 盲排 / cross-review（诚实状态）

> 本卡已建齐 `eval-kit` 预设（questions.json 五题人工出题 + style-decoys.md 两份通用对照样本），
> 并**实跑**了 `eval-kit check` → `FIDELITY.json` → `gate`。但必须写明：**实跑是同一家族 LLM 自测
> （答题者 + 两评分者均为本项目主 Agent，eval_mode 已诚实标为 `fallback-self`）**，
> 不是独立双 Agent 复评。

| 项 | 状态 |
|---|---|
| eval-kit 预设 | ✅ 完成（5 题：3 立场 + 1 超范围 edge + 1 盲排 style） |
| `eval-kit check` 实跑 | ✅ 已跑，合并维度总 87/A（两评分者分差 3 ≤ 10） |
| `gate`（严格 / 自测） | ⚠️ 自测按纪律打折（style 置 0、维度 1/3 ×0.8）→ 65/C，**明确不通过质量门槛**——自测不是质量证据 |
| `style` 真盲排 | ⚠️ **未做三选一盲辨**（同族自测无独立评分 Agent 指认）；style-decoys.md 已就绪，待独立评分 Agent 跑 |
| cross-review ≥95/A | ❌ **未达**（自测非独立复评，不得宣称） |
| 跨模型 / 人类复评 | **未做**，不外推 |

**结论**：验收标准 3 要求的「cross-review ≥95/A、盲读辨识 ≥2/3」目前**无独立评分 Agent 背书**，
本卡只提供了可运行的预设与诚实的自测占位。对外质量认证**空缺**，待独立评分 Agent（跨模型/人类）复评。
这一诚实边界与本项目 Phase 4b「同族 LLM、标质量下限、不外推」的纪律一致。
