#!/usr/bin/env python3
"""docs-check 的结构自检：Markdown 死链与重复章节（纯文本层，无需构建）。

2026-10-10（#64）：这段逻辑原先以 heredoc **内联在 `.github/workflows/docs-check.yml`** 里，
于是**本地回归永远跑不到它**——我在 CONSTRAINTS.md 里举例写了 ``[配套](../b/)``（反引号里），
本地 96 项全绿，CI 却红了两处。与 #51 同类：**改了文件却没按用户的路径跑一遍**。
现在搬进仓库脚本并接入 `tests/e2e.py`，本地就能拦住。

用法：`python tests/doc_structure_check.py`（在仓库根目录执行）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from tdlib.util import strip_code  # noqa: E402

# 只看**相对**链接（http/https 与页内锚点不查）
LINK_RE = re.compile(r"\]\((?!https?://|#)([^)]+)\)")


def check(root: Path | str = Path(".")) -> list[str]:
    """返回问题列表（空 = 通过）。扫描 root 下的 *.md。"""
    root = Path(root)
    bad: list[str] = []
    for p in sorted(root.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        heads = re.findall(r"^## (.+)$", text, re.M)
        dup = [h for h in set(heads) if heads.count(h) > 1]
        if dup:
            bad.append(f"{p}: 重复章节 {dup}")
        # #64：`strip_code` 让反引号/围栏里的链接语法不被当真链接
        for m in LINK_RE.finditer(strip_code(text)):
            t = m.group(1).split("#")[0].strip()
            if t and not (p.parent / t).exists():
                bad.append(f"{p}: 死链 {t}")
    return bad


def main() -> int:
    problems = check()
    if problems:
        print("::error::Markdown 结构问题")
        for b in problems:
            print(b)
        return 1
    print("Markdown 结构自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
