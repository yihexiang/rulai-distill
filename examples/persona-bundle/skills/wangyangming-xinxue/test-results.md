# test-results · wangyangming-xinxue

> 全部命令在仓库根 `/Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill` 下执行，
> 用托管 Python：`/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3`
> （系统 `/usr/bin/python3` 是 3.9.6，跑不了本项目）。
> 以下输出为 **2026-10-14 实跑结果**，不是建卡时的估计。

## 一、机械自验（实测）

| 命令 | 结果 |
|---|---|
| `td.py validate` | **error 0 / warn 0** |
| `td.py anchor`（双 corpus） | **68 条引语，锚定命中 68，未标注段号 0 → PASS** |
| `td.py lint-quotes` | 检查 57 条；**未发现用字不一致（简繁/异体）**；无省略号节引 |

`anchor` 实测输出：

```
引语 68 条：锚定命中 68，未标注段号 0
判定明细：{'ANCHOR_HIT': 68}
抽取：候选 77 = 认出 68 + 噪声 1 + 中文太短跳过 8（自检 True）
   其中短引语（<8 汉字、逐字见于语料、同行带 §N）已纳入核验并命中 12 条
✅ 判定 PASS：68 条带段号标注的引语全部锚定在声明的段号内
```

复跑命令：

```bash
P=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
CARD=examples/persona-bundle/skills/wangyangming-xinxue/SKILL.md

$P scripts/td.py validate $CARD
$P scripts/td.py anchor $CARD \
    --corpus corpus/anchored/src-10-chuanxilu.md \
             corpus/anchored/src-13-mingshi-wangshouren.md
$P scripts/td.py lint-quotes $CARD
```

## 二、`verify-quotes` 对本卡**不适用**——这条必须写清楚，不能 silent

实测：

```
$P scripts/td.py verify-quotes $CARD corpus/anchored/src-10-chuanxilu.md
   引用 0 个（条目引用 0 + 时间戳 0 + 书类引用块 0）
   逐字引语核验 0 条 → 命中 0 条
❌ ⚠️ 空集假绿：卡片里含引语（「」/引号），但没有任何可识别的定位标记
```

**原因不是卡片没引语，是工具不认这种写法。** `verify-quotes` 认三种定位形态：
`【第N条】`、`[HH:MM:SS]` 时间戳、以及 `>` 引用块 + `—— 《书名》` 出处行。
本卡用行内 `（src-10 §6）` 标注（**因为有两份语料，必须标出归属**），三种形态都不匹配。

**本卡的核验改由 `anchor` 承担，且判据更强**：

| 工具 | 验什么 | 本卡 |
|---|---|---|
| `verify-quotes` | 引语在语料里**存在**吗 | ❌ 不适用（格式不认，返回 0 条） |
| `anchor` | 引语在**它声明的那一段**里吗 | ✅ 68/68 PASS，且支持多语料 |

只验"存在"不验"归属"正是 C10 要防的；`anchor` 验的是更强的那一层。
**但"0 条核验"绝不能被当成"0 条问题"**——所以这里显式写明，并已登记为缺陷 **#84**。

## 三、表达 DNA 量化（B4，实测）

```bash
$P benchmarks/expression-dna/measure.py \
   --corpus corpus/anchored/src-10-chuanxilu.md --speaker-only 先生曰
```

实测：

| 指标 | 值 |
|---|---|
| 说话人过滤 | `先生曰`（只取 203 段／389 段正文，43,790 字） |
| 句均长 | **19.8 字**（标准差 11.2，最长 90 字，共 2,104 句） |
| 转折词密度 | **7.22 次/千字**（然×177、雖×55、但×53） |
| 确定性比值 | **3.07**（绝对 11.42／存疑 3.72，每千字）→ 判「很明显」型 |
| 自称密度 | 3.06 次/千字 |
| 引经典 Top3 | 《大學》×14、《書》×12、《易》×12 |
| 高频实词 | 聖人×120、天理×106、良知×105、本體×74、用功×55、格物×52 |
| 幽默 | **机械不可判**（脚本明示 `machine_judgable: false`），人工判为**讽刺型** |

三人对照（同一脚本、同一口径）：

```bash
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
> 上表取两语料 `--merge` 后的 4,138 字。这不是缺陷，是脚本的设计行为——
> 小样本上给句长与词频就是假精确。

## 四、建卡过程中被工具抓出并已修的问题（留痕）

建卡自验不是一次通过的，`anchor` 与 `lint-quotes` 各抓到真问题：

| 工具 | 抓到什么 | 怎么修 |
|---|---|---|
| `anchor` | **1 条 `NOT_IN_CORPUS`**：「这一念里有没有私意掺着」标了 §6，但它是**本卡规则的举例**，语料里没有 | 去掉引号与段号——它不是引语，不该挂段号 |
| `anchor` | **27 条 `UNANCHORED`**：本卡的规则表述、举例也用了「」，被当引语要求核验 | 非引语一律去引号改加粗；真引语补 `src-XX §N` |
| `anchor` | 3 条真引语因**段号离引语太远**（在行末或隔着别的引语）未被识别 | 段号紧跟各自引语 |
| `lint-quotes` | **5 处节引省略号**（`……`），非逐字原文 | 全部补全为完整原文，不用省略号 |
| `validate` | **warn**：人物卡未见过手来源权重声明 | 补「一手来源合计权重」分列表（1.0 / 0.0，不做加权平均） |

> 这一节是**故意留着的**：它说明"建卡自验全绿"通常不是一次就绿的，
> 把这些抓出来的过程写掉，下次就会有人相信"我写的时候都校验过了"。
> 同一教训见缺陷 #83（随包卡自陈与实跑不符）。

## 五、尚未运行（**不是"通过"，是没跑**）

| 项 | 状态 |
|---|---|
| FIDELITY 双 Agent 独立质检 | 套件已建（`eval/fidelity/wangyangming-xinxue/`），**评分未跑** |
| `style` 真盲排（对照样本盲辨） | `style-decoys.md` 随套件已生成，**盲排未跑** |
| cross-review ≥95/A | **未跑** |
| 跨模型 / 人类复评 | **未做**，不外推 |
