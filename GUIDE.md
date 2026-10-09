# 安装与使用指南

> 本文所有命令与输出都是**真实跑出来的**，不是手写的示例。
> 验证环境：macOS (arm64) + Python 3.13.12。

---

## 一、这是什么

把一本书 / 一个长视频 / 一个人物，**蒸馏成能被 AI 触发的技能**。
不是书摘，不是读后感——是「机器能执行的技能 + 能证明它没编」的质检链。

一句话用法：

```
「把这本书蒸馏成技能」                    # Agent 自己去读素材、走完七阶段
```

---

## 二、安装

### 方式 A：一条命令装进所有主流 Agent（推荐）

```bash
git clone https://github.com/yihexiang/rulai-distill.git
cd rulai-distill
./install.sh
```

它会把技能**符号链接**进下面这些目录（已存在的跳过，不覆盖别人的东西，重复跑幂等）：

| Agent | 读取路径 |
|---|---|
| Claude Code | `~/.claude/skills/` |
| **Codex CLI** | `~/.codex/skills/` |
| **通用总线**（Codex 主路径，其余 Agent 兜底） | `~/.agents/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Cursor（≥ 2.4） | `~/.cursor/skills/` |
| OpenCode | `~/.config/opencode/skills/` |
| OpenClaw | `~/.openclaw/skills/` |
| Hermes | `~/.hermes/skills/` |
| WorkBuddy | `~/.workbuddy/skills/` |

常用参数：

```bash
./install.sh --list        # 只看会装哪些目录，不做改动
./install.sh --copy        # 实体复制（Windows / 不支持符号链接的环境）
./install.sh --project /path/to/your/repo   # 额外装成某个项目的项目级技能
./install.sh --uninstall   # 卸载全部
```

> ⚠️ `--project` **不能指向本仓库自己**——那会建出自引用符号链接，
> 让 `rglob` 无限递归。脚本会直接拒绝并说明。

### 手动安装（不想跑脚本的话）

本质就是**把目录放进对应路径**，Agent 会自己发现：

```bash
git clone https://github.com/yihexiang/rulai-distill.git \
  ~/.codex/skills/rulai-distill        # 换个目录名就是换个 Agent
```

### 为什么能跨 Agent：格式是开放标准

`SKILL.md` 不是某家的私有格式——Anthropic 2025-10 发布后已捐给 Linux Foundation，
是**公开规范**（<https://agentskills.io/specification>）。各家Agent 只是**读取路径不同**，
文件本身不用改。本包frontmatter 已按规范校验：

| 规范要求 | 本包 | 
|---|---|
| `name` ≤ 64 字符、小写字母/数字/连字符、**与目录同名** | `rulai-distill`✅ |
| `description` ≤ 1024 字符 | 378 字符 ✅ |
| 不得含 XML 尖括号（会被注入 system prompt） | 无 ✅ |
| 正文 < 500 行 | 274 行 ✅ |
| 可选 `license` / `compatibility` | 已填 ✅ |

### 关于 DeepSeek：它是模型，不是 Agent

DeepSeek 是**模型 API**，本身没有「技能目录」这种概念。
真正能装技能的是**跑模型的 Agent 程序**——比如 Hermes（你本机就装了）、
Codex CLI、Claude Code、OpenCode。

所以正确说法是：**任何以 DeepSeek 为后端的 Agent，都能用这个技能**，
只要它读 `SKILL.md`。你本机的 `~/.hermes/skills/` 已经有 27 个技能了，
`./install.sh` 会直接把它装进去。

### 方式 B：只当命令行工具用

```bash
git clone https://github.com/yihexiang/rulai-distill.git && cd rulai-distill
python3 scripts/td.py doctor        # 立刻能看到能力矩阵
```

本文后面的命令都假设你在仓库根目录，且用 `python3` 代指你的解释器
（Windows 把 `python3` 换成 `python`）。

### 可选依赖（装不装都能跑）

| 依赖 | 授权 | 不装的后果 |
|---|---|---|
| PyYAML | MIT | 用内置的最小 YAML 解析器，frontmatter 校验略宽松 |
| tiktoken | MIT | token 计量改为字符估算，**数值偏低** |
| jsonschema | MIT | 用内置子集校验器（覆盖 required/enum/const/pattern/type） |

```bash
python3 -m pip install pyyaml tiktoken jsonschema   # 想装全就一条
```

### 验证安装

```bash
python3 scripts/td.py doctor
```

真实输出（截取）：

```
td.py v1.6.0 · rulai-distill 环境自检

✅ Python 3.13.12（要求 ≥3.10）
⚠️  PyYAML（严格 frontmatter 解析） 缺失 —— 已降级，功能不受阻
⚠️  tiktoken（精确 token 计量） 缺失 —— 已降级，功能不受阻
✅ methodology/ 就绪（6 个文件）
✅ templates/ 就绪（5 个文件）
✅ schemas/ 就绪（8 个文件）
✅ 5 个核心模板齐全

能力矩阵（对齐三个来源技能）
──────────────
   长内容分块 / 索引 / 缓存      ← cangjie build_chunks + build_index
   ...
🎉 可以开始蒸馏。
下一步：python3 scripts/td.py init my-bundle
```

看到 `🎉 可以开始蒸馏` 就说明装好了。**顺手确认一下版本号对得上**——
`doctor` 打印的版本就是 `SKILL.md` 里的版本，测试会强制它们一致。

### 升级与卸载

```bash
# 升级
cd ~/.workbuddy/skills/rulai-distill && git pull

# 改完开发目录后，同步到已安装副本（否则你测的不是实际加载的那份）
rsync -a --delete /path/to/rulai-distill/ ~/.workbuddy/skills/rulai-distill/

# 卸载
rm -rf ~/.workbuddy/skills/rulai-distill
```

> ⚠️ **开发目录 ≠ 运行目录**。技能被调用时加载的是 `~/.workbuddy/skills/` 下那份，
> 不是你的项目目录。改完不同步，测试全绿但功能没生效——本包有一条测试专门守这个。

---

## 三、第一次跑通（真实流程）

下面每一步的输出都是从真实运行里摘的。

### Step 0 · 自检

```bash
python3 scripts/td.py doctor
```

### Step 1 · 生成骨架

```bash
python3 scripts/td.py init my-book
```

```
✅ 已生成 bundle 骨架：/tmp/demo/my-book
   bundle.json      ← 改 source / skills
   skills/*.md      ← 能力卡，按templates/CAPABILITY.md.template 写
   references/research/  ← 六路调研骨架 6 个（书籍蒸馏可删）
   SOURCES.md       ← 素材清单 + 一手来源占比
   fidelity/        ← 可放 <slug>.json 形式的质检报告
   下一步：python3 scripts/td.py validate /tmp/demo/my-book
```

生成的结构：

```
my-book/
├── bundle.json
├── SOURCES.md
├── skills/example-capability.md
└── references/research/01..06-*.md
```

### Step 2 · 长内容分块 + 检索

素材超过 5 万字**必须**先分块。

```bash
python3 scripts/td.py chunk sample.md --max-chars 4000
```

```
分块 · sample.md
──────────────
✅ 3 块 / 6 elements / 平均 45 字符
   产物目录：sample.md.td
   最大块 48 字符（上限 4000）
   下一步：td.py index sample.md.td --grep <关键词>
```

产物目录里的 `chunks.jsonl` 每行一个块，`index.json` 是标题树。

**检索（标题 + 正文都搜）：**

```bash
python3 scripts/td.py index sample.md.td --grep "分块"
```

```
✅ 命中 2 块（关键词：分块）
     ck-0000  48c  第一章 主题
     ck-0002  43c  第一章 主题 / 1.2 小节
```

> 只能给目录；要按段号取带时间戳的邻接块用 `lexindex`（SQLite FTS5 + 中文 bigram）。

### Step 3 · 写能力卡

按 `templates/CAPABILITY.md.template` 写 `my-book/skills/*.md`。
模板里六段结构是硬要求，`validate` 会逐段查。

### Step 4 · 静态校验

```bash
python3 scripts/td.py validate my-book
```

```
🔍 校验：my-book

✅ 无问题
统计：技能卡 1 / 文档 7 · error 0 / warn 0
```

### Step 5 · 出厂质检（这一步是本项目的重点）

```bash
python3 scripts/td.py gate <FIDELITY报告.md>
```

**门禁默认会拒绝放行**，这不是坏了：

```
compile
────────
❌ [example-capability] 缺少 FIDELITY 报告且未给 fidelity_score
   → 先跑阶段 4b 生成 /tmp/demo/my-book/skills/FIDELITY.md
   → 或临时应急：python3 scripts/td.py compile ... --force
```

`compile` 真实退出码 **1**（拒绝）。`gate` 报告不存在也是 **1**，`overlap` 检出重叠也是 **1**。

> `--force` 只在临时应急时用，它会留痕（写进 manifest）。

### Step 6 · 决定输出形态并发布

```bash
python3 scripts/td.py strategy my-book --purpose workflow
```

```
✅ 推荐形态：pack   （0 晋级 / 1 路由 / 共 1）
   · 用户目的为 workflow → pack
   备选：single（1 个路由入口 + 0 张能力卡）
   决策记录：my-book/output-decision.json
```

```bash
python3 scripts/td.py compile my-book --out ~/skills/my-bundle
```

发布是**原子**的：先写临时目录、校验通过才切换，失败不留半成品。
配套有 `snapshot`（建快照）和 `rollback`（回滚）。

### Step 7 · 触发压力测试

技能写完了，得测「AI 到底会不会被它触发」。

```bash
S=~/skills/my-bundle/trigger
# ① 从 bundle 生成触发测试套件骨架
python3 scripts/td.py trigger build my-bundle --out $S

# ② 固定种子切 train / validation（种子固定 → 结果可复现）
python3 scripts/td.py trigger split $S --seed 42 --out $S

# ③ 生成盲测任务包（**不含** expect/why，防止泄漏答案）
python3 scripts/td.py trigger prepare $S --out $S/blind --set all

# ④ 生成待答问卷，交给另一个 Agent 作答
python3 scripts/td.py trigger record $S --out $S/answers.md --set all

# ⑤ 机械判分，输出 P / R / F1
python3 scripts/td.py trigger score $S $S/answers.md --out $S/score.json
```

> ③ 刻意不含答案，是为了让被测 Agent 看不到「标准答案」。
> 真正想让它答题时，另开一个干净的会话，把 `blind/` 里的任务给它作答。

---

## 四、按素材类型走三条路

### 书籍 / 长文

```
init → chunk → index → 写卡 → validate → gate → strategy → compile
```

### 音视频 / 播客

字幕获取是本包**唯一联网**的命令，且**默认 dry-run**，不加 `--execute` 绝不下载：

```bash
python3 scripts/td.py fetch-subtitle "<视频URL>" --out subs/
```

```
字幕获取（本包唯一联网命令，默认 dry-run）
─────────────────────────
   将执行（这是本包唯一会联网的命令）：
     yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs zh-Hans,zh-Hant,zh,en ...
   加 --execute 才会真正下载。字幕拿到后：td.py transcript <file.srt>

⚠️  未执行：加 --execute 才会真正下载
```

需要 `yt-dlp`。中文站点若需登录态，可加 `--cookies <cookies.txt>`；网络不走代理时加 `--no-proxy`。

拿到字幕后转逐字稿：

```bash
python3 scripts/td.py transcript subs/<id>.srt --out subs/<id>
```

```
字幕 → 逐字稿（离线，不下载）
────────────────
✅ 2 cues → 1 段（去重丢弃 0）
   时长 8s
   subs/id.transcript.md
   下一步：td.py chunk <逐字稿.md> --source-id transcript
```

> ⚠️ **`--out` 是文件前缀**，不是完整文件名。给`subs/id` 会写出
> `subs/id.transcript.md` **和** `subs/id.transcript.json` 两个文件。

多字幕合并（同一场访谈的不同语言版本）：

```bash
python3 scripts/td.py transcript zh.srt en.srt --merge --out merged
```

逐字稿再交给 `chunk --source-id transcript`，段落会保留 `[时间戳]`，
供后面的 `anchor` 做段号锚定。

### 人物

```bash
python3 scripts/td.py research init my-person --person "马斯克"
# 填 01-writings / 02-conversations / 03-expression-dna /
#     04-external-views / 05-decisions / 06-timeline

python3 scripts/td.py research merge my-person/references/research/*.md \
  --out my-person/references/research-merged.md
```

`merge` 遇到**互相矛盾的一手材料不会静默取先到**，会标出来让你裁决。

---

## 五、质检工具箱（本项目与普通「拆书工具」的区别）

| 命令 | 解决什么问题 | 什么时候用 |
|---|---|---|
| `verify-quotes <卡片> <语料>` | 卡片里的引语**是不是真的存在于语料中** | 每张含引语的卡必跑 |
| `anchor <卡片> --corpus <语料…>` | 引语**是不是真在它声明的 §N 段里** | 人物卡 / 逐字稿类素材；书类素材亦支持（语料用 `【第N段】`，卡片用 `> 「引语」` + `> —— 《书》第N段`） |
| `corpus-anchor <书类原文> -o <out>` | 把书类原文规整成 anchor 可读的 `【第N段】` 形式 | 书类素材做段号锚定前 |
| `lint-quotes <卡片> --corpus <语料…>` | 核验前的**体检**：简繁不一致（确证判失败）/ 省略号 / 归属可疑（提示级） | 写卡时与发布前 |
| `audit-coverage` | 穷举语料，列出**卡片完全没覆盖的段落** | 判断覆盖率是否吹过头 |
| `overlap --new A --old B` | 证明两批素材**零重叠** | 换素材重蒸馏前 |
| `output-eval <卡片>` | 六段结构 / 引语数 / 规模体检 | 发布前 |
| `cross-review <scores>` | 多个独立评分 Agent 的**分差**门禁 | 评分环节 |
| `eval-kit init` / `check` | 把独立质检闭环产品化：题库 / 答题+评分模板 / JSON 回传 / 分差门禁 → 产出 FIDELITY JSON | 每张卡做出厂质检时（`gate` 默认要求 ≥2 评分者的交叉复核记录） |

### 为什么 `anchor` 是必需的

机械核验**只能验「存在」，验不了「归属」**。
本项目真实的翻车案例：我写下「§232 提到 `except with Uber`」，
它确实逐字存在于语料——所以 `verify-quotes` 判PASS。
但真正在§233 的是 `except with Uber Lilith`，那是《暗黑破坏神》的一个 boss，
接着上一段游戏话题的玩笑。**一条伪造的引用通过了全部机械核验。**

所以凡是引语挂到段号的卡片，都要用 `anchor` 再验一遍归属。

### 换素材重蒸馏：先证明零重叠

```bash
python3 scripts/td.py overlap --new 新语料.md --old 旧语料.md
```

- 8-gram 词级包含率 > 0.5% → 判 FAIL，退出码 **1**
- 出现**整句重复** → 判 FAIL
- 两层防护是独立的：无标点语料切不出句子，但包含率仍会兜住

实测（真实数据）：Qatar 论坛逐字稿 vs 17,144 条推文 → 包含率 **0.0000%**，PASS。

---

## 六、命令速查

| 命令 | 作用 |
|---|---|
| `doctor` | 环境自检 + 能力矩阵 |
| `init [--person P] DIR` | 生成 bundle 骨架 |
| `chunk SRC [--max-chars N] [--source-id S]` | 结构感知分块（+索引+缓存） |
| `index SIDECAR [--grep K]` | 检索块（标题 ∪ 正文） |
| `lexindex` | SQLite FTS5 词法索引 / 查询（含邻接块） |
| `preview SIDECAR` | 预览分块 |
| `transcript IN… [--merge] [--out PREFIX]` | SRT/VTT → 带时间戳逐字稿（离线） |
| `research init DIR` / `research merge FILES… --out F` | 六路调研骨架 / 合并去重+冲突标记 |
| `validate PATH` | 静态校验 |
| `gate REPORT [--min A\|B\|C\|D]` | FIDELITY 门槛判定 |
| `cross-review SCORES [--threshold N]` | 多评分 Agent 分差门禁 |
| `anchor CARD --corpus C…` | 引语段号锚定 |
| `overlap --new A --old B` | 素材零重叠证明 |
| `strategy PATH [--purpose …]` | 输出形态决策 single/pack |
| `compile BUNDLE --out DIR` | 原子发布 |
| `snapshot` / `rollback` | 建快照 / 回滚 |
| `trigger build BUNDLE --out S` | 生成触发测试套件 |
| `trigger split SUITE --seed N` | 固定种子切 train/validation |
| `trigger prepare SUITE --out D --set all` | 生成盲测任务包（不含答案） |
| `trigger record SUITE --out F --set all` | 生成待答问卷 |
| `trigger score SUITE ANSWERS` | 机械判分，输出 P/R/F1 |
| `output-eval CARD` | 产物机械体检 |
| `verify-quotes CARD CORPUS` | 引语存在性核验 |
| `audit-coverage` | 未覆盖段落审计 |
| `count PATH` | token 计量（**PATH 可以是单个文件**） |
| `bench PATH` | 重复计时 |
| `diff` / `impact` / `repair` / `patch` / `update` | 增量维护（写操作默认 dry-run） |
| `prompt SRC [--mode entry\|inline\|cards]` | 编译成单文件 prompt |
| `schema NAME` / `contract` / `failure` | 打印内置 schema / 上游契约 / 失败用例集 |
| `upstream list / run` | 直通内置上游（cangjie）实现 |
| `fetch-subtitle URL --out DIR` | **唯一联网命令**，默认 dry-run |

每个命令都有 `--help`。

---

## 七、故障排查

| 你看到的 | 真实原因 | 怎么办 |
|---|---|---|
| `缺少 FIDELITY 报告且未给 fidelity_score` | 没跑质检就想发布 | 跑 `gate`；应急才用 `compile --force`（会留痕） |
| `gate` 判 `fallback-self` | 评分模式是「自测」——**自己给自己打分不算通过**（这是设计） | 换一个独立 Agent 评分，把报告放进 `fidelity/` 再 gate |
| `未找到 index：xxx/index.json` | 还没分块 | 先跑 `chunk` |
| doctor 报 PyYAML / tiktoken 缺失 | 没装可选依赖 | 正常降级；要精确 token 就 `pip install tiktoken` |
| `不能使用他人发送的代码`（GitHub 授权页） | 设备码是别人终端里的 | 只能输入**你自己终端** `gh auth login` 打印的码 |
| 改了代码但行为没变 | 加载的是 `~/.workbuddy/skills/` 那份 | `rsync -a --delete` 同步；本包有测试专门守这条 |

---

## 八、已知限制（诚实声明）

1. **本项目处于 beta。** 机械可靠性已验证（89 项回归），
   但**它蒸馏产出的卡片尚未达到可发布质量**——这是两件不同的事，别混为一谈。
2. **FIDELITY 的「答题」侧还没完全隔离。** 独立**评分** Agent 已验证有效，
   独立**答题** Agent 尚未跑通，因此「答题者≠作者」目前只在评分侧成立。
3. **只有 `fetch-subtitle` 联网**，其余全部本地离线。
4. **`anchor` 原生支持两类段号标记**：视频/播客的 `[时间戳]` 与书类的
   `【第N段】`/`【第N条】`。书类语料先用 `td.py corpus-anchor` 规整成 `【第N段】` 形式，
   书类卡用 `> 「引语」` + `> —— 《书名》第N段` 写法即可被段号锚定。两者都会显式报错
   （而非静默 0 段）当语料无任何段号标记时。
5. **不做**：书摘、读后感、单纯摘要、模仿作者语气。

---

## 九、许可与署名

本包 MIT。内置了 `kangarooking/cangjie-skill` 的部分文件（MIT，原样保留 +
逐文件登记在 [`NOTICE`](./NOTICE) 与 [`scripts/vendor/PROVENANCE.md`](./scripts/vendor/PROVENANCE.md)）；
另两个来源（`alchaincyf/nuwa-skill`、`Yeadon8888/cangjie-skill`，同为 MIT）
只借鉴方法论、**未内置代码**。`scripts/vendor/VENDOR.sha256` 由 CI 强制校验，
确保上游文件未被改动。