# examples · 一次完整跑通的记录

> 本目录展示**工具链怎么用**，不含真实书籍蒸馏产物（那需要版权素材 + 语义提取）。
> 命令行输出是 `scripts/td.py` 在 macOS / Python 3.13 上的真实执行结果。

---

## 场景

素材：《示例方法论》第 3 章 → 蒸馏出 2 张能力卡 → 过 FIDELITY 门槛 → 发布到本地 skills 目录。

---

## 1. 环境自检

```
$ python3 scripts/td.py doctor
td.py v1.0.0 · rulai-skill 环境自检

✅ Python 3.13.12（要求 ≥3.10）
⚠️  PyYAML 缺失 —— 已降级到内置最小解析器，够用但不严格
   可选安装：python3 -m pip install pyyaml
⚠️  jsonschema 缺失 —— 已降级到内置必填字段校验
   可选安装：python3 -m pip install jsonschema
✅ methodology/ 就绪（6 个文件）
✅ templates/ 就绪（5 个文件）
✅ schemas/ 就绪（4 个文件）
✅ 5 个核心模板齐全

🎉 可以开始蒸馏。
```

> 注意两个 ⚠️ 不是错误：**无第三方依赖也能跑完全部命令**，这是刻意的降级设计。

## 2. 建 bundle

```
$ python3 scripts/td.py init /tmp/td_e2e/bundle
✅ 已生成 bundle 骨架：/tmp/td_e2e/bundle
   bundle.json      ← 包描述（改 source / skills）
   skills/*.md      ← 能力卡，按 templates/CAPABILITY.md.template 写
   SOURCES.md       ← 素材清单 + 一手来源占比
```

## 3. 校验（故意写了三张坏卡）

```
$ python3 scripts/td.py validate /tmp/td_e2e/bundle
❌ [skills/no-standard.md] E 段存在但没有『完成标准』
❌ [skills/persona-bad.md] 人物卡首句缺少『认知植入而非角色扮演』声明
❌ [skills/persona-bad.md] 『我看问题的方式』含显式步骤 ['Step 1', '第一步：', '1.'] —— 会退化成 SOP
❌ [skills/persona-bad.md] 死链：references/missing.md
⚠️  [skills/no-standard.md] description 未声明『不做/不适用』，容易被邻近技能抢调用

统计：error 4 / warn 4
❌ 存在阻断性问题，不允许发布。
```

四类拦截全部生效：**步骤禁令、完成标准、死链、边界声明**。

## 4. 修复后：FIDELITY 门槛

```
$ python3 scripts/td.py gate bundle/skills/FIDELITY.md --min B
📋 FIDELITY gate · FIDELITY.md
   总分 80/100   等级 B   评测模式 dual-agent
   分项：consistency=26  style=15  edge_honesty=14  source_transparency=12  structure=13
✅ 通过门槛 B（≥70）
exit=0

$ python3 scripts/td.py gate bundle/skills/FIDELITY.md --min A
❌ 未达门槛 A（要求 ≥85，实际 80）
   → 退回阶段 2 重做能力卡，重点补：完成标准 / 失败模式 / 原始素材一手来源
exit=1
```

## 5. 发布

```
$ python3 scripts/td.py compile bundle --out ~/.workbuddy/skills/my-distill
🔧 compile · bundle → ~/.workbuddy/skills/my-distill
   版本 0.2.0 · 技能 2 个 · 门槛 B
   ✓ good-capability              FIDELITY 80/B
   ✓ weak-capability              FIDELITY 80/B
✅ 已发布 2 个技能 → ~/.workbuddy/skills/my-distill
```

产出结构：

```
out/
├── BUILD_MANIFEST.json          ← 含 published_hashes，用于本地手改检测
├── registry/
│   ├── good-capability.json
│   └── weak-capability.json
└── skills/
    ├── good-capability/SKILL.md
    └── weak-capability/SKILL.md
```

## 6. 本地手改 → 被拦截

```
$ echo "<!-- 手写补丁 -->" >> out/skills/good-capability/SKILL.md
$ python3 scripts/td.py compile bundle --out out
❌ 检测到本地手工改动 1 处，拒绝静默覆盖：
   → skills/good-capability/SKILL.md
exit=1
```

## 7. 快照与回滚

```
$ python3 scripts/td.py compile bundle --out out --overwrite
   发布前快照：20261004-000526
✅ 已发布 2 个技能 → out

$ python3 scripts/td.py rollback out --to latest
   现状已另存为 20261004-000527，可再回滚
✅ 已回滚到 20261004-000526（5 个文件）
```

回滚本身也会先打快照，所以**回滚错了还能再回滚回来**。

## 8. 缺 FIDELITY 且未给分

```
$ python3 scripts/td.py compile bundle --out out
❌ [good-capability] 缺少 FIDELITY 报告且未给 fidelity_score
   → 先跑阶段 4b 生成 bundle/skills/good-capability/FIDELITY.md
   → 或临时应急：python3 scripts/td.py compile ... --force
```

`--force` 会放行，但 manifest 里写 `"forced": true`，事后可审计。

---

## 下一步

真正蒸馏一本书时，把 `bundle/skills/*.md` 换成按 `templates/CAPABILITY.md.template` 写的真实能力卡，
`FIDELITY.md` 换成 `templates/FIDELITY.md.template` 生成的真实质检报告（**双 Agent，别自评**），
再跑同一条命令即可。

---

# v1.1.0 新增链路（真实输出）

> 以下均为 macOS / Python 3.13.12 上的实际执行结果。

## 9. 长内容分块（>5 万字必做）

```
$ python3 scripts/td.py chunk book.md --max-chars 4000
✅ 5 块 / 10 elements / 平均 1066 字符
   产物目录：book.md.td
   最大块 1661 字符（上限 4000）

$ python3 scripts/td.py chunk book.md            # 第二次
▸ 命中确定性缓存，跳过重算（sha256 3f9a1c…）
```

产物：`document.json`（SourceDocument）/ `chunks.jsonl`（每行一块）/ `index.json`（标题树）/ `.cache.json`（sha256）

## 10. 按索引检索，避免全量读入

```
$ python3 scripts/td.py index book.md.td --grep "主要矛盾"
✅ 命中 2 块（关键词：主要矛盾）
      ck-0002  1661c  第二章 抓主要矛盾
      ck-0003   958c  第二章 抓主要矛盾 / 第二节 抓总的、主要的
```

**这是省 token 的关键动作**：5 路并行提取时每个 Agent 只拿命中块，不是整本 ×5。

## 11. 字幕 → 逐字稿（离线）

```
$ python3 scripts/td.py transcript talk.srt
✅ 5 cues → 2 段（去重丢弃 1）
   时长 32s
   talk.transcript.md
```

输入含滚动重复的字幕（同一句显示两次），去重后进逐字稿；时间段按 2.5s 间隔合并成段。
多集：`td.py transcript ep1.srt ep2.srt --merge --out series`。

## 12. 输出形态决策

```
$ python3 scripts/td.py strategy bundle --purpose workflow
✅ 推荐形态：pack   （2 晋级 / 0 路由 / 共 2）
   · 用户目的为 workflow → pack
   备选：single（1 个路由入口 + 2 张能力卡）
```

默认 `single-first`：晋级 ≥3 **且**触发验证就绪才推 pack，避免一拆多就互相抢调用。

## 13. token 计量

```
$ python3 scripts/td.py count .
   常驻发现成本 discovery_payload :     271
   语料总量 corpus_total          :  36172
   SKILL.md  min/median/max/total : 4847 / 4847 / 4847 / 4847
```

装 tiktoken 后为精确值；未装时按字符估算并在输出里标注「数值偏低」。

## 14. 增量维护

```
$ python3 scripts/td.py diff bundle-v1 bundle-v2
   新增 0 · 删除 0 · 变更 1 · 未变 1
   ~ major-contradiction：补充测试（2680→2724 字符）

$ python3 scripts/td.py repair bundle-v2 --apply
✅ CRLF→LF（换行符统一，不动内容）

$ python3 scripts/td.py update bundle --out dist --apply
✅ 已重编译 2 个技能，快照 20261004-081530
```

`repair` / `patch` / `update` 默认 dry-run，不加 `--apply` 不落盘。

## 15. 回归测试

```
$ python3 tests/e2e.py
✅ doctor 环境自检与能力矩阵
✅ init 生成 bundle + 六路调研骨架
✅ chunk 结构分块/缓存/索引
✅ chunk 超长段落二次切分
✅ transcript SRT 去重与时间戳
✅ research 六路合并去重与冲突标记
✅ validate 合格 bundle 零错误
✅ validate 拦截步骤禁令/完成标准/失败模式
✅ output-eval 产物体检
✅ gate 门槛与自测降级
✅ strategy single/pack 决策
✅ compile 原子发布 + 手改检测 + 回滚
✅ compile single 模式
✅ compile 拒绝低等级 + --force 留痕
✅ trigger build/record/score 全链路
✅ count token 计量
✅ prompt 单文件编译
✅ diff/impact/repair/patch/update
✅ schema 与 --help 完整
✅ 错误信息人话化

通过 20 / 20
```

零依赖解释器与装了 pyyaml/tiktoken 的解释器**都跑过同一套测试**，结果一致。
