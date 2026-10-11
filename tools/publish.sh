#!/usr/bin/env bash
# publish.sh — 发布编排（2026-10-11 评估 P2 项）
#
# 流程：最低版本语法自检 + 打包 → 本地回归(e2e + verify_claims) → git fetch 对齐
#       → 分叉检查 → 推送(HTTP/1.1 重试) → 发布后核对(走 api.github.com，不受 github.com 代理影响)
#       → 可选：创建 GitHub Release。
#
# 诚实约束（不造假）：
#   - 推送走 git（github.com 端点）。若代理挡了 github.com 主域导致 push 失败，
#     本脚本**不会**走 REST API 伪造一次推送（那会产生哈希分叉、与远端不一致）。
#     它会明确报告阻塞，并给出代理恢复后的重推命令。
#   - 发布后核对用 `gh api`（api.github.com，本环境可达），只做「远端==本地」确认，不替你发版。
#
# 用法：
#   tools/publish.sh 1.9.1                      # 自检 + 测试 + 推送 + 核对
#   tools/publish.sh 1.9.1 --release            # 再加：创建 GitHub Release（gh，API 通道）
#   tools/publish.sh 1.9.1 --release --notes 文件  # 用指定 Release notes
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION=""
DO_RELEASE=0
NOTES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --release) DO_RELEASE=1; shift;;
    --notes)   NOTES="$2"; shift 2;;
    -*)        echo "未知参数: $1" >&2; exit 1;;
    *)         VERSION="${VERSION:-$1}"; shift;;
  esac
done
[ -z "$VERSION" ] && { echo "用法: tools/publish.sh <version> [--release] [--notes 文件]" >&2; exit 1; }

# 选一个 >=3.10 的 python（CI 用 3.10；本机可能只有 3.9 系统解释器，要避开）
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done
[ -z "$PY" ] && { echo "❌ 需要 Python >= 3.10（CONTRIBUTING 已说明 3.9 会假失败）" >&2; exit 1; }
echo "🐍 用 $PY（$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')）跑回归"

echo
echo "== 1/6 最低版本语法自检 + 打包 =="
bash tools/make_release.sh "$VERSION"

echo
echo "== 2/6 本地回归（e2e + verify_claims）=="
"$PY" tests/e2e.py 2>&1 | tee "/tmp/e2e_pub_$$.log" | tail -4
if grep -qE "❌" "/tmp/e2e_pub_$$.log"; then
  echo "❌ e2e 有失败项，先修再发" >&2; exit 1
fi
"$PY" docs/verify_claims.py 2>&1 | tail -3

echo
echo "== 3/6 git fetch 对齐 =="
git fetch origin 2>&1 | tail -3 || echo "（fetch 失败：继续，但可能无法及时发现分叉）"

echo
echo "== 4/6 工作树 + 分叉检查 =="
if [ -n "$(git status --porcelain)" ]; then
  echo "❌ 工作树不干净，先 commit" >&2; git status --short; exit 1
fi
BR="$(git rev-parse --abbrev-ref HEAD)"
AHEAD=$(git rev-list --count "origin/$BR..HEAD" 2>/dev/null || echo 0)
BEHIND=$(git rev-list --count "HEAD..origin/$BR" 2>/dev/null || echo 0)
echo "分支 $BR：领先 origin $AHEAD / 落后 origin $BEHIND"
if [ "$BEHIND" -gt 0 ]; then
  echo "❌ 本地落后远端 $BEHIND 个提交，先 pull/rebase 再发（避免非快进 push）" >&2; exit 1
fi

echo
echo "== 5/6 推送（HTTP/1.1 + 重试）=="
PUSHED=0
if [ "$AHEAD" -gt 0 ]; then
  for i in 1 2 3 4 5; do
    echo "  push attempt $i ..."
    if git -c http.version=HTTP/1.1 push origin "$BR"; then PUSHED=1; break; fi
    sleep 3
  done
  if [ "$PUSHED" -eq 0 ]; then
    echo "❌ git push 失败（多半是代理挡了 github.com 主域的 CONNECT 隧道）。" >&2
    echo "   代理恢复后重跑本脚本，或手动：" >&2
    echo "     git -c http.version=HTTP/1.1 push origin $BR" >&2
    echo "   ⚠️ 不造哈希分叉：等代理恢复再推，不要走 REST API 伪造推送。" >&2
    exit 2
  fi
else
  echo "（无未推送提交，跳过 push）"
fi

echo
echo "== 6/6 发布后核对（gh api，走 api.github.com，不受 github.com 代理影响）=="
REMOTE_HEAD=$(gh api "repos/yihexiang/rulai-distill/git/ref/heads/$BR" --jq '.object.sha' 2>/dev/null || echo "")
LOCAL_HEAD=$(git rev-parse HEAD)
if [ "$REMOTE_HEAD" = "$LOCAL_HEAD" ]; then
  echo "✅ 远端 HEAD == 本地 HEAD（$LOCAL_HEAD）"
else
  echo "⚠️ 远端 $REMOTE_HEAD ≠ 本地 $LOCAL_HEAD（推送可能尚未完全生效，稍后重试核对）"
fi

if [ "$DO_RELEASE" -eq 1 ]; then
  echo
  echo "== 创建 GitHub Release v$VERSION =="
  ARGS=(release create "v$VERSION" --title "v$VERSION" --target "$BR")
  if [ -n "$NOTES" ]; then ARGS+=(--notes-file "$NOTES"); else ARGS+=(--generate-notes); fi
  ARGS+=( "dist/rulai-distill-$VERSION.zip" "dist/rulai-distill-$VERSION.zip.sha256" )
  gh "${ARGS[@]}"
  echo "✅ Release v$VERSION 已建：https://github.com/yihexiang/rulai-distill/releases/tag/v$VERSION"
fi

echo
echo "✅ 发布编排完成（version=$VERSION）"
