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
# 打包**当前 HEAD**（不是工作区）——保证 zip 内容 == 那个 commit 可复算的内容
git archive --format=zip --prefix="$NAME/" -o "$OUT/$NAME.zip" HEAD

# 关键：在产物目录里算 sha256 → 输出行是**相对文件名**，`shasum -c` 才能用
cd "$OUT"
shasum -a 256 "$NAME.zip" > "$NAME.zip.sha256"

echo "✅ $OUT/$NAME.zip"
cat "$NAME.zip.sha256"
echo "   自检：cd $OUT && shasum -c $NAME.zip.sha256"