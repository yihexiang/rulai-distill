#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docs/CLAIMS.md 的**核验器**（P0-4）。

对外声称（README / GUIDE / CAPABILITIES）必须满足三件事：

1. **有证据**：能指到一条命令或一个测试名；
2. **证据是真的**：那个测试**确实存在**（本脚本查`tests/e2e.py` 的注册表）；
3. **数字不过期**：CLAIMS.md 里写的数字与仓库现状一致（回归项数、缺陷条数、
   子命令数、交叉复核报告数…）。

**为什么要有这个脚本**：本项目最高频的病是「声称 ≠ 实际」——
文档里写"12张卡"而实际只有 9 张、写"2 张卡跑过交叉复核"而实际已经有 6 张报告，
都没有任何东西会红。本脚本让这类腐烂**变成 CI红**。

用法：
    python3 docs/verify_claims.py            # 核验并打印表格
    python3 docs/verify_claims.py --json     # 机器可读
退出码 0 = 全部声称有据且数字一致。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIMS_MD = ROOT / "docs" / "CLAIMS.md"


def registered_tests() -> set[str]:
    src = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    return set(re.findall(r"^\s+\(\"(?:[^\"]*)\",\s*(t_\w+)\)", src, re.M))


def count_registered_tests() -> int:
    src = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    return len(re.findall(r"^\s+\(\"[^\"]*\",\s*t_\w+\)", src, re.M))


def count_subcommands() -> int:
    """子命令数取 argparse 自己打印的那一行 choices——**不靠正则数缩进**。

    首版用 `^\\s{2,4}[a-z]...` 去数help 里的命令行，数出 0 个还不报错。
    正确做法：读 usage 里的 `{a,b,c}` choices 集合，那是 argparse 的权威输出。
    """
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "td.py"), "--help"],
                       capture_output=True, text=True)
    for line in p.stdout.splitlines():
        m = re.search(r"\{([a-z0-9,-]+)\}", line)
        if m and " " not in m.group(1):
            return len(m.group(1).split(","))
    return -1


def count_defects() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from tdlib.defects import DEFECTS
        return len(DEFECTS)
    except Exception:      # noqa: BLE001
        return -1


def parse_claims() -> list[dict]:
    """只解析「## 对外声称」那一节里的表格。

    首版扫全文所有表格，把「怎么数的」「逐卡证据」两张表也当成声称，
    于是 13 条凭空冒出来的"日期格式不对"。**校验器必须知道自己在校验什么**，
    否则它的报错会淹没真正的信号（这与 #54 同一个病：守卫太宽→真问题被淹）。
    """
    if not CLAIMS_MD.exists():
        return []
    text = CLAIMS_MD.read_text(encoding="utf-8")
    m = re.search(r"^## 对外声称\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        claim, evidence, checked = cells[0], cells[1], cells[2]
        if set(claim) <= set("-: ") or claim == "声称":
            continue
        rows.append({"claim": claim, "evidence": evidence, "checked": checked})
    return rows


def read_facts() -> dict[str, int]:
    """读 CLAIMS.md 里 `<!-- facts:begin -->` 段声明的数字。"""
    if not CLAIMS_MD.exists():
        return {}
    m = re.search(r"<!-- facts:begin -->(.*?)<!-- facts:end -->",
                  CLAIMS_MD.read_text(encoding="utf-8"), re.S)
    if not m:
        return {}
    out = {}
    for k, v in re.findall(r"^(\w+)\s*=\s*(\d+)\s*$", m.group(1), re.M):
        out[k] = int(v)
    return out


def sync_facts(facts: dict[str, int]) -> int:
    """把实际数字写回 facts 段、本文表格，以及其他文档里的回归项数。

    返回改动文件数。`--sync` 是**唯一**允许写这些数字的入口——
    人手填的下一轮就会腐烂（这正是这个脚本存在的理由）。
    """
    if not CLAIMS_MD.exists():
        return 0
    text = original = CLAIMS_MD.read_text(encoding="utf-8")
    block = "".join(f"{k} = {v}\n" for k, v in facts.items())
    text = re.sub(r"(<!-- facts:begin -->\s*```text\n).*?(\n```\s*<!-- facts:end -->)",
                  lambda m: m.group(1) + block.rstrip("\n") + m.group(2),
                  text, flags=re.S)
    # 本文表格：`| 回归项 | **100** |` 这类
    for label, key in (("回归项", "tests"), ("子命令", "subcommands"),
                       ("缺陷台账", "defects")):
        text = re.sub(rf"(\| {label} \| \*\*)\d+(\*\* \|)",
                      lambda m: m.group(1) + str(facts[key]) + m.group(2),
                      text)
    changed = 0
    if text != original:
        CLAIMS_MD.write_text(text, encoding="utf-8")
        changed += 1

    n = facts["tests"]
    for f in ("README.md", "README.en.md", "SKILL.md", "GUIDE.md",
              "CAPABILITIES.md", "OPEN-SOURCE-ASSESSMENT.md"):
        p = ROOT / f
        if not p.exists():
            continue
        body = before = p.read_text(encoding="utf-8")
        body = re.sub(r"(\d+)\s*项回归",
                      lambda m: f"{n} 项回归", body)
        body = re.sub(r"(\d+) 项回归、", f"{n} 项回归、", body)
        body = re.sub(r"regression-\d+%", f"regression-{n}%", body)
        body = re.sub(r"\b(\d+) regression tests\b", f"{n} regression tests", body)
        body = re.sub(r"\((\d+) tests,", f"({n} tests,", body)
        body = re.sub(r"（(\d+) 项，", f"（{n} 项，", body)
        body = re.sub(r"\*\*(9[0-9]|\d{3})\*\* 项回归", f"**{n}** 项回归", body)
        d = facts["defects"]
        body = re.sub(r"\*\*\d+\*\* self-found defects", f"**{d}** self-found defects", body)
        body = re.sub(r"\b\d+ of the \d+ are defects", f"{d} of the {d} are defects", body)
        body = re.sub(r"(\d+)\s*个缺陷", f"{d} 个缺陷", body)
        body = re.sub(r"(\d+)\s*条自身缺陷台账", f"{d} 条自身缺陷台账", body)
        if body != before:
            p.write_text(body, encoding="utf-8")
            changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sync", action="store_true",
                    help="把实际数字写回 facts 段与占位符（数字腐烂时用）")
    args = ap.parse_args()

    tests = registered_tests()
    facts = {
        "tests": count_registered_tests(),
        "subcommands": count_subcommands(),
        "defects": count_defects(),
    }
    if args.sync:
        sync_facts(facts)
        print(f"已同步：{facts}")

    nsubs, ndefects = facts["subcommands"], facts["defects"]

    claims = parse_claims()
    if not claims:
        print(f"❌ 没有找到 {CLAIMS_MD} 的「## 对外声称」段——"
              "声称台账本身是空的，等于没有台账", file=sys.stderr)
        return 1

    problems: list[str] = []
    for c in claims:
        # ① 证据里引用的测试名必须真实存在
        for t in re.findall(r"\bt_\w+", c["evidence"]):
            if t not in tests:
                problems.append(f"声称「{c['claim'][:40]}」引用的测试 `{t}` 不存在")
        # ② 证据必须非空，且不是"相信自己"
        if not c["evidence"] or c["evidence"] in ("—", "-", "无"):
            problems.append(f"声称「{c['claim'][:40]}」没有证据")
        # ③ 日期格式
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", c["checked"]):
            problems.append(
                f"声称「{c['claim'][:40]}」的核验日期 `{c['checked']}` 不是 YYYY-MM-DD")

    # ④ facts 段声明的数字必须与实际相等（**这一条首版是死代码**：
    #    它找的是 `{tests} = N`，而文档里根本没有这种写法 → 永远匹配不到，
    #    于是"数字腐烂"这一项看起来有检查、实际从不触发。
    #    #54 的同一个病：守卫写了但没钉住它该管的那一面。）
    declared = read_facts()
    if not declared:
        problems.append("CLAIMS.md 缺少 <!-- facts:begin --> 数字段")
    for key, actual in facts.items():
        if key not in declared:
            problems.append(f"facts 段缺 {key}（实际 {actual}）")
        elif declared[key] != actual:
            problems.append(
                f"CLAIMS.md 声明 {key}={declared[key]}，实际 {actual}"
                f"（数字腐烂了；跑 docs/verify_claims.py --sync 校准）")

    # ⑤ facts 段的数字必须在其他文档里同步出现，且**旧的数字不许残留**。
    #    （首版检查的是"正文里必须保留 {tests} 占位符"，可 `--sync` 的职责恰恰
    #    是把占位符换成实际值——于是这条检查被自己的同步机制判红。
    #    **守卫不能要求它守护的东西保持未完成状态**。）
    #
    #    顺带说明为什么必须扫**所有**文档：修「回归项数」时，
    #    README.en.md 里的缺陷数是**第三种写法**（62/48，中文版是 66/51）——
    #    三份文档各烂各的，只查中文那份就会漏。
    docs = {f: (ROOT / f).read_text(encoding="utf-8")
            for f in ("README.md", "README.en.md", "SKILL.md", "GUIDE.md",
                      "CAPABILITIES.md", "OPEN-SOURCE-ASSESSMENT.md")
            if (ROOT / f).exists()}
    stale: dict[str, set] = {}
    for f, body in docs.items():
        for n in set(re.findall(r"(\d+)\s*项回归", body)):
            if int(n) != facts["tests"]:
                stale.setdefault(f, set()).add(int(n))
        for n in set(re.findall(r"regression-(\d+)%", body)):
            if int(n) != facts["tests"]:
                stale.setdefault(f, set()).add(int(n))
        for n in set(re.findall(r"\*\*(\d+)\*\* self-found defects", body)):
            if int(n) != facts["defects"]:
                stale.setdefault(f, set()).add(int(n))
        for n in set(re.findall(r"(\d+) of the \d+ are defects", body)):
            if int(n) != facts["defects"]:
                stale.setdefault(f, set()).add(int(n))
        # 中文：「本项目把自己的 N 个缺陷」「← N 条自身缺陷台账」
        for n in set(re.findall(r"(\d+)\s*个缺陷", body)):
            if int(n) != facts["defects"]:
                stale.setdefault(f, set()).add(int(n))
        for n in set(re.findall(r"(\d+)\s*条自身缺陷台账", body)):
            if int(n) != facts["defects"]:
                stale.setdefault(f, set()).add(int(n))
    for f, ns in sorted(stale.items()):
        problems.append(
            f"{f} 里的数字 {sorted(ns)} 与实际不一致"
            f"（回归 {facts['tests']} · 缺陷 {facts['defects']}；"
            f"跑 --sync 后手工同步，或改文档）")

    out = {"facts": facts, "declared": declared,
           "claims": len(claims), "problems": problems}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"事实：回归 {facts['tests']} 项 · 子命令 {facts['subcommands']} 个"
              f" · 缺陷台账 {facts['defects']} 条")
        print(f"声称台账：{len(claims)} 条")
        if problems:
            print("\n❌ 问题：")
            for p in problems:
                print(f"· {p}")
        else:
            print("\n✅ 每条声称都有真实存在的证据，数字与仓库一致")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())