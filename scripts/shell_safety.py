#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/shell_safety.py — 扫 shell 脚本里会让 bash 犯蠢的几类写法。

**为什么需要它**：`ci_local.sh` 里写过 `echo "…（rc=$rc）"`——
全角括号紧跟变量名。bash 把 `rc` 之后那个多字节字符**当成变量名的一部分**，
于是变量取空、打印出乱码，**而退出码仍然是 0**。

实测（本脚本每条判据都跑过 bash 验证，不是猜的）：
    $ echo "（$VENV）"      # VENV=/x/y
    （��                ← 变量内容丢失，rc=0
`$dest 是实体目录`（**后面有空格**）则是**安全的**——所以判据必须是
「紧跟」，不是「后面出现中文」。首版把两者混为一谈，一次报了 8 处、
其中 6 处是假阳性；**误报的守卫等于没有守卫**。

检查项：
  1. `$VAR` **紧跟**非 ASCII 字节 → bash 静默截断变量名（**最危险：rc 仍为 0**）
  2. `cmd | tail ... || fail=` → 用管道退出码判成败（本项目已犯两次）
  3. 位置参数 `$1` 未加引号 → 路径含空格即被拆开
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `$var` **紧跟**一个非 ASCII、非空白、非引号的字节 —— 只有这种情况 bash 会吞掉变量名
VAR_THEN_NONASCII = re.compile(
    r"\$(?!\{)([A-Za-z_]\w*)(?=[^\x00-\x7f\s\"'`;)\]}])")
# 用管道退出码判成败
PIPE_AS_RC = re.compile(r"\|\s*(tail|head)\b[^|;&]*\|\s*(&&|\|\|)")
# 未加引号的位置参数（`"$1"` 是对的，要放过）
UNQUOTED_POSITIONAL = re.compile(r"(?<![\"$\w])\$[1-9](?!\w)")


def scan(path: Path) -> list[str]:
    problems = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0] if not line.strip().startswith("#") else ""
        if not code.strip():
            continue
        if VAR_THEN_NONASCII.search(code):
            problems.append(
                f"{path.name}:{i} 变量名后紧跟非 ASCII 字符——bash 会把它读进变量名：{line.strip()[:90]}")
        if PIPE_AS_RC.search(code):
            problems.append(
                f"{path.name}:{i} 用管道退出码判成败（`{line.strip()[:60]}`）——"
                f"rc 是 tail 的，不是这条命令的")
        if UNQUOTED_POSITIONAL.search(code):
            problems.append(
                f"{path.name}:{i} 位置参数未加引号：{line.strip()[:80]}")
    return problems


def main() -> int:
    candidates = (list((ROOT / "tests").glob("*.sh"))
                + list((ROOT / "scripts").rglob("*.sh"))
                + [ROOT / "install.sh"])
    scripts = sorted(p for p in candidates if p.exists())
    if not scripts:
        print("⚠️ 未运行：没找到任何 .sh 脚本")
        return 2
    problems: list[str] = []
    for p in scripts:
        problems += scan(p)
    for p in problems:
        print(f"❌ {p}")
    if problems:
        print(f"\n{len(problems)} 处会让 bash 犯蠢的写法")
        return 1
    print(f"✅ {len(scripts)} 个 shell 脚本：无上述三类写法")
    return 0


if __name__ == "__main__":
    sys.exit(main())