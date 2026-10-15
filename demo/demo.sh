#!/usr/bin/env bash
# demo.sh — 30 秒看完 rulai-distill 的核心主张：**不打分不发版，而且不由自己打分。**
#
# 为什么要有这个脚本：README 说得再漂亮，也不如让潜在用户**亲手跑一遍**。
# 本脚本只用仓库内已随包分发的真实产物（sample-bundle 的 five-affairs 卡 + 《孙子兵法》语料 +
# 三张人物卡的跨模型复评台账），不联网、不造数据、不摆拍——每一行输出都是真跑出来的。
#
# 用法：
#     bash demo/demo.sh              # 彩色 + 精简（终端观看，默认）
#     bash demo/demo.sh --full       # 不截断长输出
#     bash demo/demo.sh --ascii      # 强制纯文本（非 TTY 时自动启用）
#     bash demo/demo.sh --no-pause   # 不停顿，一口气跑完
#
# 全程只读，不写任何文件（唯一副作用是 Python 的 __pycache__）。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ASCII=0; FULL=0; PAUSE=1
[ -t 1 ] || ASCII=1          # 非 TTY（管道/录屏/CI）自动纯文本
for a in "$@"; do
  case "$a" in
    --ascii) ASCII=1 ;;
    --full) FULL=1 ;;
    --no-pause) PAUSE=0 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "未知参数：$a（可用 --full / --ascii / --no-pause）" >&2; exit 2 ;;
  esac
done

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3 python; do command -v "$cand" >/dev/null 2>&1 && { PY="$cand"; break; }; done
fi
[ -n "$PY" ] || { echo "❌ 找不到 python3" >&2; exit 1; }

CARD="examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md"
CORPUS="examples/sample-bundle/sources/sunzi-ji.txt"
FIDELITY="examples/sample-bundle/skills/five-affairs-seven-questions/FIDELITY.json"

# ── 输出helper ────────────────────────────────────────────────────────────────
if [ "$ASCII" = 1 ]; then
  C_TITLE=''; C_STEP=''; C_OK=''; C_DIM=''; C_END=''
else
  C_TITLE=$'\e[1;36m'; C_STEP=$'\e[1;33m'; C_OK=$'\e[1;32m'; C_DIM=$'\e[2m'; C_END=$'\e[0m'
fi
step()  { printf '\n%s━━━ %s%s\n' "$C_STEP" "$1" "$C_END"; }
dim()   { printf '%s%s%s\n' "$C_DIM" "$1" "$C_END"; }
ok()    { printf '%s%s%s\n' "$C_OK" "$1" "$C_END"; }
pause() { [ "$PAUSE" = 1 ] || return 0; [ -t 0 ] || return 0; printf '%s[回车继续]%s' "$C_DIM" "$C_END"; read -r _; }

# run <上限行数> <命令...>：跑真命令；精简模式下超长则**头尾各留一半、中部省略**。
# 为什么不能只留头部：anchor 这类命令的判定结论（✅ 判定 PASS / ❌  FAIL）在输出的**末尾**，
# 只 head 会把最该看的那行切掉。标注是必须的——悄悄截断会让读者以为输出就那么点，
# 那是另一种「声称≠实际」。
run() {
  local cap="$1"; shift
  if [ "$FULL" = 1 ]; then "$@"; return; fi
  local out n
  out="$("$@" 2>&1)"; n="$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
  if [ "$n" -le "$cap" ]; then printf '%s\n' "$out"; return; fi
  # 注意：必须分两行声明。`local a=1 b=$a` 在 set -u 下会因 a 尚未赋值而报 unbound。
  local head_n=$(( cap / 2 ))
  local tail_n=$(( cap - head_n ))
  printf '%s\n' "$out" | head -n "$head_n"
  dim "  …（中部省略 $(( n - cap )) 行）"
  printf '%s\n' "$out" | tail -n "$tail_n"
  dim "  （已截断：以上 $cap / $n 行。完整输出请直接跑：$*）"
}

printf '%s' "$C_TITLE"
cat <<'BANNER'
 ┌──────────────────────────────────────────────────────────────┐
 │  rulai-distill · 蒸馏工厂                                     │
 │  把书籍/长视频/播客/访谈/人物素材，蒸馏成                      │
 │  可执行 · 可验证 · 可追溯 的 Agent Skills                      │
 │                                                              │
 │  主张：不打分不发版，而且不由自己打分。                        │
 └──────────────────────────────────────────────────────────────┘
BANNER
printf '%s' "$C_END"
dim "本演示只用随包分发的真实产物，全程离线、只读，不造数据。"
pause

step "0/8 · 环境自检（零第三方依赖可跑）"
run 22 "$PY" scripts/td.py doctor

step "1/8 · 门禁① validate —— 结构 / 死链 / 完成标准 / 失败模式"
"$PY" scripts/td.py validate examples/sample-bundle

step "2/8 · 门禁② verify-quotes —— 每条引语逐字回语料（验「存在」）"
"$PY" scripts/td.py verify-quotes "$CARD" "$CORPUS"

step "3/8 · 门禁③ anchor —— 引语是否真在它声明的 §N 段里（验「归属」）"
run 16 "$PY" scripts/td.py anchor "$CARD" --corpus "$CORPUS"

step "4/8 · 门禁④ lint-quotes —— 简繁混用 / 省略号 / 归属可疑"
"$PY" scripts/td.py lint-quotes "$CARD"

step "5/8 · 门禁⑤ gate —— 默认要求 ≥2 个独立评分者，否则拒绝放行"
"$PY" scripts/td.py gate "$FIDELITY" --min A
pause

step "6/8 · 引擎对齐 —— 16 类上游能力全部在位，可逐条直通"
run 10 "$PY" scripts/td.py upstream list

step "7/8 · 跨模型异族复评台账 —— 组织独立 3/3（DeepSeek，8/8 一致、无编造）"
"$PY" scripts/tdlib/independent_recheck.py

step "8/8 · 对外声称逐条对账 —— 21 条声称必须有据、数字不许腐烂"
"$PY" docs/verify_claims.py

# 收尾横幅里的数字**从产物推导**，不手写——手写就会腐烂（本项目第 N 次）
DEFECT_N=$("$PY" -c "import sys;sys.path.insert(0,'scripts');from tdlib.defects import build_cases;print(len(build_cases()))")
CM_N=$("$PY" -c "
import json,pathlib
d=json.loads(pathlib.Path('docs/independent-recheck/ORG-INDEPENDENCE-LEDGER.json').read_text(encoding='utf-8'))
print(sum(1 for c in d['cards'].values() if c.get('org_independent')))
")

printf '\n%s' "$C_TITLE"
cat <<OUTRO
 ┌──────────────────────────────────────────────────────────────┐
 │  上面每一行都是真跑出来的：                                    │
 │    · 五道门禁全部实跑，不是文档里的口号                        │
 │    · ${DEFECT_N} 个自身缺陷公开登记，数字由测试强制相等                  │
 │    · ${CM_N} 张人物卡有跨模型异族复评（不同提供商家族）               │
 │    · 连 README 里的数字都有守卫盯着，写错即 CI 红               │
 │                                                              │
 │  下一步：                                                    │
 │    git clone https://github.com/yihexiang/rulai-distill.git   │
 │    cd rulai-distill && ./install.sh                           │
 │    python3 scripts/td.py doctor                               │
 └──────────────────────────────────────────────────────────────┘
OUTRO
printf '%s' "$C_END"

ok "演示完成。要自己改一张卡试试？看 GUIDE.md 的完整流程。"
dim "注：本演示在精简模式下会截断个别长输出，并明确标注截断了多少行——不悄悄截。"
