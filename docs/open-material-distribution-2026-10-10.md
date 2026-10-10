# 开放素材分布证据（2026-10-10）

对象：证明蒸馏管线**能消化多种开放公版素材**，而不是只在一本《論語》上成立。

为什么需要这份表：单一 exemplar 的说服力近乎为零——它证明的是"这套方法在这一种素材上跑通了"，
与"对所有素材都成立"之间隔着整个归纳问题。5 张卡覆盖 4 类文本形态，是这个归纳的第一份证据；
它**仍然不足以宣称普遍成立**，见文末边界。

## 一、五张卡 · 素材形态与规模分布

| 卡片 | 素材 | 文本形态 | 语料规模 | 卡片行数 | 卡片定位（一句话） |
|---|---|---|---:|---:|---|
| `lunyu-conduct` | 《論語》學而/為政/里仁/雍也/述而 | **语录体**（无叙事、句独立） | 5 段 / 5,947 字 | 211 | 观言行以识人 + 三省自修 |
| `tongjian-decision-trace` | 《資治通鑑》周紀卷1-5 | **编年叙事史**（事件链 + 臣光曰史论） | 147 段 / 59,206 字 | 326 | 读一项举措在秩序里激起的连锁后果 |
| `mengzi-refutation` | 《孟子》梁惠王/公孫丑/滕文公 | **对话体辩说**（王问孟答） | 38 段 / 14,642 字 | 315 | 用设问与取譬让对方自己走到结论 |
| `hanfei-upward-advice` | 《韓非子》說難/五蠹/顯學 | **论说体**（论证严密、无对话） | 36 段 / 9,113 字 | 353 | 权力不对等场景下进言的风险前置评估 |
| `xunzi-learning-order` | 《荀子·勸學篇》 | **论说体 · 短篇**（说理密集、篇幅小） | 13 段 / 2,430 字 | 247 | 学习的次第、积渐、专一与环境择取 |

合计 **239 段 / 91,338 字**；素材形态彼此不同（语录 / 编年叙事 / 对话 / 论说×2），
篇幅跨度 **2.4 千字 → 5.9 万字（24 倍）**。

## 二、机械核验实跑结果（`td.py anchor`）

| 卡片 | ANCHOR_HIT（锚定成功） | UNANCHORED（无段号标注） | 挂错段号 |
|---|---:|---:|---:|
| `lunyu-conduct` | 13 | 22 | **0** |
| `tongjian-decision-trace` | 69 | 0 | **0** |
| `mengzi-refutation` | 34 | 7 | **0** |
| `hanfei-upward-advice` | 86 | 6 | **0** |
| `xunzi-learning-order` | 94 | 0 | **0** |
| **合计** | **296** | **35** | **0** |

**引语密度差异很大**（每人/13 条 vs 每卡/94 条）——这不是哪张卡更好，
而是素材形态决定的：语录体天然短句密集、论说体长句少而长。
把它当成质量排序就读反了。

**UNANCHORED 不是"合格"而是"本命令无从核验"**：主要包括两类——
①作者的语言信号示例（"用户会怎么说"，本来就不是素材里的句子，如 hanfei 的 6 条）；
②作者未补段号的位置（工具会一并报出"在语料 §N 命中"，提示可补）。

### 口径变更说明（必须交代）

历史上本项目对 `lunyu-conduct` 声称的是「32 候选 / 12 条 ANCHOR_HIT」。
本表中的数字（13 / 22）与之不同，**原因是 #77/#78 修正了段号归属口径**，不是卡片变了：
新口径不再把"同行但不属于该段号的解释性引号串"算作引语，同时补认了 `第N段「…」`
这类写法。任何跨版本比较 anchor 数字时都要知道这一点。

## 三、可复跑

```bash
PY=python3   # 建议 /usr/bin/env python3 ≥3.10；本项目验证用 3.13.12
cd rulai-distill

# 逐张复跑段号锚定（括号内为期望结果）
$PY scripts/td.py anchor examples/open-bundle/skills/lunyu-conduct/SKILL.md \
    --corpus corpus/anchored/src-06-lunyu.md                                 # PASS 13 / 挂错 0
$PY scripts/td.py anchor examples/open-bundle/skills/tongjian-decision-trace/SKILL.md \
    --corpus corpus/anchored/src-01-tongjian-wei.md                          # PASS 69 / 挂错 0
$PY scripts/td.py anchor examples/open-bundle/skills/mengzi-refutation/SKILL.md \
    --corpus corpus/anchored/src-02-mengzi.md                                # PASS 34 / 挂错 0
$PY scripts/td.py anchor examples/open-bundle/skills/hanfei-upward-advice/SKILL.md \
    --corpus corpus/anchored/src-04-hanfeizi.md                              # PASS 86 / 挂错 0
$PY scripts/td.py anchor examples/open-bundle/skills/xunzi-learning-order/SKILL.md \
    --corpus corpus/anchored/src-07-xunzi.md                                 # PASS 94 / 挂错 0

$PY scripts/td.py validate examples/open-bundle         # error 0（六段齐全）
```

> **语料随本仓库分发**（`corpus/anchored/`），路径与卡片 `source_locator` 完全一致，
> 因此 clone 之后无需另外准备数据即可原样复算下面所有命令。

## 四、claim-level 来源状态分布（#75 机制）

| 卡片 | [原文] | [通法] | [本卡规则] |
|---|---:|---:|---:|
| `lunyu-conduct` | 2 | 3 | 2 |
| `tongjian-decision-trace` | 11 | 3 | 3 |
| `mengzi-refutation` | 11 | 2 | 3 |
| `hanfei-upward-advice` | 13 | 3 | 4 |
| `xunzi-learning-order` | 8 | 3 | 5 |

五张卡**全部**声明了来源状态区块（`validate` 要求：声明了就必须逐条标注，缺标签或自造标签 → error）。
这张表本身就是可读的结论：**每张卡都有 2–5 条"原文没有、卡片自加的操作约束"**——
它们被显式标出来了，而不是混在"古人的方法论"里冒充古人说的。

## 五、边界（这张表**不能**证明什么）

1. **5 张卡 ≠ 5 类验证。** 只有 `lunyu-conduct` 跑过独立交叉复核（95/A）；其余 4 张
   **只有机器核验**（引语锚定 + 六段齐全 + 用字一致），**没有 FIDELITY、没有独立评分、
   没有 no-skill 效用对照**。它们证明的是"管线跑得通且句句可核"，不是"卡片质量已被独立证实"。
2. **机械核验验不了"归属"。** anchor 证的是"这句确实在第 N 段"，不证"这句支持卡片那条论断"
   （参见 Uber Lilith 编造引语案）。引语存在 ≠ 引用得当。
3. **素材形态高度同源。** 5 张全都拆自维基文库的中文公版典籍、同一套 `corpus-anchor` 规整流程。
   换成视频逐字稿、英文素材、或排版糟糕的 PDF，这套沉淀未必成立——那是另一批实验。
4. **卡片是同期由同一套流程批量产出的**，不是跨时间、跨作者的独立产出；
   因此存在"同一批写法偏好"的系统性偏差（同一份撰写规范、同期产出）。

下一步该做的（按证据价值）：给其余 4 张补交叉复核 → 至少 1 张补效用对照 → 引入非典籍素材（视频/播客）。
