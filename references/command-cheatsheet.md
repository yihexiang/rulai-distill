# reference · 命令速查（22 个子命令）

> 全部命令纯本地、零网络。`td.py --help` 与各子命令 `--help` 是权威来源，本文是带场景的速查。

## 场景 → 命令

| 我要做什么 | 命令 |
|---|---|
| 确认环境与能力 | `td.py doctor` |
| 建一个新 bundle | `td.py init <dir> [--person 名字]` |
| 长书/长文分块 | `td.py chunk <src> --max-chars 4000` |
| 只取某几节原文（轻量，按标题路径） | `td.py index <sidecar> --grep "关键词"` |
| 深度检索（词法 + 邻接块，防断章取义） | `td.py lexindex <chunks.jsonl>` → `td.py lexindex --db <db> --query "…" --neighbors 1` |
| 看看切得对不对 | `td.py preview <sidecar>` |
| 取字幕（唯一联网，默认 dry-run） | `td.py fetch-subtitle <URL> --out <dir> [--execute --cookies f]` |
| 字幕 → 逐字稿 | `td.py transcript <srt…> [--merge --out]` |
| 人物六路调研骨架 | `td.py research init <dir> --person 名字` |
| 合并多路调研 | `td.py research merge <files…> --out merged.md` |
| 静态校验 | `td.py validate <dir>` |
| FIDELITY 门槛 | `td.py gate <report> [--min A\|B\|C\|D] [--allow-fallback]` |
| 该 single 还是 pack | `td.py strategy <bundle> [--purpose …] [--trigger-ready]` |
| 发布 | `td.py compile <bundle> --out <dir> [--mode pack\|single] [--force] [--overwrite]` |
| 手动存档点 | `td.py snapshot <dir> [--label "改前"]` |
| 回滚 | `td.py rollback <dir> --to <id>\|latest` |
| 生成触发测试 | `td.py trigger build <bundle> --out suite.json` |
| 切 train/validation（防过拟合） | `td.py trigger split <suite.json>` |
| 生成盲测包（不含答案） | `td.py trigger prepare <suite.json> --out <dir> [--set train\|validation]` |
| 生成待答问卷 | `td.py trigger record suite.json --out sheet.md` |
| 触发判分（容错 0） | `td.py trigger score suite.json answers.json` |
| 产物机械体检 | `td.py output-eval <card>` |
| token 计量 | `td.py count <dir>` |
| 重复计时 | `td.py bench <dir> --rounds 5` |
| 两版差异 | `td.py diff <bundleA> <bundleB>` |
| 改这张卡会影响谁 | `td.py impact <dir> <slug>` |
| 机械修复（默认 dry-run） | `td.py repair <dir> [--apply]` |
| 结构化补丁（默认 dry-run） | `td.py patch <card> <patch.json> [--apply]` |
| 重新校验并重编译（默认 dry-run） | `td.py update <bundle> --out <dir> [--apply]` |
| 压成单文件 prompt | `td.py prompt <src> [--mode entry\|inline\|cards]` |
| 查看内置 Schema | `td.py schema bundle\|chunk\|transcript\|…` |
| 看上游（cangjie）能力与依赖 | `td.py upstream list` |
| 直通执行上游实现 | `td.py upstream run --dry-run <tool> <args…>` |

---

## 关键参数

### chunk
| 参数 | 默认 | 说明 |
|---|---|---|
| `--max-chars` | 4000 | 单块上限；元素超长时按**句边界**二次切分 |
| `--sidecar` | `<src><后缀>.td` | 产物目录 |
| `--source-id` | src-main | 多来源时的来源标识 |
| `--force` | 关 | 忽略 sha256 缓存重算 |

### transcript
| 参数 | 默认 | 说明 |
|---|---|---|
| `--gap` | 2500ms | 间隔小于此值的 cue 合并成段 |
| `--max-chars` | 420 | 单段最长字符 |
| `--offset` | 0 | 整体时间偏移（秒），多集拼接用 |
| `--merge` | 关 | 多文件按自然序合并 |

### research merge
`--threshold` 默认 0.62（3-gram Jaccard）。**只对命题去重**，出处写法不同不影响判定；
相似但互相矛盾的一手条目会被标 `⚠️ 冲突` 而不是静默取先到。

### compile
| 情形 | 行为 |
|---|---|
| FIDELITY 低于门槛 | 拒绝发布（`--force` 可强发，manifest 留 `forced: true`） |
| `eval_mode` 非 dual-agent | `gate` 默认拒绝（`--allow-fallback` 才放行） |
| 检测到本地手改 | 拒绝静默覆盖（`--overwrite` 才放行，先自动快照） |
| `--mode single` | 额外生成路由入口 `SKILL.md` + `cards/` |

---

## 典型全链路

```bash
# 书籍
td.py init books/x && td.py chunk books/x/source.md
td.py lexindex books/x/source.md.td/chunks.jsonl
td.py lexindex --db books/x/source.md.td/lexical.sqlite --query "第N章关键词" --neighbors 1
vim books/x/skills/*/SKILL.md            # 按模板写能力卡
td.py validate books/x && td.py gate books/x/skills/*/FIDELITY.md --min B
td.py strategy books/x && td.py compile books/x --out ~/.workbuddy/skills/x

# 视频
td.py fetch-subtitle "<URL>" --out subs/ --execute     # 不加 --execute 只打印命令
td.py transcript subs/<id>.srt && td.py chunk subs/<id>.transcript.md --source-id transcript
# 之后同上

# 人物
td.py research init books/p --person "某人"    # 填 6 个车道
td.py research merge books/p/references/research/*.md --out books/p/references/research-merged.md
# 按 PERSONA 模板写卡，走同一套 validate/gate/compile

# 触发测试（防过拟合 + 统计口径）
td.py trigger build  books/x --out suite.json
td.py trigger split  suite.json                  # 固定种子 60/40
td.py trigger prepare suite.json --out blind      # 盲测包不含 expect
#   → Agent 作答 → td.py trigger score suite.json answers.json
#     输出 precision / recall / F1 / 诱饵通过率 / 兄弟混淆率

# 演进
td.py diff dist-v1 books/x && td.py impact dist-v1 <slug> && td.py update books/x --out dist-v1 --apply
```

---

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 校验/门槛失败（阻断性问题、低等级、手改冲突、触发测试未过） |
| 2 | 参数错误（argparse） |
| 130 | 用户中断 |

> `upstream run` 的 `--dry-run` 必须放在 `<tool>` **之前**，其后会被 argparse 的 REMAINDER 吞掉：
> `td.py upstream run --dry-run count <dir>`。

**所有失败都是人话 + 可执行下一步**，不会抛裸 traceback。
