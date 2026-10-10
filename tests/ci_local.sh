#!/usr/bin/env bash
# 把 CI（4 个 workflow）的每一步在本地跑一遍。发版前的固定动作。
# 教训来源：#64——「本地全绿、CI 全红」= 有 CI 步骤没进本地测试网。
set -u
cd "$(dirname "$0")/.." || exit 1
PY=/Users/yihe/.workbuddy/binaries/python/versions/3.13.12/bin/python3
fail=0
step() { printf '\n=== %s ===\n' "$1"; }

# ⚠️ 本脚本第一版犯了本项目已记录过的老错：`cmd | tail -3 || fail=1` ——
# **管道的退出码是 tail 的**，于是有步骤失败时脚本仍打印"✅ 完成"（假绿）。
# 现在统一走 run()：先落日志、取真实 rc、再打印尾部。
run() {
  local log=/tmp/ci_local_step.log
  "$@" >"$log" 2>&1; local rc=$?
  tail -3 "$log"
  [ $rc -eq 0 ] || { echo "  ↑ 该步失败（rc=${rc}）"; fail=1; }
  return 0
}

# 路径守卫：脚本第一版 cd 错了目录，结果每一"步"都在空目录里跑，
# grep 找不到文件 → 打印"干净/无"，`glob` 找不到 schema → 打印"0 个 schema 合法"。
# **那是假绿**——正是本项目最忌讳的模式。先确认自己在仓库根，再往下走。
if [ ! -f scripts/td.py ] || [ ! -f tests/e2e.py ]; then
  echo "❌ 不在仓库根目录（找不到 scripts/td.py）——拒绝给出任何'通过'结论"
  exit 1
fi

step "⓪ 自检：本脚本必须能报「失败」"
# 只报"通过"的检查器比没有更危险。让 run() 执行一次必然失败的命令，
# 确认它真的把 fail 置位；若没置位，说明脚本本身坏了（例如又用了 `cmd | tail` 判退出码——
# 本脚本第一版正是这么写的，结果有步骤失败时它仍打印 ✅）。
_before=$fail
run false
if [ "$fail" -ne "$_before" ]; then
  echo "  ✓ 失败路径生效（run() 能捕获 rc≠0）"
else
  echo "  ✗ 失败路径失效：本脚本会给假绿，全部结论不可信"
  fail=1
fi
fail=$_before   # 自检不污染最终结论

step "① schema 合法性"
$PY - <<'PY' || fail=1
import glob, json
files = sorted(glob.glob('schemas/*.json') + glob.glob('scripts/vendor/cangjie/schemas/**/*.json', recursive=True))
for f in files:
    json.load(open(f, encoding='utf-8'))
print(f'{len(files)} 个 schema 合法')
PY

step "② 技能包静态校验 validate ."
run $PY scripts/td.py validate .

step "③ Markdown 结构自检"
run $PY tests/doc_structure_check.py

step "③b 对外声称台账（P0-4）"
run $PY docs/verify_claims.py

step "④ vendored 上游体检"
run $PY scripts/td.py upstream list
run $PY scripts/td.py upstream run --dry-run chunk --help

step "⑤ 红线扫描（危险调用模式）"
if grep -rnE "\beval\(|\bexec\(|os\.system|shell=True|socket\.|requests\.|urllib\.request|httpx|aiohttp" \
    scripts/td.py scripts/tdlib/ --include='*.py' | grep -v -e "output_eval" -e "subprocess(shell=True)"; then
  echo ">>> RED LINE HIT"; fail=1
else
  echo "干净"
fi

step "⑥ 禁止硬编码密钥"
if grep -rniE "api[_-]?key\s*=\s*['\"]|secret\s*=\s*['\"]|password\s*=\s*['\"]|Bearer [A-Za-z0-9]{20}" \
    scripts/ --include='*.py' --include='*.sh'; then
  echo ">>> SECRET HIT"; fail=1
else
  echo "无"
fi

step "⑦ docs-check 的四项测试"
run $PY tests/e2e.py --only t_docs_no_drift,t_defect_ledger_stats,t_defect_regression_ledger,t_contract_ledger_no_silent_gap

# pipeline-check 另有一条「完整依赖模式」回归（装了 pyyaml/tiktoken 再跑一遍）。
# 本地若没有带可选依赖的解释器，**明确说"没跑"**——不许静默跳过（跳过伪装成通过 = #65）。
step "⑧ 完整依赖模式回归（CI 的第二步）"
VENV=/Users/yihe/.workbuddy/binaries/python/envs/default/bin/python
if [ -x "$VENV" ] && "$VENV" -c "import yaml, tiktoken" 2>/dev/null; then
  run "$VENV" tests/e2e.py --tiktoken
else
  echo "⚠️ 未运行：找不到带 pyyaml/tiktoken 的解释器（${VENV}）—— CI 会跑这一步"
  echo "   （本地建法：python3 -m venv <dir> && <dir>/bin/pip install pyyaml tiktoken jsonschema）"
  skipped_full=1
fi

step "结论"
if [ $fail -ne 0 ]; then
  echo "❌ 有步骤失败"
elif [ "${skipped_full:-0}" = "1" ]; then
  echo "⚠️ 通过（但有 1 步未运行：完整依赖模式）—— 不要把这次预演当成 CI 的等价物"
else
  echo "✅ CI 全部步骤本地通过"
fi
exit $fail
