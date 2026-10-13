# test-results · zai-de-bu-zai-xian

> 本文件如实记录测试状态。**凡未运行的测试，一律标「待运行」，不填任何数字。**
> 建卡日期：2026-10-13。建卡人：能力卡构造子 Agent。

## 1. 触发压力测试（Phase 4a）—— **待运行，无结果**

用例集：同目录 `test-prompts.json`（7 条：3 should_trigger / 2 should_not_trigger / 2 sibling）。

- **状态：Phase 4 待运行。** 截至建卡时，本套件**尚未执行**，没有任何命中率数字。
- 不预填数字的原因：通过线是 `should_trigger` 100% 命中、`should_not_trigger` 100% 返回 null、`sibling` 两条全部判给正确一侧——这些只能由实际作答产生，建卡时写任何数字都是虚构。

**复跑命令**（在仓库根目录执行，必须用托管 Python）：

```bash
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
cd /Users/yihe/WorkBuddy/2026-10-03-12-20-21/rulai-distill

# ① 从套件生成待答问卷（含 skills_in_scope，强制选择题）
$PY scripts/td.py trigger record books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/test-prompts.json \
    --out books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/trigger-record.json

# ② Agent 或人工作答，产出 answers.json（每案一个 chosen slug 或 null）

# ③ 机械判分
$PY scripts/td.py trigger score books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/test-prompts.json \
    books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/answers.json
```

**跑之前必须解决的前置项**（否则 sibling 判定基线不成立）：

- `mingfen-scan`（F01 名分三层扫描）本体卡尚未建成。`test-prompts.json` 的 `skills_in_scope` 里它的
  description 是建卡时按 F01 拟定的边界描述——**跑 x-01/x-02 前，应以 mingfen-scan 实际卡片的
  description 替换该字段**，否则选择题的候选池与真实发布态不一致。

## 2. 建卡时已实跑的静态自验（有真实输出，可复算）

以下命令在建卡当天真实执行过，输出如下；复跑命令见每节。

### 2.1 引语逐字核验（verify-quotes）—— PASS

```
$PY scripts/td.py verify-quotes books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/SKILL.md corpus/anchored/src-01-tongjian-wei.md
引用 12 个（条目引用 0 + 时间戳 0 + 书类引用块 12）
逐字引语核验 12 条 → 命中 12 条
✅ 全部引语在语料中核到
```

### 2.2 段号锚定（anchor）—— PASS

```
$PY scripts/td.py anchor books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/SKILL.md --corpus corpus/anchored/src-01-tongjian-wei.md
✅ 判定 PASS：57 条带段号标注的引语全部锚定在声明的段号内；另有 30 条无 §N 标注、不可定位（未核验）
```

30 条无 §N 标注者为 A2 语言信号（用户口语原话）与卡片自造概念，按工具口径「不判失败」；
其中 6 条建卡后已补段号（§85×3、§117×2、§109×1）。首轮曾报 6 处挂错
（1 处跨段 SPAN_HIT + 5 处 NOT_IN_CORPUS），已逐条修正后复跑通过——修正记录见 SOURCES.md。

### 2.3 引语体检（lint-quotes）—— 通过（退出码 0）

```
$PY scripts/td.py lint-quotes books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/SKILL.md
✅ 未发现用字不一致（简繁/异体）
```

3 条省略号提示（`…`，第 109/134/197 行）均为规范节引，符合 card-authoring-spec §0 红线 2「省略必须用 `…`」。
（首轮曾报 5 条，其中 2 条在 R 段引语拆改为连续片段后消除，终态为 3 条。）

### 2.4 产物体检（output-eval）与静态校验（validate）—— 均通过

```
$PY scripts/td.py output-eval books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/SKILL.md
规模：11846 字符 / 8880 tokens；六段：齐全

$PY scripts/td.py validate books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/SKILL.md
✅ 无问题（error 0 / warn 0）
```

## 3. 输出评测（Phase 4b · eval-kit）—— **待运行，无结果**

- 题库（consistency / edge_honesty）尚未出题，`eval-kit init` 尚未执行。
- 复跑命令：

```bash
$PY scripts/td.py eval-kit init books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/SKILL.md \
    --out books/tongjian-wei-bundle/skills/zai-de-bu-zai-xian/eval-kit
```

出题时必须覆盖的两维（照本卡 B 段自定的红线）：
① 四层账每层都要落到可指名的证据，写不出证据记「未验证」——测「未验证」是否被当成通过；
② 引论（荀子論/臣光曰）与叙事（吴起对答）必须分开——测是否把作者立场证据当成事件事实。

## 4. 跨卡对照评测（Phase 4c）—— **待运行，无结果**

- 需与 `mingfen-scan` 成对跑（该卡未建成前无法进行）。
- 通过线：x-01（秩序问题）判给 mingfen-scan、x-02（韧性问题）判回本卡，两条都对才算分界写清。
