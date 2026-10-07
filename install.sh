#!/bin/sh
# install.sh — 把 rulai-distill 装进任何支持 Agent Skills 开放标准的 Agent。
#
# 事实依据（2026-10 核实）：
#   · SKILL.md 是 Anthropic 2025-10 发布、现已捐给 Linux Foundation 的**开放标准**
#   · 各Agent 只是**读取路径不同**，格式无需改动
#   · `.agents/skills/` 是通用总线：Codex 读它当主路径，其余Agent 读它当兜底
#   · Gemini CLI 对文件名大小写敏感，SKILL.md 必须严格大写
#
# 用法：
#   ./install.sh                # 符号链接（推荐，改代码自动生效）
#   ./install.sh --copy         # 实体复制（Windows / 不支持符号链接的环境）
#   ./install.sh --uninstall    # 卸载全部
#   ./install.sh --list         # 只看会装到哪些目录
#   ./install.sh --dir ~/.some/skills   # 额外装一个自定义目录
#   ./install.sh --project /path/to/repo  # 额外装成那个项目的项目级技能
#
# 幂等：重复跑不会重复安装，也不会覆盖已有目录。
#
# ⚠️ 项目级安装**必须显式给--project <路径>**：默认只装全局，绝不往当前目录里
#    塞自引用符号链接（`.agents/skills/rulai-distill -> .` 会让 rglob 无限递归）。

set -eu

SKILL_NAME="rulai-distill"
SRC=$(cd "$(dirname "$0")" && pwd)
MODE="symlink"
CUSTOM_DIRS=""
ACTION="install"

# ── 目标目录表 ────────────────────────────────────────────────────────────
# 左边是人类可读的 Agent 名，右边是它读技能的路径（已核实存在性）。
AGENT_TARGETS="
claude-code:$HOME/.claude/skills
codex-cli:$HOME/.codex/skills
universal:$HOME/.agents/skills
gemini-cli:$HOME/.gemini/skills
cursor:$HOME/.cursor/skills
opencode:$HOME/.config/opencode/skills
openclaw:$HOME/.openclaw/skills
hermes:$HOME/.hermes/skills
workbuddy:$HOME/.workbuddy/skills
"

PROJECT_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --copy)      MODE="copy" ;;
    --uninstall) ACTION="uninstall" ;;
    --list)      ACTION="list" ;;
    --dir)       shift; CUSTOM_DIRS="$CUSTOM_DIRS$1
" ;;
    --project)   shift; PROJECT_DIR="$1" ;;
    -h|--help)   sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
  esac
  shift
done

# 项目级目标必须显式指定路径，且不能是本仓库自己（否则建出自引用链接）
if [ -n "$PROJECT_DIR" ]; then
    PABS=$(cd "$PROJECT_DIR" 2>/dev/null && pwd) || {
        echo "❌ --project 指向的目录不存在：$PROJECT_DIR" >&2; exit 2; }
    [ "$PABS" = "$SRC" ] && {
        echo "❌ --project 不能指向本仓库自己——那会建出自引用符号链接。" >&2
        echo "   项目级安装请指向**使用**技能的另一个仓库。" >&2
        exit 2; }
    PROJECT_TARGETS="$PABS/.claude/skills
$PABS/.agents/skills
"
else
    PROJECT_TARGETS=""
fi

# ── 前置检查：源目录必须像一个技能 ────────────────────────────────────────
if [ ! -f "$SRC/SKILL.md" ]; then
  echo "❌ 这里没有 SKILL.md，请从 rulai-distill 仓库根目录运行本脚本。" >&2
  exit 1
fi
if [ ! -d "$SRC/scripts" ]; then
  echo "❌ 缺少 scripts/ 目录，这看起来不是完整的 rulai-distill 仓库。" >&2
  exit 1
fi

# ── 收集要处理的目录 ──────────────────────────────────────────────────────
TARGETS=$(printf '%s\n%s' "$AGENT_TARGETS" "$PROJECT_TARGETS" | sed '/^$/d')
[ -n "$CUSTOM_DIRS" ] && TARGETS=$(printf '%s\n%s' "$TARGETS" "$CUSTOM_DIRS" | sed '/^$/d')

place_one() {
    dir=$1
    dest="$dir/$SKILL_NAME"

    if [ "$ACTION" = "list" ]; then
        printf '  %-20s %s%s\n' "$2" "$dir" "$([ -e "$dest" ] && echo '  [已安装]')"
        return 0
    fi

    mkdir -p "$dir"

    if [ "$ACTION" = "uninstall" ]; then
        if [ -L "$dest" ]; then rm "$dest"; echo "  ✅ 已移除链接 $dest"
        elif [ -d "$dest" ]; then
            echo "  ⚠️  $dest 是实体目录，未自动删除（请手动确认后 rm -rf）"
        else
            echo "  ➖ 未安装：$dest"
        fi
        return 0
    fi

    if [ -L "$dest" ]; then
        if [ "$(cd "$(dirname "$dest")" && readlink "$dest")" = "$SRC" ]; then
            echo "  ✅ 已是最新链接，跳过：$dest"; return 0
        fi
        rm "$dest"
    elif [ -d "$dest" ]; then
        echo "  ⚠️  $dest 已存在且不是链接，跳过（不覆盖别人的东西）"; return 0
    fi

    if [ "$MODE" = "copy" ]; then
        cp -R "$SRC" "$dest"
        echo "  ✅ 已复制到 $dest"
    else
        ln -s "$SRC" "$dest"
        echo "  ✅ 已链接到 $dest"
    fi
}

echo "rulai-distill 安装器"
echo "  源目录：$SRC"
echo "  方式：  $MODE"
echo

OLDIFS=$IFS; IFS='
'
for line in $TARGETS; do
    [ -z "$line" ] && continue
    dir=$(printf '%s' "$line" | cut -d: -f2-)
    name=$(printf '%s' "$line" | cut -d: -f1)
    [ -z "$dir" ] && continue
    IFS=$OLDIFS
    place_one "$dir" "$name"
    IFS='
'
done
IFS=$OLDIFS

echo
case "$ACTION" in
  list)     echo "（--list：以上是会涉及的目录，未做任何改动）" ;;
  uninstall) echo "完成卸载。链接已删，实体目录请手动确认。" ;;
  *)        echo "完成。多数 Agent 需要重启一次才会加载新技能。" ;;
esac
echo "自检：cd \"$SRC\" && python3 scripts/td.py doctor"