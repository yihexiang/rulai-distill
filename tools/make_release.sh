#!/usr/bin/env bash
# make_release.sh — 生成发布 zip + sha256（可复跑，缺陷 #76 的收口）
#
# 为什么要有这个脚本（2026-10-10）：
# 此前 zip 与 sha256 是手工打的，于是 sha256 里写进了**绝对路径**
# （`1a2bdf65…  /tmp/rulai-distill-1.8.0.zip`）——而 README / Release notes
# 教用户跑的是 `shasum -c rulai-distill-1.8.0.zip.sha256`：
# **那条命令对下载来的用户必然失败**（找不到 /tmp/…）。
# 这是「声称≠实际」的同一种病：文档教了一个跑不通的命令。
#
# 修法：sha256 一律在**产物所在目录**里生成，文件名就是相对文件名；
# 且本脚本可复跑，测试直接跑它来验证（tools/ 与 tests/ 之间不留手工步骤）。
#
# 用法：
#     tools/make_release.sh 1.8.0            # 输出到 dist/
#     tools/make_release.sh 1.8.0 /tmp/out   # 输出到指定目录
set -euo pipefail

VERSION="${1:?用法: make_release.sh <version> [outdir]}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${2:-$ROOT/dist}"
NAME="rulai-distill-$VERSION"

command -v shasum >/dev/null || { echo "需要 shasum（macOS 自带）" >&2; exit 1; }

mkdir -p "$OUT"
cd "$ROOT"

# ── 最低版本语法自检（防 PEP 701 f-string 反斜杠病，# 见 2026-10-11 评估）
# 现象：f-string 表达式里含反斜杠（如嵌正则）只在 Python 3.12+ 合法，
# 3.10/3.11 直接 SyntaxError —— 本机用 3.13 跑测试全绿，CI 用 3.10 却红。
# 这里挑一个 <3.12 的解释器对全部 .py 做 py_compile；挑不到就告警（不致命，
# 但发布前请在 3.10/3.11 上至少手动复跑一次 py_compile）。
OLD_PY=""
for cand in python3.11 python3.10 python3.9 python3; do
  if command -v "$cand" >/dev/null; then
    if ! "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
      OLD_PY="$cand"; break
    fi
  fi
done
if [ -n "$OLD_PY" ]; then
  echo "🔎 最低版本语法自检（用 $OLD_PY / $("$OLD_PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')）"
  # 用 find -exec 批量编译（避免 bash3 mapfile / 文件名空格问题）
  if find . -name '*.py' -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/venv/*' \
       -exec "$OLD_PY" -m py_compile {} + ; then
    echo "✅ 全部 .py 在 <3.12 解释器下编译通过（CI py3.10 不会再 SyntaxError）"
  else
    echo "❌ 存在 <3.12 不兼容语法（多半是 f-string 反斜杠），先修再发布" >&2
    exit 1
  fi
else
  echo "⚠️  未在环境中找到 <3.12 的解释器，跳过最低版本语法自检" >&2
  echo "    发布前请在 Python 3.10/3.11 上至少手动跑一次：python3 -m py_compile \$(find . -name '*.py')" >&2
fi

# 打包**当前 HEAD**（不是工作区）——保证 zip 内容 == 那个 commit 可复算的内容
git archive --format=zip --prefix="$NAME/" -o "$OUT/$NAME.zip" HEAD

# ── BUILD_INFO：把「这个 zip 从哪个 commit 打出」写进包内（A2 · cangjie 有、rulai 补）
# 为什么：外部用户拿到 zip 后无法回答「这是哪个 commit 的产物」；
# 手改检测（published_hashes）只在发布目录内有效，zip 本身需要自描述。
# 用 Python zipfile 追加（不依赖 zip 二进制；git archive 本身也不依赖）。
STAGE="$OUT/.build-info-stage"
mkdir -p "$STAGE/$NAME"
{
  echo "name: rulai-distill"
  echo "version: $VERSION"
  echo "commit: $(git rev-parse HEAD)"
  echo "commit_date: $(git log -1 --format=%cI HEAD)"
  echo "build_date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "python_min: 3.10"
  echo "vendor_sha256: $(shasum -a 256 scripts/vendor/VENDOR.sha256 | awk '{print $1}')"
  echo "upstream: kangarooking/cangjie-skill v2.5.0（vendored 原样，见 scripts/vendor/PROVENANCE.md）"
} > "$STAGE/$NAME/BUILD_INFO"
python3 - "$OUT/$NAME.zip" "$STAGE/$NAME/BUILD_INFO" "$NAME/BUILD_INFO" <<'PY'
import sys, zipfile
zip_path, info_path, arcname = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(zip_path, "a") as z:
    z.write(info_path, arcname)
print("BUILD_INFO 已注入 zip：", arcname)
PY
rm -rf "$STAGE"

# 关键：在产物目录里算 sha256 → 输出行是**相对文件名**，`shasum -c` 才能用
cd "$OUT"
shasum -a 256 "$NAME.zip" > "$NAME.zip.sha256"

echo "✅ $OUT/$NAME.zip"
cat "$NAME.zip.sha256"
echo "   自检：cd $OUT && shasum -c $NAME.zip.sha256"