# reference · 长内容与音视频素材管线

> 素材超过 5 万字、或素材是视频/播客/访谈音频时，先走这条管线，再进入阶段 0。
> 除 `fetch-subtitle --execute`（本包唯一联网动作，默认 dry-run）外，全部命令**离线**。
> `video-understand` 连联网能力都没有——它只生成「授权前披露单」（见 3.6）。

---

## 一、为什么必须先分块

| 不分块 | 分块 + 索引 |
|---|---|
| 整本进上下文，超限就截断，尾部内容**从未被看过** | 按索引只取相关块 |
| 每次重跑都重新读全文，重复烧 token | sha256 缓存命中即跳过重算 |
| 无法回答"这个结论出自哪一章" | 每块带 `heading_path`，可回溯 |

实测口径见 `examples/walkthrough.md` 第 3 步。

---

## 二、书籍 / 长文

```bash
td.py chunk  book.md --max-chars 4000          # 产物：book.md.td/{document.json,chunks.jsonl,index.json}
td.py index  book.md.td --grep "主要矛盾"       # 只把命中块的原文喂给提取 Agent
td.py chunk  book.md                           # 第二次运行：命中缓存，秒回
```

**产物结构**

| 文件 | 用途 |
|---|---|
| `document.json` | SourceDocument：elements + heading_path + char 区间 |
| `chunks.jsonl` | 每行一个块：`chunk_id / heading_path / chars / text` |
| `index.json` | 标题树 → chunk 映射，供 `--grep` 检索 |
| `.cache.json` | 源文件 sha256 + 分块参数，命中即跳过 |

**给 Agent 的指令模板**

```
先用 `td.py index <sidecar> --grep "<关键词>"` 定位相关块，
再只读这些块的原文（用 `preview` 或直接读 chunks.jsonl 对应行），
不要把整本书读进上下文。
```

---

## 三、视频 / 播客 / 访谈

### 3.1 拿到字幕文件（四条路）

```bash
# ① 本技能内置（唯一联网命令，默认 dry-run，加 --execute 才真下）
td.py fetch-subtitle "<URL>" --out subs/                 # 打印命令，不执行
td.py fetch-subtitle "<URL>" --out subs/ --execute      # 真正下载
td.py fetch-subtitle "<URL>" --out subs/ --execute --cookies cookies.txt   # 需登录的视频
```

**相对 nuwa `download_subtitles.sh` 修掉的三个缺陷**

| nuwa 的问题 | 本实现 |
|---|---|
| `find -newer /tmp/.ytdlp_marker` 判断人工字幕，但该 marker **全文从未被 touch** → 检测恒假，人工字幕识别静默失效 | marker 建在 `--out` 目录内并真实写入，重复下载直接命中缓存并提示 |
| 隐式联网，出错只抛 yt-dlp 原始输出 | **默认 dry-run**；`--execute` 才联网；失败给中文可执行提示（含 cookies 建议） |
| 状态写在固定 `/tmp`，多项目并行互相污染 | 全部状态落在 `--out` 目录内 |

**其余三条路（完全离线）**

| 方式 | 说明 |
|---|---|
| 视频站点自带字幕 | 手动下载 .srt / .vtt |
| `ffmpeg -i input.mp4 output.srt` | 本地转写，无需联网 |
| ASR 工具 / 用户直接提供文稿 | 导出或直接给 SRT |

### 3.2 转成逐字稿

```bash
td.py transcript talk.srt                          # → talk.transcript.md / .json
td.py transcript ep1.srt ep2.srt --merge --out series   # 多集合并（自然序）
td.py transcript ep2.srt --offset 3720             # 第二集接在 62 分钟处
```

**做了什么**

| 步骤 | 说明 |
|---|---|
| 解析 | SRT 与 WebVTT 通吃，时间戳精确到毫秒 |
| 去重 | 字幕滚动会把同一句显示 2–3 次，按归一化相邻去重（阈值 0.86） |
| 成段 | 间隔 < `--gap`（默认 2.5s）且未超 `--max-chars` 的短 cue 合并为一段 |
| 过滤 | 纯符号行、`[音乐]` 一类短括注行 |
| 说话人 | `张三：` 前缀识别为 speaker，渲染为 `**张三**：` |

**产物**：`[HH:MM:SS.ss] 正文` 格式的逐字稿，时间戳直接用于能力卡的 `source_locator`。

### 3.3 逐字稿同样要分块

```bash
td.py chunk talk.transcript.md --source-id transcript
```

逐字稿是长文，**同样适用**索引检索，不要整份灌入。

### 3.4 字幕的固有风险

| 风险 | 表现 | 应对 |
|---|---|---|
| 同音错字 | 人名/术语错 | 关键引语必须回听核对；FIDELITY 维度 4 扣分 |
| 断句错 | 一句被拆到两段 | 调大 `--gap` |
| 说话人未标注 | 无法区分提问者与回答者 | 合并时人工补 `名字：` 前缀 |
| 多集重叠 | 合并后时间戳错位 | 用 `--offset` 校正 |
| AI 观察混入语料 | 画面描述被当成「他说过的话」，anchor 假绿 | 见 3.5 素材三层；`lint-quotes` 硬失败 |

### 3.5 素材三层：可核原文 ≠ AI 观察（**机械隔离**）

> 2026-11-06 增。背景：仓颉 3.0 的 `video-downloader` 用 LongCat / 豆包做视觉理解，
> 产出「口播 + 画面 + 时间戳」的多模态稿。它已经做对了一半——把 `transcript.txt`
> （纯音频原文）与 `visual_notes.jsonl`（可见事实、屏幕文字、动作）**分开存放**。
> rulai 不 vendor 这个工具（见 3.6），但必须吸收这条设计，并加一道机械规矩。

| 层 | 值 | 是什么 | 能否作引语出处 / `--corpus` |
|---|---|---|---|
| **L1 可核原文** | `verbatim` | 平台字幕、本地 ASR 逐字稿、用户手抄原文；带时间戳 | ✅ **唯一允许**。`source_locator` 只能指向这一层 |
| **L2 AI 观察** | `ai-observation` | 视觉理解稿、画面描述、屏幕文字归纳、OCR 摘要；是模型对画面的**理解性复述**，不是「视频里说过的话」 | ❌ **禁止**。`lint-quotes` 硬失败（exit 1） |
| **L3 用户提供/推断** | `user-supplied` | 人工笔记、通法、本卡规则 | ⚠️ 不自动算原文；按「来源状态」逐条标 `[原文]/[通法]/[本卡规则]` |

**为什么必须机械隔离**：`verify-quotes` / `anchor` / `lint-quotes` 的判定都是
「逐字去语料里找，找到才算命中」。若把 L2 混进 `--corpus`，anchor 会把 AI 生成的句子
当成已核实原文，产出**假 ANCHOR_HIT**——核验链从源头就断了，而且显示为绿。
这与 #77（无出处的词被伪装成核实过的）是同一类事故，更隐蔽：这次连「原文」本身
都是模型编的。靠文档叮嘱挡不住，必须让体检器在锚定之前就红。

**标记约定（机器可扫）**：任何 L2 产物**必须**在文件开头带一行：

```text
<!-- RULAI_LAYER: ai-observation | 禁止作为可核原文 / 引语出处 -->
```

JSONL 也可每行带 `"layer": "ai-observation"`。文件名兜底：`*.visual-notes.jsonl` /
`*.ai-transcript.md` / `*.vision.md` / `multimodal-transcript*`，漏写标记也判 L2。

```bash
td.py lint-quotes <card> --corpus transcript.md          # L1：正常体检
td.py lint-quotes <card> --corpus visual-notes.jsonl     # L2：❌ 硬失败，exit 1
```

`lint-quotes` 检查三处：传入的 `--corpus` 正文标记、语料文件名、卡片自身的
`source_locator` 是否指向 L2 产物。命中即判 `verdict=fail`，并给可执行的改法。
正向 / 负向 / 文件名兜底 / JSONL 四态都有回归（`t_layer_isolation_lint_quotes`）。

**已知边界（别写成「已全面拦截」）**：本轮只在 `lint-quotes` 落地硬失败；
绕过体检器直接跑 `anchor` / `verify-quotes` 仍会把 L2 当语料。未带约定标记、
文件名也随意的 AI 生成文本，工具无从分辨。把守卫扩展到这两个核验器属 P2。

### 3.6 视频理解：外部引擎与「授权前披露单」

> 2026-11-06 增。仓颉 3.0 的 `video-downloader`（独立仓库
> `kangarooking-skills/video-downloader`）用 LongCat-2.5 / 豆包做视觉理解。
> 软件教程、板书公式、PPT 架构图这类**信息在画面里**的素材，光听音频确实会丢内容；
> 这是 rulai 目前的真缺口（无自有 ASR、无视觉理解、无多模态逐字稿）。

**不 vendor，只引用**：`kangarooking-skills` 仓库顶层无 LICENSE（默认版权），
其视频号 provider 依赖 `ltaoo/wx_channels_download`（MIT + Commons Clause）。
所以 rulai 不收编其代码，只把它列为**用户自行安装的外部可选工具**。
本包提供的是 `td.py video-understand`——一份**授权前披露单**：

```bash
td.py video-understand talk.mp4 --duration-seconds 2700          # 打印披露单，零网络
td.py video-understand talk.mp4 --duration-seconds 2700 --json-out plan.json
td.py video-understand talk.mp4 --upload-to none --engine none    # 纯本地路线的披露
td.py video-understand talk.mp4 --execute                        # 无此参数，命令拒绝
```

| 做 | 不做 |
|---|---|
| 读取本地文件大小、打印将被上传的目标与体积 | ❌ 不上传、不联网、不读取视频内容 |
| 披露第三方托管风险、引擎与端点、单价口径 | ❌ 不调用任何视觉引擎、不探测网络 |
| 按显式假设常量给出 token / 费用**规划估算** | ❌ 不给报价（单帧消耗与截断行为均未实测） |
| 打印 L1/L2/L3 分层契约（L2 必须带标记） | ❌ 不产出多模态逐字稿 |
| `--json-out` 落一份可留证的本地 JSON | ❌ 不提供 `--execute`（上传必须是人显式做的一次性动作） |

**三条必须先读的披露**

1. **隐私**：LongCat / 豆包的 `video_url` 只收**公网 URL**，本地文件必须先传到第三方。
   文章作者用的 Uguu 临时公网托管**约 3 小时自动过期、期间任何拿到链接的人可访问、
   无法提前删除**。私有 / 涉密 / 未授权素材禁止走这条路；完全不出机器请走
   `--engine none` + 本地 Whisper / 平台字幕（3.1）。
2. **成本口径不一致**：官方 API 文档 2026-11 查得 ¥2/M 输入 · ¥8/M 输出 · ¥0.04/M
   缓存命中；社区文章按 755 万 token ≈ ¥23 反推约 ¥3/M。**两者不一致、均未复核账单**，
   用 `--price-in / --price-out / --price-cache` 覆盖。估算里的单帧 / 单段 token 假设
   见 `scripts/tdlib/videounderstand.py`，全部**未实测**。
3. **分层**：视觉理解稿一律属 L2，产物必须带 `RULAI_LAYER: ai-observation` 标记
   （见 3.5），**禁作引语出处 / `--corpus`**，`lint-quotes` 会硬失败。

零网络不是承诺而是可机械验证的性质：回归 `t_video_understand_zero_network`
用 AST 钉住该模块不含任何网络导入或子进程调用，并验证相同输入两次输出完全一致。

---

## 四、人物素材：六路调研

```bash
td.py research init <bundle-dir> --person "某人"
# → references/research/01-writings.md … 06-timeline.md

td.py research merge references/research/*.md --out references/research-merged.md
```

| 编号 | 车道 | 为什么不能省 |
|---|---|---|
| 01 | writings 本人著作 | 判断他主动主张了什么 |
| 02 | conversations 访谈/演讲 | 长对话暴露推理过程与退让 |
| 03 | expression-dna 表达样本 | ≥800 字原话，供风格辨识度评测 |
| 04 | **external-views 外部评价** | 没有外部视角就发现不了自我认知与实际的落差 |
| 05 | decisions 关键决策 | 决策 + **事后反思** 才是认知，不然只是履历 |
| 06 | timeline 时间线 | 立场转折点解释了为什么现在这样想 |

**合并器的三个动作**

1. 归一化后按 3-gram Jaccard 去重（只看**命题**，出处写法不同不影响判定）
2. 同一命题的**冲突表述**打 `⚠️ 冲突` 标记，交人工判断，不静默取先到
3. 产出一手/二手占比；**<70% 时 FIDELITY 维度 4 扣分**，且不得宣称"基于原始素材"

---

## 五、发布前的一次体检（含 E4 对照）

**为什么要做 E4 对照**：不测的话，你无法区分"这张卡有用"与"基座模型本来就够强"。
孙子样本的实测结果就是最好的例子——不测就不知道 E4 只能算"边际增益"。

```bash
# 实验组与对照组各答同一道题
# 实验组：只给 SKILL.md；对照组：不给任何材料
# 评分：按 TRACE 5.3 的 E1/E2/E3/E5 四项量纲打分，判定显著/边际/无增益
```

**判定标准（先定死，跑完不改）**

| 结论 | 条件 |
|---|---|
| 显著增益 | 实验组在 ≥2 项明显优于对照，且省去关键提示工程 |
| 边际增益 | 仅格式/措辞改善，实质能力无差 |
| 无/负增益 | 对照已能做或更好 → E4 不得高于 2 分 |

详见 `examples/sample-bundle/eval/NO-SKILL-COMPARISON.md`。


```bash
td.py count <bundle-dir>          # 常驻发现成本 / 语料总量 / 最耗 token 的文件
td.py output-eval <card>          # 六段齐全性、引语数、完成标准、失败模式
td.py validate <bundle-dir>       # 阻断性问题清零
td.py gate <FIDELITY.md> --min B  # 非双 Agent 评测默认不放行
```

四项全绿再 `compile`。
