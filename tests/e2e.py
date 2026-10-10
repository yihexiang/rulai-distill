#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/e2e.py — rulai-distill 工具链端到端回归测试。

用法：
  python3 tests/e2e.py                 # 用当前解释器（验证零依赖可跑）
  python3 tests/e2e.py --tiktoken      # 额外验证 tiktoken 计量路径

覆盖：doctor / init / chunk(+缓存+索引) / transcript / research / validate / output-eval
      / gate / strategy / compile(pack+single) / 手改检测 / snapshot / rollback
      / trigger(build,record,score) / count / prompt / diff / impact / repair / patch / update

不依赖 pytest，失败即退出码非 0，并打印失败原因。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TD = ROOT / "scripts" / "td.py"

# --------------------------------------------------------------------------
# 外部工作区依赖登记册（P0-1c）
# --------------------------------------------------------------------------
# 规则（#65 的教训）：
#   1. **默认不依赖仓库外任何路径** —— git clone 后必须直接全绿。
#   2. 确实需要真实素材的测试，必须整段包在 `external_ws()` 守卫里：
#      它只在显式设 `RULAI_WORKSPACE=1` **且**路径存在时才跑，否则整条测试
#      报「未运行」而不是「通过」。
#   3. 每一条都登记在这里，`t_no_external_fixture_deps` 强制
#      「登记了就必须真的被守卫，守卫了才允许引用 ROOT.parent」。
# 允许引用：真实素材只在作者本机跑（CI 拿不到，也不该去抓）。
EXTERNAL_DEPS_WHITELIST = {
    "video-run/sources/arj7oStGLkU.en.srt": "t_verify_quotes_real_transcript",
    "video-run/skills/two-kinds-of-procrastination/SKILL.md":
        "t_no_unqualified_absence_claims / t_disclosure_completeness / "
        "t_disclosure_covers_uncovered",
    "video-run/eval/FROZEN.snapshot.json": "t_eval_freeze_integrity",
    "video-run/eval/style-decoys.md": "t_style_decoy_anonymity",
    "video-run/sources/arj7oStGLkU.en.transcript.md":
        "t_audit_coverage_runs / t_disclosure_covers_uncovered",
    "video-run/（整目录，t_real_sample_artifacts）": "t_real_sample_artifacts",
}

_ENV_HINT = ("未运行：需要作者工作区的真实素材（设 RULAI_WORKSPACE=1 且存在 ../video-run/）"
             "——这不是「通过」")


def external_ws(rel: str) -> Path | None:
    """返回仓库外素材路径；**不可用时返回 None**（调用方须如实报"未运行"）。

    这是唯一允许的外部依赖入口。用它替换裸的 `ROOT.parent / ...`，
    好处是「跳过」不再伪装成「通过」：调用方拿不到路径时会把该测试记为
    `SKIPPED` 并在结尾打印清单。
    """
    base = ROOT.parent if os.environ.get("RULAI_WORKSPACE") == "1" else None
    if base is None or not (base / rel).exists():
        return None
    return base / rel


SKIPPED: list[tuple[str, str]] = []


def skip_ws(test: str, what: str) -> None:
    """把「因缺外部素材而未运行」如实登记，结尾会打印，绝不冒充通过。"""
    SKIPPED.append((test, what))

PASS, FAIL = [], []


def run(args, expect: int | None = 0, cwd: Path | None = None):
    proc = subprocess.run([sys.executable, str(TD), *args], capture_output=True, text=True,
                          cwd=str(cwd) if cwd else None)
    if expect is not None and proc.returncode != expect:
        raise AssertionError(
            f"命令失败 td.py {' '.join(args)}\n期望 exit={expect} 实际 {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout[-1500:]}\n--- stderr ---\n{proc.stderr[-800:]}")
    return proc


def check(name: str, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAIL.append((name, str(e)))
        print(f"  ❌ {name}\n     {e}")
    except Exception as e:  # noqa: BLE001
        FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ❌ {name}\n     {type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# 素材生成
# --------------------------------------------------------------------------
BOOK = """# 第一章 问题的起点

""" + "矛盾是事物发展的根本动力。" * 60 + """

## 第一节 为什么会这样

""" + "任何判断都依赖前提，前提变了结论就变了。" * 50 + """

# 第二章 抓主要矛盾

""" + "众多矛盾之中必有一个起主导作用的矛盾，抓住了它就抓住了全局。" * 55 + """

## 第二节 抓总的、主要的

""" + "任何过程都有许多矛盾，矛盾中有主要和次要。" * 45 + """

# 第三章 矛盾转化

""" + "事物的发展是矛盾双方相互转化的过程。" * 50 + """
"""


def make_srt(path: Path):
    """生成测试字幕：含滚动重复、说话人、无意义短行。"""
    def ts(ms: int) -> str:
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, msec = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{msec:03d}"

    cues = [(0, "今天我们聊一个很多人搞反的问题", 4000),
            (500, "今天我们聊一个很多人搞反的问题", 4500),   # 滚动重复，应被去重
            (6000, "不是先看谁的声音大 而是先看谁错了影响最大", 9000),
            (7000, "大部分人把这件事做反了", 12000),
            (12000, "这不是玄学 是一套可以练习的判断方式", 16000),
            (30000, "好 今天就到这里 下期继续", 32000)]
    blocks = [f"{i}\n{ts(s)} --> {ts(e)}\n{t}\n" for i, (s, t, e) in enumerate(cues, 1)]
    path.write_text("\n".join(blocks), encoding="utf-8")


CARD = """---
name: {name}
title: 抓主要矛盾
description: |
  在多个矛盾同时存在时，判断哪个是主导矛盾，从而决定资源与注意力的分配顺序。
  适用：多目标冲突、多方诉求打架、优先级反复摇摆的场景。
  不做：单一线索的简单排序；已经确认根因后的执行修复。
source_material: 示例书
source_locator: 第二章
capability_type: framework
promotion: promoted
contrasts_with: [{other}]
---

# 抓主要矛盾

## R — Reading

> 「众多矛盾之中必有一个起主导作用的矛盾。」
> —— 示例书 第二章

## I — Interpretation

1. 存在多个矛盾 → 找出影响全局的那个 → 资源优先给它 → 其余矛盾退居次要

**适用前提**：矛盾数 ≥2 且确实相互影响。

## A1 — Past

**案例**：多线同时告急时的排序 —— 先修影响全局的那条，其余暂缓。

## A2 — Future

**触发情境**：多个需求同时抢资源。

**语言信号**：「这几件事我先做哪个」

**与邻近能力的区分**：

| 邻近能力 | 本卡 | 对方 |
|---|---|---|
| {other} | 判断主次 | 排执行顺序 |

## E — Execution

**Step 1 · 列出矛盾**
- 做什么：把所有同时存在的矛盾列出来
- 完成标准：形成不超过 7 条的清单
- ⏸️ 检查点：每条都能说清「它错了会怎样」

**Step 2 · 判定主导**
- 做什么：找出影响范围最大的那条
- 完成标准：能写出一句「它错了会怎样，其它都还能救」
- ⏸️ 检查点：出现两条势均力敌时说明前提没列全

## B — Boundary

**不适用**：只有一个矛盾时直接做。

**失败模式**：

| 症状 | 根因 | 纠正 |
|---|---|---|
| 把声音大的当主导 | 按发言频次而非影响面排序 | 回到 Step 2 判定 |
"""

FIDELITY_MD = """---
eval_mode: dual-agent
answerer: agent-A
graders: [agent-B, agent-C]
---
# FIDELITY 报告

## 维度 1 · 立场/结论一致性（30 分）
| # | 问题 | 卡回答 | 一致 | 得分 |
|---|---|---|---|---|
| Q1 | 判断主次的依据 | 影响面 | ✅ | 10 |
| Q2 | 跨技能混淆题 | 交给对方 | ✅ | 9 |
| Q3 | 前提缺失时 | 先补前提 | ✅ | 7 |
小计：26/30

## 维度 2 · 风格辨识度（20 分）
得分：15/20

## 维度 3 · 边缘诚实度（20 分）
得分：14/20

## 维度 4 · 来源透明度（15 分）
得分：12/15

## 维度 5 · 结构完整度（15 分）
得分：13/15

| 维度 | 得分 |
|---|---|
| **总分** | **80** |
| **等级** | B |

## 最弱项

维度 4 来源透明度：卡片对二级文献的引用不够明确。
"""


def setup(tmp: Path) -> Path:
    """构建一个可发布的 bundle。"""
    b = tmp / "bundle"
    (b / "skills").mkdir(parents=True)
    (b / "skills" / "major-contradiction").mkdir(parents=True)
    (b / "skills" / "sequence-execution").mkdir(parents=True)
    (b / "skills" / "major-contradiction" / "SKILL.md").write_text(
        CARD.format(name="major-contradiction", other="sequence-execution"), encoding="utf-8")
    (b / "skills" / "sequence-execution" / "SKILL.md").write_text(
        CARD.format(name="sequence-execution", other="major-contradiction"), encoding="utf-8")
    (b / "skills" / "major-contradiction" / "FIDELITY.md").write_text(FIDELITY_MD, encoding="utf-8")
    (b / "skills" / "sequence-execution" / "FIDELITY.md").write_text(FIDELITY_MD, encoding="utf-8")
    write = lambda p, d: (Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"))
    write(b / "bundle.json", {
        "schema": "rulai-distill/bundle/v1", "version": "0.2.0",
        "source": {"material": "示例书", "material_type": "book", "coverage": 100},
        "skills": [
            {"slug": "major-contradiction", "role": "promoted", "promotion": "promoted",
             "src": "skills/major-contradiction/SKILL.md"},
            {"slug": "sequence-execution", "role": "promoted", "promotion": "promoted",
             "src": "skills/sequence-execution/SKILL.md"},
        ],
        "publish": {"allow_grade_below": "B"},
    })
    return b


# --------------------------------------------------------------------------
# 测试项
# --------------------------------------------------------------------------
def t_doctor():
    out = run(["doctor"]).stdout
    assert "能力矩阵" in out and "cangjie" in out and "nuwa" in out


def t_init():
    with tempfile.TemporaryDirectory() as d:
        run(["init", f"{d}/b"])
        assert (Path(d) / "b" / "bundle.json").exists()
        lanes = list((Path(d) / "b" / "references" / "research").glob("*.md"))
        assert len(lanes) == 6, f"六路调研骨架应为 6 个文件，实际 {len(lanes)}"
        run(["validate", f"{d}/b"])


def t_chunk():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "book.md"
        src.write_text(BOOK, encoding="utf-8")
        out = run(["chunk", str(src)]).stdout
        sidecar = src.with_suffix(".md.td")
        chunks = [json.loads(l) for l in (sidecar / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(chunks) >= 3, f"应按标题切出多块，实际 {len(chunks)}"
        assert all(c["chars"] <= 4000 + 200 for c in chunks), "存在超限块"
        assert any(c["heading_path"] for c in chunks), "heading_path 未保留"
        # 缓存命中
        p2 = run(["chunk", str(src)]).stdout
        assert "命中确定性缓存" in p2, "第二次运行未命中缓存"
        # 索引检索
        o3 = run(["index", str(sidecar), "--grep", "主要矛盾"]).stdout
        assert "命中" in o3
        # 2026-10-07（#49）：`index --grep` 原来只按**标题**检索，正文里的词搜不到，
        # 而 `chunk` 的输出恰恰提示「下一步：index --grep <关键词>」——**承诺了做不到**。
        # 「前提」只出现在正文、任何标题里都没有，必须能命中。
        o4 = run(["index", str(sidecar), "--grep", "前提"]).stdout
        assert "命中 0 块" not in o4, f"正文关键词检索不到（只搜了标题）：{o4.strip()}"
        assert (sidecar / "index.json").exists() and (sidecar / "document.json").exists()


def t_chunk_oversize():
    """单段超长时应按句边界二次切分而不是硬切丢内容。"""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "long.md"
        src.write_text("# 标题\n\n" + "这是一个很长的句子。" * 900 + "\n", encoding="utf-8")
        run(["chunk", str(src), "--max-chars", "1000"])
        sidecar = src.with_suffix(".md.td")
        chunks = [json.loads(l) for l in (sidecar / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        joined = "".join(c["text"] for c in chunks)
        assert "这是一个很长的句子。" in joined, "二次切分丢了内容"
        assert len(chunks) >= 10, f"超长段应被切多块，实际 {len(chunks)}"


def t_transcript():
    with tempfile.TemporaryDirectory() as d:
        srt = Path(d) / "a.srt"
        make_srt(srt)
        run(["transcript", str(srt)])
        md = srt.with_suffix(".transcript.md")
        assert md.exists(), "未生成逐字稿"
        text = md.read_text(encoding="utf-8")
        assert "[00:00:00" in text, "缺时间戳"
        assert text.count("今天我们聊一个很多人搞反的问题") == 1, "滚动重复未被去重"
        data = json.loads(srt.with_suffix(".transcript.json").read_text(encoding="utf-8"))
        assert data["dedup_dropped"] >= 1
        assert data["paragraph_count"] >= 2
        # 多文件合并
        srt2 = Path(d) / "b.srt"
        make_srt(srt2)
        run(["transcript", str(srt), str(srt2), "--merge", "--out", f"{d}/merged"])
        assert (Path(d) / "merged.transcript.md").exists()


def t_research():
    with tempfile.TemporaryDirectory() as d:
        run(["research", "init", d, "--person", "测试人物"])
        rd = Path(d) / "references" / "research"
        (rd / "01-writings.md").write_text(
            "---\nlane: 01\n---\n# 01\n\n"
            "- **[一手]** 他强调抓主要矛盾 —— 出处：《矛盾论》1937年\n"
            "- **[一手]** 他强调抓主要矛盾 —— 出处：《矛盾论》1937年\n", encoding="utf-8")
        (rd / "04-external-views.md").write_text(
            "---\nlane: 04\n---\n# 04\n\n"
            "- **[二手]** 有人批评他的方法过于机械 —— 出处：某传记\n"
            "- **[一手]** 他在 1958 年承认这条批评有道理 —— 出处：1958 年讲话\n",
            encoding="utf-8")
        (rd / "05-decisions.md").write_text(
            "---\nlane: 05\n---\n# 05\n\n"
            "- **[一手]** 他在 1958 年承认这条批评没有道理 —— 出处：另一次讲话\n",
            encoding="utf-8")
        out = f"{d}/merged.md"
        run(["research", "merge", str(rd / "01-writings.md"), str(rd / "04-external-views.md"),
             str(rd / "05-decisions.md"), "--out", out])
        text = Path(out).read_text(encoding="utf-8")
        assert "去重 2" in text, f"完全重复与近似重复都应去重：\n{text[:500]}"
        rep = json.loads(Path(out).with_suffix(".merge.json").read_text(encoding="utf-8"))
        assert rep["kept"] == 3, f"应保留 3 条，实际 {rep['kept']}"
        assert 0.6 <= rep["one_hand_ratio"] <= 0.7, rep["one_hand_ratio"]
        assert len(rep["conflicts"]) == 1, f"相似但互相矛盾的一手条目应被标记：{rep['conflicts']}"
        assert "冲突" in text, "合并稿缺少冲突段落"


def t_self_validate_clean_and_doc_structure():
    """仓库自身必须通过 CI 的那两步：`td.py validate .` 与文档结构自检。

    2026-10-10（#64）：这两步此前**只存在于 CI**（pipeline-check / docs-check），
    本地回归跑不到。我在 CONSTRAINTS.md 的台账里举例写了 `[配套](../b/)`（反引号里），
    本地 96 项全绿、CI 两处红。与 #51 同类：**改了文件却没按用户的路径跑一遍**。
    现在把这两步钉进回归，本地就能拦住。

    附带守住 #64 的根因：**代码段里的链接语法不是链接**。
    """
    # ① 仓库自身 validate：0 error（CI pipeline-check 的一步）
    p = run(["validate", "."], cwd=ROOT)
    assert "error 0" in p.stdout, f"仓库自身 validate 不干净：\n{p.stdout[-1200:]}"

    # ② 文档结构自检（CI docs-check 的一步）
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "doc_structure_check", ROOT / "tests" / "doc_structure_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bad = mod.check(ROOT)
    assert not bad, f"文档结构问题：{bad}"

    # ③ 根因守卫：反引号/围栏里的链接语法不得被当成真链接
    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        (wd / "x.md").write_text(
            "举例：写 `[配套](../b/)` 就是相对链接；下面这个是代码块里的：\n\n"
            "```\n[也不该算](../nope/)\n```\n", encoding="utf-8")
        assert not mod.check(wd), "代码段里的链接语法被当成了真链接"
        # 反方向：正文里真写了个不存在的链接，仍须报出
        (wd / "y.md").write_text("见 [不存在](nope/missing.md)。\n", encoding="utf-8")
        assert mod.check(wd), "真死链必须仍被报出"


def t_dead_link_relative_within_root():
    """#63：**正常相对链接**（同级技能 / 回包根）不得被判「路径逃逸」。

    死链检查此前写成 `safe_target(md.parent, tgt)`——把"根"当成了"该 md 所在的目录"，
    于是 `skills/a/README.md` 里写 `../b/`（同级技能，完全合法且仍在包内）会被报
    「路径逃逸出根目录」。实测：给 guoxue-skills 补四份技能介绍后，validate 一次报出
    **27 条假阳性**，把一份正常文档判成"不可发布"——**假阳性会逼人删掉正确的链接**。

    反方向同时守住：真逃出校验根、真死链，都必须继续报。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import validate as V

    def card(name: str) -> str:
        return ("---\n"
                f"name: {name}\n"
                f"description: 用于验证相对链接判定的探针卡，描述写够长度。不做：通用问答。\n"
                "source_locator: 探针\n"
                "---\n\n"
                "# E — 可执行步骤\n\n**Step 1 · 做**\n\n完成标准：做完。\n\n"
                "# B — 边界\n\n失败模式：无。\n")

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        for slug in ("a", "b"):
            (base / "skills" / slug).mkdir(parents=True)
            (base / "skills" / slug / "SKILL.md").write_text(card(slug), encoding="utf-8")
        (base / "README.md").write_text(
            "# 包首页\n\n见 [a](skills/a/) 与 [b](skills/b/SKILL.md)。\n", encoding="utf-8")
        # 兄弟技能 + 回包根：两种合法的 `../` 链接
        (base / "skills" / "a" / "README.md").write_text(
            "# a 的说明\n\n[← 回首页](../../README.md) · [配套](../b/)\n", encoding="utf-8")
        problems, _ = V.validate_path(base)
        errs = [p for p in problems if p[0] == "error"]
        assert not errs, f"合法相对链接被判错（假阳性）：{errs}"

    with tempfile.TemporaryDirectory() as d2:
        base2 = Path(d2)
        (base2 / "README.md").write_text("# x\n\n[逃出去](../../../etc/passwd)\n",
                                        encoding="utf-8")
        problems2, _ = V.validate_path(base2)
        assert any("逃逸" in p[2] for p in problems2), \
            f"逃出校验根的链接必须仍被拒绝：{problems2}"
        (base2 / "README.md").write_text("# x\n\n[不存在](nope/missing.md)\n", encoding="utf-8")
        problems3, _ = V.validate_path(base2)
        assert any("死链" in p[2] for p in problems3), f"真死链必须仍被报出：{problems3}"


def t_validate_bundle():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = run(["validate", str(b)]).stdout
        assert "error 0" in out, out


def t_validate_catches():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        bad = b / "skills" / "bad-persona" / "SKILL.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("---\nname: bad-persona\ndescription: 人物卡\nsubject_type: person\n---\n# 坏卡\n"
                       "## 我看问题的方式\n\nStep 1. 先看全局\n第一步：再拆\n1. 排序\n", encoding="utf-8")
        proc = run(["validate", str(b)], expect=1)
        o = proc.stdout
        assert "认知植入" in o, "未检出首句声明"
        assert "显式步骤" in o, "未检出显式步骤"
        no_std = b / "skills" / "no-std" / "SKILL.md"
        no_std.parent.mkdir(parents=True)
        no_std.write_text("---\nname: no-std\ndescription: x\n---\n# t\n## E — Execution\n做事\n## B — Boundary\n无\n",
                          encoding="utf-8")
        o2 = run(["validate", str(b)], expect=1).stdout
        assert "完成标准" in o2, "未检出 E 段缺完成标准"
        assert "失败模式" in o2, "未检出 B 段缺失败模式"


def t_output_eval():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = run(["output-eval", str(b / "skills/major-contradiction/SKILL.md")]).stdout
        assert "六段：齐全" in out, out
        assert "引语 1 条" in out, out


def t_gate():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        rep = b / "skills/major-contradiction/FIDELITY.md"
        # grade 解析路径：用 --allow-single-scorer 关掉交叉复核默认要求，专测 grade 判定
        out = run(["gate", str(rep), "--min", "B", "--allow-single-scorer"]).stdout
        assert "总分 80" in out and "通过门槛" in out, out
        assert "consistency=26" in out, "分项解析失败"
        run(["gate", str(rep), "--min", "A", "--allow-single-scorer"], expect=1)
        # 新默认（复审 P0）：不给交叉复核记录就拒绝——单评分不构成质检结论
        o_no = run(["gate", str(rep), "--min", "B"], expect=1).stdout
        assert "交叉复核" in o_no, o_no
        # fallback 自测降级
        fb = Path(d) / "fb.md"
        fb.write_text("# 报告\n\neval_mode: fallback-self\n\n"
                      "## 维度 1 · 立场/结论一致性（30 分）\n小计：30/30\n"
                      "## 维度 2 · 风格辨识度（20 分）\n得分：20/20\n"
                      "## 维度 3 · 边缘诚实度（20 分）\n得分：20/20\n"
                      "## 维度 4 · 来源透明度（15 分）\n得分：15/15\n"
                      "## 维度 5 · 结构完整度（15 分）\n得分：15/15\n"
                      "**总分** 100\n", encoding="utf-8")
        o = run(["gate", str(fb), "--allow-single-scorer"], expect=1).stdout
        assert "风格辨识度" in o and ("作废" in o or "style=0" in o), o
        # 非双 Agent 默认不得通过
        assert "非双 Agent" in run(["gate", str(fb), "--allow-single-scorer"], expect=1).stdout
        # 显式 allow-fallback 才放行
        assert "通过门槛" in run(["gate", str(fb), "--allow-fallback", "--allow-single-scorer"]).stdout


def t_gate_requires_cross_review():
    """复审 P0：gate **默认要求交叉复核记录**（≥2 个独立评分者）。

    此前 --scores 是 opt-in：不给就静默按单评分放行——等于"质检靠人记得加参数"。
    现在默认拒绝，除非显式 --allow-single-scorer，或报告内嵌 graders（eval-kit 产出）。
    """
    with tempfile.TemporaryDirectory() as d:
        bare = Path(d) / "bare.json"
        bare.write_text(json.dumps({
            "schema": "rulai-distill/fidelity/v1", "subject": "bare", "eval_mode": "dual-agent",
            "dimensions": {"consistency": 26, "style": 17, "edge_honesty": 18,
                           "source_transparency": 13, "structure": 14},
            "total": 88, "grade": "A"}, ensure_ascii=False), encoding="utf-8")
        # 1) 默认拒绝（缺交叉复核）
        o = run(["gate", str(bare), "--min", "A"], expect=1).stdout
        assert "交叉复核" in o, o
        # 2) 显式 --scores 提供交叉复核 → 放行
        assert "通过门槛" in run(["gate", str(bare), "--min", "A", "--scores", "90,88"]).stdout
        # 3) 分差 >10 → 拒绝（哪怕总分够）
        o3 = run(["gate", str(bare), "--min", "A", "--scores", "95,70"], expect=1).stdout
        assert "交叉复核" in o3, o3
        # 4) 显式豁免单评分 → 放行
        assert "通过门槛" in run(["gate", str(bare), "--min", "A", "--allow-single-scorer"]).stdout


def t_eval_kit():
    """复审 P0：eval-kit 把 FIDELITY 独立质检闭环产品化。

    init 出题库/模板；check 汇总 ≥2 评分 → 交叉复核 → 产出**可被 fidelity 契约校验**的
    FIDELITY JSON；gate 能直接吃它（内嵌 graders）。空集/单评分/分差过大一律不判通过。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts, evalkit
    card = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md"
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        kit = base / "kit"
        evalkit.build_kit(card, kit)
        for f in ("questions.json", "answers.template.json", "scores.template.json", "README.md"):
            assert (kit / f).exists(), f"eval-kit 未生成 {f}"
        q = json.loads((kit / "questions.json").read_text(encoding="utf-8"))
        assert q["needs_human_augmentation"] is True, "题库必须显式标注需人工补题（不假装自动够用）"
        assert any(x["kind"] == "edge_honesty" for x in q["questions"]), \
            "题库必须含 edge_honesty 维度——那是唯一能抓出『编造』的一维"

        def write_scores(name, grader, dims):
            p = base / name
            p.write_text(json.dumps({"schema": "rulai-distill/eval-kit-scores@1", "grader": grader,
                                     "dimensions": {k: {"score": v, "max": m}
                                                    for (k, v), m in zip(dims.items(), [30, 20, 20, 15, 15])}},
                                    ensure_ascii=False), encoding="utf-8")
            return p

        ans = base / "answers.json"
        ans.write_text(json.dumps({"schema": "rulai-distill/eval-kit-answers@1",
                                   "answerer": "answerer-A",
                                   "answers": [{"id": x["id"], "answer": "回答"} for x in q["questions"]]},
                                  ensure_ascii=False), encoding="utf-8")
        dims1 = {"consistency": 24, "style": 15, "edge_honesty": 17,
                 "source_transparency": 12, "structure": 12}
        dims2 = {"consistency": 22, "style": 14, "edge_honesty": 16,
                 "source_transparency": 11, "structure": 13}
        dims3 = {"consistency": 30, "style": 20, "edge_honesty": 20,
                 "source_transparency": 15, "structure": 15}
        s1 = write_scores("s1.json", "grader-1", dims1)
        s2 = write_scores("s2.json", "grader-2", dims2)
        s3 = write_scores("s3.json", "grader-3", dims3)

        # 正常：2 评分分差 4 → pass，产物合 fidelity 契约
        r = evalkit.check(ans, [s1, s2], subject="demo")
        assert r["verdict"] == "pass", (r["verdict"], r["errors"], r["cross"])
        assert r["report"]["eval_mode"] == "dual-agent"
        assert r["report"]["graders"] == ["grader-1", "grader-2"]
        vres = contracts.validate_local("fidelity", r["report"])
        assert vres["ok"], f"eval-kit 产物不合 fidelity 契约：{vres['errors']}"

        # 单评分 → 不构成交叉复核 → fail
        r1 = evalkit.check(ans, [s1], subject="demo")
        assert r1["verdict"] == "fail" and r1["cross"]["verdict"] == "insufficient_scorers", r1["cross"]

        # 分差 >10 → fail（评分分歧过大）
        r2 = evalkit.check(ans, [s1, s3], subject="demo")
        assert r2["verdict"] == "fail" and r2["cross"]["spread"] == 20, r2["cross"]

        # 答题者/评分者未填（仍是模板占位） → 报错，不得据此下结论
        bad = base / "bad.json"
        bad.write_text(json.dumps({"schema": "x", "answerer": "【必填】",
                                   "answers": [{"id": "q", "answer": "【填】"}]},
                                  ensure_ascii=False), encoding="utf-8")
        r3 = evalkit.check(bad, [s1, s2])
        assert r3["errors"] and r3["verdict"] == "fail", r3

        # CLI 端到端：init → check → gate 放行（gate 走报告内嵌的交叉复核）
        kit2 = base / "kit2"
        run(["eval-kit", "init", str(card), "--out", str(kit2)])
        out = base / "FIDELITY.json"
        run(["eval-kit", "check", "--answers", str(ans), "--scores", str(s1), str(s2),
             "--subject", "demo", "--out", str(out)])
        assert out.exists(), "eval-kit check 未产出 FIDELITY JSON"
        assert "通过门槛" in run(["gate", str(out), "--min", "B"]).stdout, \
            "gate 应能直接消费 eval-kit 产出的报告（内嵌交叉复核）"


def t_lint_quotes():
    """复审 P1：lint-quotes 引语体检器（简繁不一致 / 省略号 / 归属可疑）。

    这三条是 guoxue 现场用过的检查里最确定的。纪律：glyph 只在**找到近似匹配**时报
    （不越界抢 verify-quotes 的活）；ellipsis/authorship 是启发式，只提示。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import lintquotes as L
    corpus = "【第1段】兵者，國之大事，死生之地，存亡之道，不可不察也。凡此五者，將莫不聞，知之者勝，不知者不勝。"
    cc = L._clean(corpus)
    sents = [L._clean(x) for x in re.split(r"[。！？；\n]+", corpus) if len(L._clean(x)) >= 8]

    # 1) 简繁不一致：卡片简体、语料繁体 → glyph，且报出差异字形对
    g = L.lint_corpus("「知之者胜，不知者不胜」", cc, sents)
    assert g and g["kind"] == "glyph", f"简繁不一致应判 glyph：{g}"
    assert ("胜", "勝") in g["pairs"], f"应报出 胜→勝 差异对：{g.get('pairs')}"

    # 2) 省略号：非逐字原文 → ellipsis
    e = L.lint_corpus("「主孰有道？将孰有能？…？」", cc, sents)
    assert e and e["kind"] == "ellipsis", f"含省略号应判 ellipsis：{e}"

    # 3) 归属可疑：语料里没有 + 作者行文特征 → authorship
    a = L.lint_corpus("「该选 A 还是 B，我两边都说得通」", cc, sents)
    assert a and a["kind"] == "authorship", f"疑似作者举例应判 authorship：{a}"

    # 4) 规范引语（与语料逐字一致，繁体）→ 无发现（不许误报健康引语）
    ok_ = L.lint_corpus("「凡此五者，將莫不聞，知之者勝，不知者不勝」", cc, sents)
    assert ok_ is None, f"逐字一致的繁体引语不该报：{ok_}"

    # 5) 空集守卫：卡片含引语候选但全在元描述框内 → vacuous，不判通过
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "meta.md"
        p.write_text("归属拆分：「这是足够长的引语候选文本，用来触发空集守卫」→ 作者\n",
                     encoding="utf-8")
        rep = L.lint(p, {"c": corpus})
        assert rep["vacuous"] is True and rep["verdict"] == "vacuous", rep

    # 6) 真实样本卡（本轮已把引语统一成语料的繁体字形）：应干净、判 pass。
    #    这条同时是「作者举例框（语言信号）里的示范句不算引语」的守卫。
    card = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md"
    src = ROOT / "examples/sample-bundle/sources/sunzi-ji.txt"
    r = L.lint(card, {"sunzi": src.read_text(encoding="utf-8")})
    assert r["verdict"] == "pass", f"样本卡修好后应判 pass：{r['by_kind']} {r['findings'][:2]}"
    assert r["by_kind"].get("glyph", 0) == 0, f"样本卡不应再有用字不一致：{r['by_kind']}"

    # 7) CLI：干净卡 → exit 0（带/不带语料都是）
    run(["lint-quotes", str(card), "--corpus", str(src)], expect=0)
    run(["lint-quotes", str(card)], expect=0)
    # 7b) CLI glyph 判失败路径（临时卡：正文简体引语 vs 繁体语料）
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.md"
        bad.write_text("> 「兵者，國之大事，死生之地，存亡之道，不可不察也。」\n"
                       "> —— 《孫子兵法·計篇》第1段\n\n"
                       "他说「知之者胜，不知者不胜」。\n", encoding="utf-8")
        run(["lint-quotes", str(bad), "--corpus", str(src)], expect=1)


def t_lint_quotes_technical_and_sectional():
    """#62：①引号里的**文件名/通配**不是引语（工具自己的假阳性）；
    ②卡片已**显式标注为节引**时，省略号提示必须停（工具给的两种处置之一，照做就该过）。

    实测：zhouyi-yili 卡写 `任一返回"未找到 references/…md"时…`，
    被体检器当成"含省略号的引语"报了出来；另 geju-yunshi 的合法节引在标注后仍被反复提示。
    **工具给的建议，工具自己必须认。**
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import lintquotes as L

    # ① 技术 token 必须被跳过，且单独计数（不静默）
    assert L._looks_like_path("未找到 references/…md"), "文件名形态应判为技术 token"
    assert L._looks_like_path("见 scripts/td.py"), "路径形态应判为技术 token"
    assert L._looks_like_path("https://example.com/x"), "URL 应判为技术 token"
    assert not L._looks_like_path("孩子/新事物如何启蒙"), \
        "中文夹斜杠的正文不得被误杀（假阳性比漏报更坏）"

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "card.md"
        p.write_text(
            "任一返回\"未找到 references/…md\"时，如实说本技能包不完整。\n"
            "再看「孩子/新事物如何启蒙」这个中文短语（含斜杠，但仍是正文）。\n",
            encoding="utf-8")
        rep = L.lint(p, {"c": "与上面无关的语料内容，用于让体检器有语料可查。"})
        kinds = {f["kind"] for f in rep["findings"]}
        assert "ellipsis" not in kinds, f"技术 token 不该报省略号：{rep['findings']}"
        assert rep["technical_tokens_skipped"] >= 1, rep
        assert rep["quotes_checked"] >= 1, f"中文正文里的引语仍须被检查：{rep}"

    # ② 已标注「节引」的引语不再提示省略号；未标注的仍提示
    with tempfile.TemporaryDirectory() as d:
        marked = Path(d) / "marked.md"
        marked.write_text(
            "> src-01 §1 「开头逐字……结尾逐字。」（**节引**：省略号处为原文省略）\n",
            encoding="utf-8")
        r1 = L.lint(marked, {})
        assert not [f for f in r1["findings"] if f["kind"] == "ellipsis"], \
            f"已标注节引不该再提示：{r1['findings']}"
        unmarked = Path(d) / "unmarked.md"
        unmarked.write_text("> src-01 §1 「开头逐字……结尾逐字。」\n", encoding="utf-8")
        r2 = L.lint(unmarked, {})
        assert [f for f in r2["findings"] if f["kind"] == "ellipsis"], \
            "未标注的省略号仍须提示"


def t_g1_evalkit_hardening():
    """复审 G1：①失败产物不得过 gate；②同名评分者不算独立复核。

    实测两次 exit=0 的翻车：空答题产物 / 同名评分产物都能过 gate；grader-1 ×2 被当
    2 个独立评分者。修法：唯一评分者校验 + 失败写 .rejected + blocking_issues 一票否决。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evalkit, fidelity as F
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)

        def sc(name, grader, dims):
            p = base / name
            p.write_text(json.dumps({"grader": grader, "dimensions": {
                k: {"score": v, "max": m} for (k, v), m in zip(dims.items(), [30, 20, 20, 15, 15])}},
                ensure_ascii=False), encoding="utf-8")
            return p

        dimsA = {"consistency": 24, "style": 15, "edge_honesty": 17,
                 "source_transparency": 12, "structure": 12}
        dimsB = {"consistency": 22, "style": 14, "edge_honesty": 16,
                 "source_transparency": 11, "structure": 13}
        ans = base / "a.json"
        ans.write_text(json.dumps({"answerer": "answerer-A",
                                   "answers": [{"id": "q1", "answer": "x"}]}, ensure_ascii=False),
                       encoding="utf-8")
        s1 = sc("s1.json", "grader-1", dimsA)
        s2dup = sc("s2dup.json", "grader-1", dimsB)   # 与 s1 同名 → 不算独立

        r = evalkit.check(ans, [s1, s2dup])
        assert r["verdict"] == "fail", f"同名评分者不得放行：{r}"
        assert any("重复" in e for e in r["errors"]), r["errors"]
        assert r["unique_graders"] == 1, r

        # blocking_issues → gate 一票否决（fail 产物即便存在也放行不了）
        rep = {"total": 90, "grade": "A", "eval_mode": "dual-agent",
               "dimensions": {"consistency": 28, "style": 18, "edge_honesty": 18,
                              "source_transparency": 13, "structure": 13},
               "blocking_issues": ["评测未通过：评分分歧过大"]}
        passed, reasons = F.gate(rep, "A")
        assert not passed and any("blocking_issues" in x for x in reasons), reasons

        # 失败时 CLI 写 .rejected，不写普通 out
        out = base / "FIDELITY.json"
        run(["eval-kit", "check", "--answers", str(ans), "--scores", str(s1), str(s2dup),
             "--out", str(out)], expect=1)
        assert not out.exists(), "失败不得写出普通产物（否则照样能喂给 gate）"
        assert (base / "FIDELITY.rejected.json").exists(), "应写出 .rejected.json 供排查"

        # 复审 #3（G1 残余）：**errors 类失败**（空答题）产物若改名当正常报告，gate 必须仍拒。
        # 此前这种产物的 blocking_issues 为空 → gate 放行（实测 exit 0）。
        s2 = sc("s2.json", "grader-2", dimsB)      # 与 s1 不同名 → 交叉复核本身没问题
        empty_ans = base / "empty.json"
        empty_ans.write_text(json.dumps({"answerer": "answerer-A", "answers": []},
                                        ensure_ascii=False), encoding="utf-8")
        rej = base / "EMPTY.rejected.json"
        run(["eval-kit", "check", "--answers", str(empty_ans), "--scores", str(s1), str(s2),
             "--out", str(base / "EMPTY.json")], expect=1)
        data = json.loads(rej.read_text(encoding="utf-8"))
        assert data.get("blocking_issues"), f"errors 类失败必须并入 blocking_issues：{data}"
        assert data.get("verdict") == "fail", f"失败产物必须带 verdict=fail：{data}"
        norm = base / "renamed-as-normal.json"    # 冒充正常报告
        os.replace(rej, norm)
        g = run(["gate", str(norm), "--min", "A"], expect=1)
        assert ("verdict=fail" in g.stdout) or ("blocking_issues" in g.stdout), \
            f"改名冒充的报告必须仍被拒：{g.stdout}"


def t_validate_exempts_aux_docs():
    """复审：技能目录根级辅助文档（VERIFY.md/COVERAGE.md，无 frontmatter）不得被当卡片。

    guoxue zhouyi 实测：VERIFY.md / COVERAGE.md 被当卡片 → error 6「不允许发布」。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import validate as V
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        sk = base / "skills" / "demo"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text(
            "---\nname: demo\ndescription: 用于演示辅助文档豁免。不做：通用问答。\n---\n\n"
            "# E — 可执行步骤\n\n**Step 1 · 做**\n\n完成标准：做完。\n\n"
            "# B — 边界\n\n失败模式：无。\n", encoding="utf-8")
        (sk / "VERIFY.md").write_text("# VERIFY · demo\n\n> 核验记录，无 frontmatter。\n",
                                      encoding="utf-8")
        (sk / "COVERAGE.md").write_text("# COVERAGE · demo\n\n> 覆盖审计，无 frontmatter。\n",
                                        encoding="utf-8")
        problems, stats = V.validate_path(base)
    errs = [p for p in problems if p[0] == "error"]
    bad = [p for p in errs if "VERIFY" in p[1] or "COVERAGE" in p[1]]
    assert not bad, f"根级辅助文档不应按卡片校验：{bad}"
    assert stats["cards"] == 1, f"只应把 SKILL.md 当卡片：{stats}"


def t_validate_flat_layout():
    """复审 #4：扁平布局 `skills/*.md` **恒为卡片**——不得因无 frontmatter 被静默跳过。

    实测：`skills/only-card.md`（无 frontmatter）被归为"文档"→ **完全不校验**（免检通行证）。
    同时守住反方向：嵌套布局的技能目录根级辅助文档（skills/<slug>/VERIFY.md）仍应归文档，
    否则会把上一轮的 validate 修复又推翻回去。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import validate as V
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "skills").mkdir(parents=True)
        (base / "skills" / "flat-card.md").write_text(
            "# 扁平卡片\n\n没有 frontmatter。\n", encoding="utf-8")
        problems, stats = V.validate_path(base)
    assert stats["cards"] == 1, f"扁平 skills/*.md 必须当卡片：{stats}"
    assert any(p[0] == "error" and "name" in p[2] for p in problems), \
        f"无 frontmatter 的扁平卡片应报缺失字段（而非静默免检）：{problems}"
    with tempfile.TemporaryDirectory() as d2:
        base2 = Path(d2)
        sk = base2 / "skills" / "demo"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text(
            "---\nname: demo\ndescription: 用于校验扁平与嵌套布局的区分。不做：通用问答。\n---\n\n"
            "# E — 可执行步骤\n\n**Step 1 · 做**\n\n完成标准：做完。\n\n"
            "# B — 边界\n\n失败模式：无。\n", encoding="utf-8")
        (sk / "VERIFY.md").write_text("# VERIFY\n\n无 frontmatter 的辅助文档。\n",
                                      encoding="utf-8")
        _, stats2 = V.validate_path(base2)
    assert stats2["cards"] == 1 and stats2["docs"] == 1, \
        f"嵌套布局的辅助文档仍应归文档：{stats2}"


def t_ci_artifact_gate():
    """复审 G2/#2：CI 的样例 gate 步骤必须真能过——防策略变更静默打破 CI。

    复审 #2 后 CI 改用**交叉复核**报告（不再需要 --allow-single-scorer 豁免）：
    样例卡自带 `FIDELITY.json`（2 个独立评分者、分差 8）→ gate 直接放行。
    """
    rep = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/FIDELITY.json"
    assert rep.exists(), f"样例交叉复核报告缺失：{rep}"
    out = run(["gate", str(rep), "--min", "B"]).stdout
    assert "通过门槛" in out, out
    assert "交叉复核" in out, f"gate 应识别报告内嵌的交叉复核：{out}"
    # 旧单评分报告仍在（作人类可读的叙事），但不再作为 CI 门禁依据
    old = ROOT / "examples/sample-bundle/eval/fidelity-report.md"
    assert old.exists(), "人类可读的 FIDELITY 报告应保留"


def t_registry_structured_fidelity_and_reports():
    """复审 #2/#3：registry 旁挂 fidelity **结构化**；FIDELITY 报告**随产物发布**。"""
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = Path(d) / "dist"
        run(["compile", str(b), "--out", str(out), "--with-reports"])
        # #3 报告随包
        assert (out / "skills" / "major-contradiction" / "FIDELITY.md").exists(), \
            "--with-reports 应把 FIDELITY 报告放进产物"
        man = json.loads((out / "BUILD_MANIFEST.json").read_text(encoding="utf-8"))
        assert man.get("with_reports") is True, man.get("with_reports")
        # #2 registry 旁挂结构化 fidelity（不再只有 score/grade）
        meta = json.loads((out / "registry" / "_td-meta.json").read_text(encoding="utf-8"))
        fid = meta["entries"]["major-contradiction"]["fidelity"]
        assert fid.get("dimensions"), f"fidelity 应含结构化维度：{fid}"
        assert "eval_mode" in fid, f"fidelity 应含 eval_mode：{fid}"
        # 默认（不带 --with-reports）不随包发布报告
        out2 = Path(d) / "dist2"
        run(["compile", str(b), "--out", str(out2)])
        assert not (out2 / "skills" / "major-contradiction" / "FIDELITY.md").exists(), \
            "默认不应随包发布报告"


def t_compile_with_reports_honest():
    """复审 #2：`--with-reports` **未找到报告时不得宣称"已随产物发布"**（假绿）。

    此前成功提示是无条件打印的：实测官方样例 bundle 打印「FIDELITY 报告已随产物发布」，
    但产物里只有 SKILL.md（查找路径不含样例的报告位置）。现在：真复制了才说"已写入"，
    没找到就 warn 并列出 slug。**没做过的事不许说做过。**
    """
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        for slug in ("major-contradiction", "sequence-execution"):
            (b / "skills" / slug / "FIDELITY.md").unlink()
        out = Path(d) / "dist"
        p = run(["compile", str(b), "--out", str(out), "--with-reports", "--force"])
        assert "已写入产物" not in p.stdout, f"没找到报告却宣称已发布（假绿）：{p.stdout}"
        assert "未找到" in p.stdout, f"应明确 warn 未找到报告：{p.stdout}"
        assert not list((out / "skills").rglob("FIDELITY.*")), "无报告时产物里不应出现报告"
    with tempfile.TemporaryDirectory() as d2:
        b2 = setup(Path(d2))
        out2 = Path(d2) / "dist"
        p2 = run(["compile", str(b2), "--out", str(out2), "--with-reports"])
        assert "已写入产物" in p2.stdout, f"确有报告时应如实报告已发布：{p2.stdout}"
        assert (out2 / "skills" / "major-contradiction" / "FIDELITY.md").exists()


def t_compile_finds_card_json_report():
    """复审 #2：卡同级的 `FIDELITY.json` 也必须被找到（此前只认 FIDELITY.md）。

    样例 bundle 的真实报告就是 FIDELITY.json；查找不到 → 门禁数据缺失 + with-reports 假绿。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import publish
    rep = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/FIDELITY.json"
    src = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md"
    score, grade, path, rdict = publish._fidelity_for(ROOT / "examples/sample-bundle",
                                                      src, {"slug": "five-affairs-seven-questions"})
    assert path is not None and Path(path) == rep, f"应找到卡片同级 FIDELITY.json：{path}"
    assert (score, grade) == (93, "A"), (score, grade)
    assert rdict and rdict.get("graders") == ["grader-1", "grader-2"], rdict

def t_strategy():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        o = run(["strategy", str(b)]).stdout
        assert "推荐形态：single" in o, o
        o2 = run(["strategy", str(b), "--purpose", "workflow"]).stdout
        assert "推荐形态：pack" in o2, o2
        o3 = run(["strategy", str(b), "--mode", "pack"]).stdout
        assert "不覆盖用户选择" in o3, o3
        assert (b / "output-decision.json").exists()


def t_compile_and_publish():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = Path(d) / "dist"
        o = run(["compile", str(b), "--out", str(out)]).stdout
        assert "已发布 2 个技能" in o, o
        m = json.loads((out / "BUILD_MANIFEST.json").read_text(encoding="utf-8"))
        assert m["mode"] == "pack" and len(m["published_hashes"]) >= 2
        assert (out / "registry/major-contradiction.json").exists()
        assert not (out / "skills/major-contradiction/FIDELITY.md").exists(), "FIDELITY 不应随包发布"
        # 本地手改 → 拒绝
        f = out / "skills/major-contradiction/SKILL.md"
        f.write_text(f.read_text(encoding="utf-8") + "\n<!-- 手改 -->\n", encoding="utf-8")
        run(["compile", str(b), "--out", str(out)], expect=1)
        # 快照 + 覆盖
        run(["compile", str(b), "--out", str(out), "--overwrite"])
        assert "手改" not in f.read_text(encoding="utf-8")
        snaps = sorted((out.parent / (out.name + ".td_snapshots")).iterdir())
        assert len(snaps) >= 1
        # 回滚
        run(["rollback", str(out), "--to", "latest"])
        run(["rollback", str(out), "--to", "1999-01-01-000000"], expect=1)


def t_compile_single_mode():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = Path(d) / "dist-single"
        run(["compile", str(b), "--out", str(out), "--mode", "single"])
        assert (out / "SKILL.md").exists(), "single 模式缺路由入口"
        assert (out / "cards/major-contradiction.md").exists()


def t_compile_blocks_low_grade():
    with tempfile.Terminaldir() if False else tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        fid = b / "skills/major-contradiction/FIDELITY.md"
        fid.write_text(FIDELITY_MD.replace("**80**", "**40**").replace("**B**", "**D**"),
                       encoding="utf-8")
        run(["compile", str(b), "--out", f"{d}/x"], expect=1)
        o = run(["compile", str(b), "--out", f"{d}/x", "--force"]).stdout
        assert "强制发布" in o, o
        m = json.loads(Path(d).joinpath("x/BUILD_MANIFEST.json").read_text(encoding="utf-8"))
        assert m["forced"] is True


def t_fidelity_parse_strictness():
    """第三方测评 #2 / 报告 P1-2：FIDELITY 解析严格化。

    旧解析：报告里漏一个维度、或声明总分与维度之和不符，都会被**静默忽略**，
    gate 直接信任声明总分开绿灯。现在：漏维度进 `unparsed_dims` 显式提示；
    声明总分 ≠ 维度之和 → `total_mismatch` 显式提示，且 gate 命令行打印警示。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import fidelity as fid
    # ① 漏一个维度（结构完整度整段删掉）：总分声明 80，但维度之和只剩 67
    missing_one = FIDELITY_MD.replace(
        "## 维度 5 · 结构完整度（15 分）\n得分：13/15\n\n", "")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p = d / "r.md"
        p.write_text(missing_one, encoding="utf-8")
        rep = fid.parse_report(p)
        assert "structure" in rep["unparsed_dims"], f"漏维度应进 unparsed_dims：{rep}"
        assert rep["total_mismatch"] is True, (
            f"声明总分(80)≠维度之和(67)应标记不一致：{rep}")
        assert rep["declared_total"] == 80 and rep["dimension_sum"] == 67, rep
        # gate 命令行应打印两条警示（漏维度 + 总分不一致）。
        # 用 --allow-single-scorer 关掉新默认的交叉复核要求，专测解析警示。
        o = run(["gate", str(p), "--allow-fallback", "--allow-single-scorer"]).stdout
        assert "未解析" in o, f"gate 应提示漏维度：{o}"
        assert "不一致" in o, f"gate 应提示总分不一致：{o}"

    # ② 维度齐全但声明总分写错（80 → 90）：维度之和 80，声明 90
    wrong_total = FIDELITY_MD.replace("**80**", "**90**")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        p2 = d / "r2.md"
        p2.write_text(wrong_total, encoding="utf-8")
        rep2 = fid.parse_report(p2)
        assert not rep2["unparsed_dims"], f"维度齐全不应有未解析：{rep2}"
        assert rep2["total_mismatch"] is True, (
            f"声明 90 ≠ 维度之和 80 应标记不一致：{rep2}")
        o2 = run(["gate", str(p2), "--allow-fallback", "--allow-single-scorer"]).stdout
        assert "不一致" in o2, f"gate 应提示总分不一致：{o2}"


def t_trigger():
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        suite_path = Path(d) / "suite.json"
        run(["trigger", "build", str(b), "--out", str(suite_path)])
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        # 补齐 prompt（build 只给骨架，prompt 必须由人/Agent 用口语写）
        for i, c in enumerate(suite["trigger_cases"], 1):
            c["prompt"] = f"用户口语测试句 {i}：这件事我该先动哪一头？"
        suite_path.write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8")
        ids = [c["case_id"] for c in suite["trigger_cases"]]
        assert any(c["case_id"].startswith("x-") for c in suite["trigger_cases"]), "缺 sibling 用例"
        assert any(c["expected"] == "should_not_trigger" for c in suite["trigger_cases"]), "缺诱饵用例"
        sheet = run(["trigger", "record", str(suite_path), "--out", f"{d}/sheet.md"]).stdout
        assert "答卷已生成" in sheet
        # 全对（按契约字段构造期望答案）
        ans = {}
        for c in suite["trigger_cases"]:
            ans[c["case_id"]] = ("none" if c["expected"] == "should_not_trigger"
                                 else (c.get("sibling_target") or c.get("target_slug")))
        ap = Path(d) / "ans.json"
        ap.write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
        o = run(["trigger", "score", str(suite_path), str(ap)]).stdout
        assert "→ pass" in o, o
        # 空 prompt 应拒绝判分
        bad_suite = Path(d) / "bad-suite.json"
        suite2 = json.loads(json.dumps(suite))
        suite2["trigger_cases"][0]["prompt"] = ""
        bad_suite.write_text(json.dumps(suite2, ensure_ascii=False), encoding="utf-8")
        assert "prompt 为空" in run(["trigger", "score", str(bad_suite), str(ap)], expect=1).stdout
        # 错一个 → fail
        ans2 = dict(ans)
        first_trigger = next(c for c in suite["trigger_cases"]
                             if c["expected"] != "should_not_trigger")
        ans2[first_trigger["case_id"]] = "wrong-slug"
        ap2 = Path(d) / "ans2.json"
        ap2.write_text(json.dumps(ans2, ensure_ascii=False), encoding="utf-8")
        p = run(["trigger", "score", str(suite_path), str(ap2)], expect=1)
        assert "❌" in p.stdout, p.stdout
        assert ids


def t_count():
    with tempfile.TemporaryDirectory() as d:
        out = f"{d}/m.json"
        o = run(["count", str(ROOT), "--out", out]).stdout
        m = json.loads(Path(out).read_text(encoding="utf-8"))
        assert m["discovery_payload"] > 0
        assert m["corpus_total"] > m["discovery_payload"]
        assert len(m["top10"]) == 10
        # 2026-10-07（#50）：传**单个文件**时不能静默报 0——旧实现对文件做 rglob
        # 返回空，于是 `count 某.md` 显示「语料总量 0」，看起来像"这文件不耗 token"。
        one = Path(d) / "one.md"
        one.write_text("语料总量的计量必须对单文件也成立，否则会静默报零。\n" * 20,
                       encoding="utf-8")
        out2 = f"{d}/m2.json"
        run(["count", str(one), "--out", out2])
        m2 = json.loads(Path(out2).read_text(encoding="utf-8"))
        assert m2["file_count"] == 1, f"单文件应被计量 1 次，实际 {m2['file_count']}"
        assert m2["corpus_total"] > 0, "单文件计量返回 0——静默假绿"


def t_prompt():
    with tempfile.TemporaryDirectory() as d:
        o = run(["prompt", str(ROOT / "SKILL.md"), "--out", f"{d}/p.md", "--mode", "entry"]).stdout
        assert "编译" in o or "tokens" in o
        assert Path(d, "p.md").exists()
        o2 = run(["prompt", str(ROOT), "--out", f"{d}/p2.md", "--mode", "inline"]).stdout
        p2 = Path(d) / "p2.md"
        assert p2.exists() and "附：" in p2.read_text(encoding="utf-8"), o2
        assert "内联文件" in o2, o2


def t_diff_impact_repair_patch_update():
    with tempfile.TemporaryDirectory() as d:
        b1, b2 = setup(Path(d) / "v1"), setup(Path(d) / "v2")
        card = b2 / "skills/major-contradiction/SKILL.md"
        card.write_text(card.read_text(encoding="utf-8") + "\n## 补充\n\n新增一节。\n", encoding="utf-8")
        o = run(["diff", str(b1), str(b2)]).stdout
        assert "变更 1" in o, o
        imp = run(["impact", str(b1), "sequence-execution"]).stdout
        assert "引用" in imp, imp
        # repair（dry-run 不落盘）
        crlf = b2 / "skills/sequence-execution/SKILL.md"
        crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
        o1 = run(["repair", str(b2)]).stdout
        assert "CRLF" in o1, o1
        assert b"\r\n" in crlf.read_bytes(), "dry-run 不应落盘"
        run(["repair", str(b2), "--apply"])
        assert b"\r\n" not in crlf.read_bytes(), "--apply 后应已修复"
        # patch
        pj = Path(d) / "patch.json"
        pj.write_text(json.dumps({"append_section": {"补充测试": "由 patch 写入"},
                                  "set_frontmatter": {"version": "0.2.1"}}, ensure_ascii=False),
                      encoding="utf-8")
        o2 = run(["patch", str(card), str(pj), "--apply"]).stdout
        assert "append_section" in o2 and "已落盘" in o2, o2
        assert "补充测试" in card.read_text(encoding="utf-8")
        run(["patch", str(card), str(pj)], expect=0)  # 幂等
        # update
        o3 = run(["update", str(b2), "--out", f"{d}/dist2"]).stdout
        assert "dry-run" in o3, o3
        o4 = run(["update", str(b2), "--out", f"{d}/dist2", "--apply"]).stdout
        assert "已重编译" in o4, o4


def t_upstream_vendor():
    """vendored 上游代码必须真的能跑（本机零依赖环境）。"""
    out = run(["upstream", "list"]).stdout
    assert "可用工具 16/16" in out, out
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "book.md"
        src.write_text(BOOK, encoding="utf-8")
        o = run(["upstream", "run", "chunk", str(src), "--sidecar", f"{d}/side"]).stdout
        assert "上游 build_chunks.py" in o, o
        # 上游产物：normalized + chunks + 版本化 cache
        assert (Path(d) / "side" / "chunks" / "chunks.jsonl").exists(), "上游 chunks 产物缺失"
        assert list((Path(d) / "side" / "cache" / "build_chunks").iterdir()), "上游缓存目录缺失"
    # 未知工具要人话报错
    assert "未知上游工具" in run(["upstream", "run", "nope"], expect=1).stdout
    # dry-run 必须放在 tool 之前（其后会被 REMAINDER 吞掉）
    o = run(["upstream", "run", "--dry-run", "count", str(ROOT)]).stdout
    assert "dry-run：将执行" in o, o


def t_cache_versioning():
    """缓存键必须含实现版本/契约版本/参数——否则改算法不失效。"""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "book.md"
        src.write_text(BOOK, encoding="utf-8")
        run(["chunk", str(src), "--max-chars", "4000"])
        m = json.loads(sorted((src.with_suffix(".md.td") / "runs").glob("*/manifest.json"))[0]
                        .read_text(encoding="utf-8"))
        for k in ("run_id", "impl_version", "schema_version", "cache_key"):
            assert k in m, f"manifest 缺 {k}"
        assert m["cache_key"] == m["cache_key"].lower() and len(m["cache_key"]) == 64
        # 改参数 → 缓存键必须变
        run(["chunk", str(src), "--max-chars", "2000"])
        keys = {p.name for p in (src.with_suffix(".md.td") / "cache" / "build_chunks").iterdir()}
        assert len(keys) >= 2, f"参数变化后缓存键未变：{keys}"


def t_run_traceability():
    """每次分块运行必须独立留痕。"""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "book.md"
        src.write_text(BOOK, encoding="utf-8")
        run(["chunk", str(src)])
        run(["chunk", str(src), "--force"])
        runs = list((src.with_suffix(".md.td") / "runs").iterdir())
        assert len(runs) == 2, f"应有 2 次运行留痕，实际 {len(runs)}"


def t_writer_lock():
    """并发写保护：目标被锁时 compile 必须拒绝而不是产生半个 target。"""
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = Path(d) / "dist"
        out.mkdir(parents=True, exist_ok=True)
        lock = out.with_name(out.name + ".td-write-lock")
        lock.write_text("pid=99999 at=2026-01-01T00:00:00", encoding="utf-8")
        p = run(["compile", str(b), "--out", str(out)], expect=1)
        assert "另一个写者" in p.stdout, p.stdout
        lock.unlink()
        run(["compile", str(b), "--out", str(out)])
        assert not lock.exists(), "锁文件未清理"


def t_fetch_subtitle_dryrun():
    """字幕获取默认 dry-run：不得联网。"""
    with tempfile.TemporaryDirectory() as d:
        o = run(["fetch-subtitle", "https://example.com/v", "--out", d]).stdout
        assert "加 --execute" in o, o
        assert not list(Path(d).glob("*.srt")), "dry-run 不应产生任何文件"
        assert run(["fetch-subtitle", "https://example.com/v", "--out", d]).returncode == 0


def t_bigram_tokenizer():
    """CJK bigram + 英文整词——两个方向的回归都在这里。

    真实缺陷（由 tests/bench_index.py 对照基准抓出）：英文曾被逐字母拆成 "c o s t"，
    FTS 于是匹配任何含 c/o/s/t 的块，816 个假命中。修完又引入新 bug：
    CJK 缓冲区在追加当前字之前就 flush，导致中文查询返回空串。
    两个 bug 方向相反，必须同时回归。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib.chunking import _cjk_bigrams as f
    assert f("cost") == "cost", f"英文应整词保留：{f('cost')!r}"
    assert f("first principles") == "first principles", f(f("first principles"))
    assert f("SpaceX") == "spacex", f(f("SpaceX"))
    assert f("主要矛盾") == "主要 要矛 矛盾", f"中文应出 bigram：{f('主要矛盾')!r}"
    assert f("矛盾") == "矛盾", f"两字中文应出一个 bigram：{f('矛盾')!r}"
    assert f("AI 效率") == "ai 效率", f"中英混排：{f('AI 效率')!r}"
    assert f("抓总的、主要的") == "抓总 总的 主要 要的", f(f("抓总的、主要的"))


def t_lexindex_both_scripts():
    """索引必须同时支持中文与英文查询（语料不同语言都要能检索）。"""
    with tempfile.TemporaryDirectory() as d:
        zh = Path(d) / "zh.md"
        zh.write_text(BOOK, encoding="utf-8")
        en = Path(d) / "en.md"
        en.write_text(
            "# Production notes\n\n"
            "Musk said the secret is to look at the problem from first principles "
            "and question every requirement, then simplify aggressively.\n\n"
            "Manufacturing is underrated and production is the real bottleneck.\n",
            encoding="utf-8")
        run(["chunk", str(zh)]); run(["lexindex", str(zh.with_suffix(".md.td") / "chunks.jsonl")])
        run(["chunk", str(en)]); run(["lexindex", str(en.with_suffix(".md.td") / "chunks.jsonl")])
        q1 = run(["lexindex", "--db", str(zh.with_suffix(".md.td") / "lexical.sqlite"),
                  "--query", "主要矛盾"]).stdout
        assert "命中" in q1, f"中文查询未命中：{q1}"
        q2 = run(["lexindex", "--db", str(en.with_suffix(".md.td") / "lexical.sqlite"),
                  "--query", "first principles"]).stdout
        assert "命中" in q2, f"英文短语查询未命中：{q2}"
        q3 = run(["lexindex", "--db", str(en.with_suffix(".md.td") / "lexical.sqlite"),
                  "--query", "manufacturing"]).stdout
        assert "命中" in q3, f"英文单词查询未命中：{q3}"


def t_lexindex():
    """SQLite FTS5 词法索引：中文 bigram 分词 + 邻接块扩展。"""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "book.md"
        src.write_text(BOOK, encoding="utf-8")
        run(["chunk", str(src)])
        sidecar = src.with_suffix(".md.td")
        o = run(["lexindex", str(sidecar / "chunks.jsonl")]).stdout
        assert "索引已建" in o, o
        q = run(["lexindex", "--db", str(sidecar / "lexical.sqlite"),
                 "--query", "主要矛盾", "--neighbors", "1"]).stdout
        assert "命中" in q and "ck-" in q, q
        # 邻接块必须带出上下文块（防断章取义）
        assert "seq" in q, q
        # 未命中要人话提示而不是报错
        assert "未命中" in run(["lexindex", "--db", str(sidecar / "lexical.sqlite"),
                                "--query", "不存在的词"]).stdout
        # 缺索引文件：人话报错，不是裸 traceback
        miss = run(["lexindex", "--db", f"{d}/none.sqlite", "--query", "x"], expect=1)
        assert "索引不存在" in miss.stdout and "Traceback" not in miss.stdout, miss.stdout


def t_lexindex_single_char_cjk():
    """第三方测评 #2 / 报告 P0-2：单字 CJK 查询不能让 FTS5 崩。

    旧 `_cjk_bigrams` 对单字 CJK 段返回空串，注入 FTS5 变成 `MATCH ''`
    → sqlite3.OperationalError（fts5: syntax error）。单字查询（如「道」「法」）
    在中文书类语料里极常见，一旦崩就整条索引不可用。修复：单字 CJK 原字入库。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import chunking
    # 单元层：单字 CJK 必须返回自身，不得返回空串（否则注入 FTS5 变 MATCH '' → 崩）
    assert chunking._cjk_bigrams("道") == "道", "单字 CJK 应原字入库"
    assert chunking._cjk_bigrams("法") == "法", "单字 CJK 应原字入库"
    assert chunking._cjk_bigrams("AB") == "ab", "英文整词不变"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = d / "book.md"
        src.write_text("# 道\n\n法者，曲制官道主用也。\n\n道\n", encoding="utf-8")
        run(["chunk", str(src)])
        sidecar = src.with_suffix(".md.td")
        run(["lexindex", str(sidecar / "chunks.jsonl")])
        q = run(["lexindex", "--db", str(sidecar / "lexical.sqlite"),
                 "--query", "道"]).stdout
        assert "Traceback" not in q, f"单字中文查询不应崩：{q}"
        assert "命中" in q, f"单字中文查询应命中（独立单字块已索引）：{q}"


def t_trigger_split_metrics():
    """train/validation 切分 + 盲测包不泄露答案 + P/R/F1 与兄弟混淆率。"""
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        sp = Path(d) / "suite.json"
        run(["trigger", "build", str(b), "--out", str(sp)])
        suite = json.loads(sp.read_text(encoding="utf-8"))
        for i, c in enumerate(suite["trigger_cases"], 1):
            c["prompt"] = f"口语测试句{i}：先动哪一头？"
        sp.write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8")

        o = run(["trigger", "split", str(sp)]).stdout
        assert "train" in o and "validation" in o, o
        split = json.loads((sp.parent / "trigger-split.json").read_text(encoding="utf-8"))
        assert set(split["train"]) & set(split["validation"]) == set(), "train/validation 有重叠"
        assert len(split["train"]) + len(split["validation"]) == len(suite["trigger_cases"])

        # 盲测包绝不能含答案
        run(["trigger", "prepare", str(sp), "--out", f"{d}/blind"])
        blind = json.loads((Path(d) / "blind" / "blind-tasks.json").read_text(encoding="utf-8"))
        for leaked in ("expected", "sibling_target", "target_slug", "why"):
            assert leaked not in json.dumps(blind, ensure_ascii=False), f"盲测包泄露了 {leaked}"
        assert (Path(d) / "blind" / "answers-template.jsonl").exists()

        # 造一个「兄弟混淆 + 诱饵误触发」的答案，验证指标算对
        cases = suite["trigger_cases"]
        ans = {}
        for c in cases:
            ans[c["case_id"]] = ("none" if c["expected"] == "should_not_trigger"
                                 else (c.get("sibling_target") or c.get("target_slug")))
        pos = [c for c in cases if c["expected"] != "should_not_trigger"]
        dec = [c for c in cases if c["expected"] == "should_not_trigger"]
        sib = [c for c in cases if c["expected"] == "sibling"]
        if sib:                      # 选错邻居 → 兄弟混淆
            other = [s for s in suite["skills_in_scope"] if s["name"] != sib[0]["sibling_target"]]
            ans[sib[0]["case_id"]] = other[0]["name"] if other else "wrong-slug"
        if dec:                      # 诱饵误触发 → FP
            ans[dec[0]["case_id"]] = pos[0].get("target_slug") or suite["skills_in_scope"][0]["name"]
        ap = Path(d) / "ans.json"
        ap.write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
        p = run(["trigger", "score", str(sp), str(ap)], expect=1)
        assert "precision" in p.stdout and "F1" in p.stdout, p.stdout
        assert "兄弟混淆率" in p.stdout, p.stdout
        rep = json.loads((sp.parent / "trigger-eval.json").read_text(encoding="utf-8"))
        m = rep["metrics"]
        assert m["tp"] == 3 and m["fp"] == 1 and m["fn"] == 1, m
        assert m["sibling_confusion"] == 1, m
        assert 0 < m["f1"] < 1, m


def t_answer_normalization():
    """判分器必须归一化 'none'/'null'/'不适用' 等字符串。

    真实盲测（sample-bundle）暴露：Agent 返回字符串 "none" 而非 JSON null，
    第一版判分器把两条「正确判断为不触发」的诱饵误判成误触发（FP=2、诱饵通过率 0%）。
    合成测试里 answers 用 Python None 构造，走不到这条分支——只有真实盲测能发现。
    """
    from importlib import util as _u
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = _u.spec_from_file_location("_evals", ROOT / "scripts" / "tdlib" / "evals.py")
    # 直接测归一化函数，不走整条链路
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        sp = Path(d) / "suite.json"
        run(["trigger", "build", str(b), "--out", str(sp)])
        suite = json.loads(sp.read_text(encoding="utf-8"))
        for i, c in enumerate(suite["trigger_cases"], 1):
            c["prompt"] = f"口语测试句{i}"
        sp.write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8")
        # 诱饵用字符串 "none" 作答，期望它们被判为 pass
        ans = {}
        for c in suite["trigger_cases"]:
            ans[c["case_id"]] = ("none" if c["expected"] == "should_not_trigger"
                                 else (c.get("sibling_target") or c.get("target_slug")))
        ap = Path(d) / "a.json"
        ap.write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
        p = run(["trigger", "score", str(sp), str(ap)])
        rep = json.loads((sp.parent / "trigger-eval.json").read_text(encoding="utf-8"))
        m = rep["metrics"]
        assert m["fp"] == 0, f"字符串 none 被误判为误触发：{m}"
        assert m["decoy_pass_rate"] == 1.0, f"诱饵通过率应 100%：{m}"
        assert rep["verdict"] == "pass", p.stdout


# --------------------------------------------------------------------------
# 约束检查器：让 CONSTRAINTS.md 的每一条断言变成会红的测试
# --------------------------------------------------------------------------
def t_fetch_subtitle_exists():
    """C1：字幕获取能力必须存在，且缺环境时降级为 dry-run 而不是报错。"""
    h = run(["fetch-subtitle", "--help"]).stdout
    assert "--execute" in h and "--cookies" in h, h
    with tempfile.TemporaryDirectory() as d:
        o = run(["fetch-subtitle", "https://example.com/v", "--out", d]).stdout
        assert "加 --execute" in o, o
        assert not list(Path(d).iterdir()), "dry-run 不应产生任何文件"


def t_upstream_coverage():
    """C2：上游 16 类能力必须逐项有归属，不允许出现"没接上"的能力。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import upstream
    missing = [t for t, (f, _d) in upstream.MAPPING.items() if not (upstream.CANGJIE_DIR / f).exists()]
    assert not missing, f"这些上游能力没有 vendored 脚本：{missing}"
    # 契约层必须也被 vendor（否则 C3 只在算法层成立）
    schemas = list((upstream.CANGJIE_DIR / "schemas").rglob("*.schema.json"))
    assert len(schemas) >= 10, f"上游 schema 应 ≥10 个，实际 {len(schemas)}"
    # 归属表必须与代码一致：CAPABILITIES.md 里逐个工具都要出现，且不得有未列出的工具
    # 注意：表里写的是 `td.py chunk` 这种形式，含空格与点，取反引号内容的**最后一段**
    cap = (ROOT / "CAPABILITIES.md").read_text(encoding="utf-8").split("## 二、")[0]
    listed = {t for t in (seg.split()[-1] for seg in re.findall(r"`([^`]+)`", cap)) if t}
    unlisted = [t for t in upstream.MAPPING if t not in listed and t != "lexindex"]
    assert not unlisted, f"这些上游能力没写进 CAPABILITIES.md：{unlisted}"


def t_contract_ledger_no_silent_gap():
    """C4 的核心：CONSTRAINTS.md 里不允许存在"既没✅也没❌"的静默缺口。"""
    doc = (ROOT / "CONSTRAINTS.md").read_text(encoding="utf-8")
    rows = [ln for ln in doc.splitlines() if re.match(r"\| C\d+ \|", ln)]
    assert len(rows) >= 6, f"约束条目不足：{len(rows)}"
    for ln in rows:
        cid = ln.split("|")[1].strip()
        assert re.search(r"✅|❌|⚠️", ln), f"{cid} 没有明确状态（禁止静默缺口）"


def t_defect_regression_ledger():
    """C4：缺陷台账里每一条都必须有对应回归测试；测试不存在则红。"""
    doc = (ROOT / "CONSTRAINTS.md").read_text(encoding="utf-8")
    body = doc.split("## 已发现的自身缺陷台账", 1)[-1]
    rows = [ln for ln in body.splitlines() if re.match(r"\| \d+ \|", ln)]
    assert len(rows) >= 11, f"台账条目不足：{len(rows)}"
    src = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    for ln in rows:
        m = re.findall(r"`(t_[a-z0-9_]+)`", ln)
        assert m, f"台账行没有指向任何回归测试：{ln[:60]}"
        for name in m:
            assert f"def {name}(" in src, f"台账引用的测试不存在：{name}"


def t_verify_quotes_direction():
    """缺陷 3/4/5：引语核验必须向后取窗、遇到下一个引用即停、编号用位置切片。

    这三条曾经分别造成 16/18 假阴性、跨引用错配、以及 17144 条只匹配 27 条。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    with tempfile.TemporaryDirectory() as d:
        corpus = Path(d) / "c.md"
        # 构造：两个引用各自紧跟一段引语，且第 1 条也含「」式自述
        corpus.write_text(
            "【第1条 | 2020-01-01 | 111】Alpha statement here.\n\n"
            "【第2条 | 2020-01-02 | 222】Beta statement here.\n\n"
            "【第3条 | 2020-01-03 | 333】Gamma statement here.\n", encoding="utf-8")
        card = Path(d) / "SKILL.md"
        card.write_text(
            "---\nname: t\ndescription: |\n  测试用，足够长以通过描述长度检查。\n---\n"
            "【第1条】「Alpha statement here.」这是紧跟的引语。\n\n"
            "【第2条】这句里也有「」，但**不是**引语，是我的行文。\n\n"
            "【第3条】「Beta statement here.」故意错配，应被抓出。\n", encoding="utf-8")
        res = evals.verify_quotes(card, corpus)
        # 语义：#1 命中；#2 引用了但没给逐字引语（自述里只有空引号）→ unquoted；
        #       #3 引用了却核不到（跨引用错配）→ unverified
        assert res["refs_total"] == 3, res
        assert res["verified"] == 1, f"应命中 1 条：{res}"
        assert [u["ref"] for u in res["unverified"]] == ["3"], res
        assert [u["ref"] for u in res["unquoted_refs"]] == ["2"], \
            f"概述式引用必须留痕而不是静默跳过：{res}"
        assert res["orphaned_refs"] == [], res
        assert res["verdict"] == "fail", "存在核不到的引语时必须判失败"


def t_research_lane_coverage():
    """缺陷 6：调研合并必须输出车道覆盖审计，2/6 缺失不能被 100% 一手占比掩盖。"""
    with tempfile.TemporaryDirectory() as d:
        rd = Path(d)
        (rd / "01-writings.md").write_text(
            "---\nlane: 01-writings\nstatus: partial\none_hand_weight: 0.5\n---\n"
            "- **[一手]** 某条结论 —— 出处：X\n", encoding="utf-8")
        (rd / "04-external-views.md").write_text(
            "---\nlane: 04-external-views\nstatus: missing\none_hand_weight: 0\n---\n"
            "> 缺口声明：本路完全未获取。\n", encoding="utf-8")
        out = rd / "merged.md"
        run(["research", "merge", str(rd / "01-writings.md"), str(rd / "04-external-views.md"),
             "--out", str(out)])
        text = out.read_text(encoding="utf-8")
        assert "车道覆盖审计" in text, text[:400]
        assert "1/2 路缺失" in text, f"缺失车道必须被显式标注：{text[:400]}"
        assert "幸存条目" in text, "占比必须改称『幸存条目』，不能让人误读为整体覆盖度"


def t_validate_upstream_format():
    """缺陷 7/8：校验器必须接受上游 cangjie 的产物格式，不产生假阳性。"""
    upstream_card = """---
name: upstream-style-card
description: |
  当用户在重大选择上纠结、列了利弊表还是拿不定主意时调用。
  核心理念: 无法决定就答否; 不适用于: 日常琐碎选择。
source_book: 《纳瓦尔宝典》
source_chapter: 第一章·财富
---

# 重大决策启发式

## R — 原文 (Reading)
> 「如果你无法下决定，就回答否。」——《纳瓦尔宝典》

## I — 方法论骨架 (Interpretation)
1. 无法决定 → 答否

## A1 — 书中的应用 (Past Application)
### 案例 1: 读不懂的书

## A2 — 触发场景 (Future Trigger)
### 用户会在什么情境下需要这个 skill?

## E — 可执行步骤 (Execution)
1. 判断跨度
   - 完成标准: 是五年以上的决定才算

## B — 边界 (Boundary)
### 不要在以下情况使用此 skill
- 日常琐碎选择

### 作者在书中警告的失败模式
- 把「无法决定就答否」当成万能规则，滥用在日常琐碎选择上
"""
    with tempfile.TemporaryDirectory() as d:
        sk = Path(d) / "skills" / "upstream-style-card"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text(upstream_card, encoding="utf-8")
        o = run(["validate", str(Path(d))]).stdout
        assert "E — Execution" not in o and "未发现 E" not in o, f"双语段标题被误报：{o}"
        assert "可溯源" not in o, f"source_book/source_chapter 被误报为缺溯源：{o}"
        assert "error 0" in o, o


def t_persona_no_e_section():
    """缺陷 9：人物卡模板禁止显式步骤，校验器不得反过来要求它有 E 段。"""
    persona = """---
name: someone-mind
description: |
  以某人的认知框架分析问题：调用其判断习惯与认知边界。
  适用：技术选型、复杂度取舍。不做：需要外部证据的判断。
subject_type: person
material_type: person
---

# 某人的思维方式

> **你不是在模仿语气；你带着以下经历、判断、失败和边界来思考。**

## 我的认知上下文
### 信念及其来源
1. **某信念** —— 2020-01-01，某地，【第1条】
### 我做过的关键决策
**某决策**（2019）—— 情境 / 判断依据 / 事后反思
### 我栽过的跟头
- **某失败**：代价 → 改了什么
### 我的内在矛盾
- **A vs B**：什么情况下倒向哪边
### 我明确不懂的
- 某领域：为什么超出能力
  - 未知，非推测。

## 我看问题的方式
- 先问有没有更本质的约束

## 我绝不会做的事
- **绝不**用类比当主要论据

## 我说话的方式
- **偏好**：长句诊断 + 极短断言收尾

## 素材来源
| 素材 | 一手 | 权重 |
|---|---|---|
| 推文 | [一手] | 0.8 |
"""
    with tempfile.TemporaryDirectory() as d:
        sk = Path(d) / "skills" / "someone-mind"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text(persona, encoding="utf-8")
        o = run(["validate", str(Path(d))]).stdout
        assert "未发现 E" not in o, f"人物卡被要求 E 段（与禁止显式步骤矛盾）：{o}"
        assert "error 0" in o, o


# --------------------------------------------------------------------------
# C3：契约归一 —— 产物必须能被上游 schema 校验
# --------------------------------------------------------------------------
def t_contract_list():
    """契约层必须自带全部 11 份映射，且能列出。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts
    o = run(["contract", "list"]).stdout
    assert "source-document" in o and "registry-entry" in o, o[:300]
    st = contracts.status()
    missing = [k for k, v in st["contracts"].items() if not v]
    assert not missing, f"契约文件缺失：{missing}"
    assert len(st["contracts"]) >= 10, st


def t_contract_source_document():
    """chunk 产物必须符合上游 source-document（含 normalized 版本化分层）。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "b.md"
        src.write_text(BOOK, encoding="utf-8")
        run(["chunk", str(src)])
        sidecar = src.with_suffix(".md.td")
        doc = sidecar / "document.json"
        res = contracts.validate("source-document", json.loads(doc.read_text(encoding="utf-8")))
        assert res["ok"], f"document.json 不合契约：{res['errors'][:3]}"
        # 版本化分层：normalized/<source_id>/<version_id>/document.json
        norm = list((sidecar / "normalized").rglob("document.json"))
        assert norm, "缺少 normalized/<source_id>/<version_id>/ 分层"
        ver = json.loads(norm[0].read_text(encoding="utf-8"))["version_id"]
        assert ver.startswith("sha256:"), ver


def t_contract_registry_entry():
    """compile 产出的 registry 条目必须符合 registry-entry-v2（15 必填 + 禁额外字段）。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        out = Path(d) / "dist"
        run(["compile", str(b), "--out", str(out)])
        regs = list((out / "registry").glob("*.json"))
        entries = [p for p in regs if p.name != "_td-meta.json"]
        assert entries, "没有产出 registry 条目"
        for p in entries:
            res = contracts.validate("registry-entry", json.loads(p.read_text(encoding="utf-8")))
            assert res["ok"], f"{p.name} 不合 registry-entry-v2：{res['errors'][:3]}"
        # 本包自有的 FIDELITY 明细必须旁挂，不能污染契约条目
        assert (out / "registry" / "_td-meta.json").exists(), "缺旁挂元数据"


def t_contract_source_manifest():
    """调研合并必须产出 source-manifest，且缺失车道映射为 tertiary（不默认 primary）。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts
    with tempfile.TemporaryDirectory() as d:
        rd = Path(d)
        (rd / "01-writings.md").write_text(
            "---\nlane: 01-writings\nstatus: partial\none_hand_weight: 0.6\n---\n"
            "- **[一手]** 结论 —— 出处：X\n", encoding="utf-8")
        (rd / "04-external-views.md").write_text(
            "---\nlane: 04-external-views\nstatus: missing\none_hand_weight: 0\n---\n"
            "> 缺口声明\n", encoding="utf-8")
        out = rd / "merged.md"
        run(["research", "merge", str(rd / "01-writings.md"), str(rd / "04-external-views.md"),
             "--out", str(out)])
        mp = rd / "source-manifest.json"
        assert mp.exists(), "未产出 source-manifest.json"
        m = json.loads(mp.read_text(encoding="utf-8"))
        res = contracts.validate("source-manifest", m)
        assert res["ok"], f"不合契约：{res['errors'][:3]}"
        # source_id 形如 "src-04-external-views"，去掉 "src-" 前缀才是车道号
        trust = {s["source_id"].removeprefix("src-"): s["trust"] for s in m["sources"]}
        assert trust.get("04-external-views") == "tertiary", \
            f"缺失车道不得被标成 primary：{trust}"
        assert trust.get("01-writings") == "primary", \
            f"权重 0.6 的一手车道应标 primary：{trust}"


def t_contract_change_set():
    """diff 必须产出 change-set，且 change_type 取值在契约 enum 内。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts
    with tempfile.TemporaryDirectory() as d:
        a, b = setup(Path(d) / "v1"), setup(Path(d) / "v2")
        card = b / "skills" / "major-contradiction" / "SKILL.md"
        card.write_text(card.read_text(encoding="utf-8") + "\n## 新增\n\n内容\n", encoding="utf-8")
        run(["diff", str(a), str(b)])
        cs = b / "change-set.json"
        assert cs.exists(), "未产出 change-set.json"
        data = json.loads(cs.read_text(encoding="utf-8"))
        res = contracts.validate("change-set", data)
        assert res["ok"], f"不合契约：{res['errors'][:3]}"
        assert data["changes"], "change-set 不应为空"
        assert data["base_version"] != data["new_version"], "版本号应随内容变化"


def t_cross_review_gate():
    """nuwa 第三条铁律（交叉复核）必须是机器门禁，不只是文档里的一句话。

    背景（缺陷 #43）：此前 TD 只继承了「双 Agent 分离」，第三条铁律
    「2 个独立评分 agent、分差 >10 分人工复核」只在我脑子里和报告里，
    没有任何代码强制——等于没有。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts, fidelity as F
    from tdlib.util import ToolError

    # 1) 分差在阈值内 → pass
    r = F.cross_review([95, 91])
    assert r["verdict"] == "pass" and r["needs_human_review"] is False, r
    assert r["spread"] == 4 and r["scorers"] == 2

    # 2) 分差 > 10 → 人工复核（原文口径是严格大于）
    r = F.cross_review([95, 83])
    assert r["verdict"] == "needs_human_review" and r["spread"] == 12, r
    assert r["reasons"], "必须给出人话理由，不能只丢一个布尔"

    # 3) 贴边必须自报脆弱（阈值脆的时候不许单独引用单点读数）
    r = F.cross_review([95, 85])          # spread == 10 == 阈值
    assert r["verdict"] == "pass", "口径照抄上游：>10 才复核，等于 10 不触发"
    assert r["threshold_fragile"] is True, "贴着阈值却没报脆弱——这正是虚假 100% 的同型病"

    # 4) 单个评分不构成交叉复核
    r = F.cross_review([95])
    assert r["verdict"] == "insufficient_scorers" and r["needs_human_review"] is True, r

    # 5) 空集 / 越界必须报错，绝不判通过（防空集假绿）
    for bad in ([], None, [95, 130], [95, -1]):
        try:
            F.cross_review(bad)
            raise AssertionError(f"非法输入 {bad!r} 未报错——空集假绿")
        except ToolError:
            pass

    # 6) 产物必须符合自有契约，且坏产物过不了
    res = F.cross_review([95, 91], subject="demo")
    assert contracts.validate_local("cross-review", res)["ok"], res
    broken = dict(res)
    broken["verdict"] = "looks-fine-to-me"
    del broken["threshold_fragile"]
    assert not contracts.validate_local("cross-review", broken)["ok"], "坏产物竟然过了契约"

    # 7) gate 接入：交叉复核未过 → 拒绝放行（哪怕总分够高）
    rep = {"total": 95, "grade": "A", "eval_mode": "dual-agent",
           "dimensions": {"consistency": 30, "style": 20, "edge_honesty": 20,
                          "source_transparency": 15, "structure": 10}}
    passed, reasons = F.gate(rep, "A")
    assert passed, reasons
    passed, reasons = F.gate(rep, "A", cross=F.cross_review([95, 91]))
    assert passed, "分差 4 应放行"
    passed, reasons = F.gate(rep, "A", cross=F.cross_review([95, 78]))
    assert not passed and any("交叉复核" in r for r in reasons), reasons

    # 8) CLI 两端
    okp = run(["cross-review", "95,91"])
    assert "pass" in okp.stdout, okp.stdout
    bad_out = run(["cross-review", "95,80"], expect=1)
    assert "needs_human_review" in bad_out.stdout, bad_out.stdout
    solo = run(["cross-review", "95"], expect=1)
    assert "insufficient_scorers" in solo.stdout, solo.stdout

    # 贴边情形：断言**结构化字段**而不是 CLI 文案（缺陷 #39 的纪律：断言不许绑死措辞）
    tmp = Path(tempfile.mkdtemp()) / "cr.json"
    run(["cross-review", "95,85", "--out", str(tmp)])
    cli = json.loads(tmp.read_text(encoding="utf-8"))
    assert cli["threshold_fragile"] is True, cli
    assert cli["verdict"] == "pass" and cli["spread"] == 10, cli
    assert contracts.validate_local("cross-review", cli)["ok"], cli


def t_cli_handlers_intact():
    """所有 CLI 子命令都必须有实现函数。

    实测教训：用字符串切片替换代码时，`record_sheet` 被整段吞掉，而当时的测试
    被更早的另一个失败遮住，没能报出来。**结构层面的丢失必须有守卫测试**。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_td_cli", ROOT / "scripts" / "td.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import argparse as _ap
    parser = mod.build_parser()

    def leaves(p):
        sp = getattr(p, "_subparsers", None)
        if not sp:
            return [p]
        out = []
        for a in sp._group_actions[0].choices.values():
            out.extend(leaves(a) if isinstance(a, _ap.ArgumentParser) else [a])
        return out

    missing = [p.prog for p in leaves(parser)
               if getattr(p, "get_default", lambda k: None)("func") is None
               and not isinstance(p, _ap.ArgumentParser)]
    assert not missing, f"这些子命令没有绑定实现：{missing}"
    assert len(leaves(parser)) >= 30, f"子命令数量异常：{len(leaves(parser))}"
    # tdlib 的公开函数也不该凭空消失
    from tdlib import evals as E
    for name in ("build_suite", "split_cases", "record_sheet", "prepare_blind",
                 "score_suite", "output_eval", "verify_quotes", "token_metrics",
                 "bench", "build_lexindex"):
        assert hasattr(E, name) or name == "build_lexindex", f"evals 缺少 {name}"


def t_contract_eval_suite_and_failure():
    """eval-suite 与 failure-case 两份契约必须端到端合规。

    failure-case 的内容就是本包自己的 15 个缺陷——**缺陷必须可机校验**，
    否则 CONSTRAINTS.md 的台账就只是散文。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import contracts, defects
    with tempfile.TemporaryDirectory() as d:
        b = setup(Path(d))
        sp = Path(d) / "suite.json"
        run(["trigger", "build", str(b), "--out", str(sp)])
        res = contracts.validate("eval-suite", json.loads(sp.read_text(encoding="utf-8")))
        assert res["ok"], f"eval-suite 不合规：{res['errors'][:3]}"
        out = Path(d) / "fc.json"
        p = run(["failure", "export", "--out", str(out)]).stdout
        rep = json.loads(out.read_text(encoding="utf-8"))
        assert rep["invalid"] == 0, f"{rep['invalid']} 条 failure-case 不合规"
        assert rep["total"] >= 15, rep["total"]
        assert rep["by_severity"]["critical"] > 0, "缺陷里应有 critical 级"
        # 台账条数与 failure-case 条数必须一致（两处登记不许漂移）
        doc = (ROOT / "CONSTRAINTS.md").read_text(encoding="utf-8")
        rows = [ln for ln in doc.split("## 已发现的自身缺陷台账", 1)[-1].splitlines()
                if re.match(r"\| \d+ \|", ln)]
        assert len(rows) == rep["total"], \
            f"CONSTRAINTS 台账 {len(rows)} 条 vs failure-case {rep['total']} 条，两处必须同步"


def t_verify_quotes_timestamp():
    """视频/逐字稿来源的卡片：时间戳型引语必须能核验（两种排版都支持）。

    真实缺口：核验器原本只认 `【第N条】`，逐字稿卡片全部无法自检。
    本轮连踩四个坑，一次比一次隐蔽：
      1. 逐字稿只记段落起点 → cue 级时间戳引用被判"不存在"
      2. 时间戳引用窗口不限于下一个引用 → 串到下一条引语
      3. 卡片排版是「引语在前、时间戳在后」→ 只向前取窗必然错配
      4. `x.transcript.md` 用 with_suffix 拼出 `x.transcript.transcript.json` → cue 索引加载不上
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        srt = p / "t.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:05,000\nThe first sentence of the talk.\n\n"
            "2\n00:00:05,500 --> 00:00:09,000\nThe second sentence, which is different.\n\n"
            "3\n00:00:20,000 --> 00:00:24,000\nThe third sentence with a key claim.\n",
            encoding="utf-8")
        run(["transcript", str(srt)])
        md = p / "t.transcript.md"
        # ① 排版 A：时间戳在后
        cardA = p / "A.md"
        cardA.write_text("---\nname: a\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
                         "# A\n\n> 「The third sentence with a key claim.」\n> —— [00:00:20.00]\n",
                         encoding="utf-8")
        rA = evals.verify_quotes(cardA, md)
        assert rA["verified"] == 1, f"排版 A（时间戳在后）应核到：{rA}"
        # ② 排版 B：时间戳在前
        cardB = p / "B.md"
        cardB.write_text("---\nname: b\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
                         "# B\n\n【00:00:20.00】「The third sentence with a key claim.」\n",
                         encoding="utf-8")
        rB = evals.verify_quotes(cardB, md)
        assert rB["verified"] == 1, f"排版 B（时间戳在前）应核到：{rB}"
        # ③ 真的核不到时必须判失败
        cardC = p / "C.md"
        cardC.write_text("---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
                         "# C\n\n> 「这句话根本不在逐字稿里出现过。」\n> —— [00:00:20.00]\n",
                         encoding="utf-8")
        rC = evals.verify_quotes(cardC, md)
        assert rC["verdict"] == "fail" and rC["unverified"], rC
        # ④ 不同 cue 的文本不得互相匹配
        cardD = p / "D.md"
        cardD.write_text("---\nname: d\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
                         "# D\n\n> 「The second sentence, which is different.」\n> —— [00:00:20.00]\n",
                         encoding="utf-8")
        rD = evals.verify_quotes(cardD, md)
        assert rD["verdict"] == "fail", f"引语与时间戳不匹配时必须判失败：{rD}"


def t_transcript_dedupe_precision():
    """英文字幕去重必须用 n-gram，不能用字符集 Jaccard。

    实测踩过：字符集相似度下，两句不同的英文被判 0.9+ → 15 条 cue 被误删 2 条。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import transcript as T
    a = T._norm_key("The answer is not more data. The answer is a smaller question.")
    b = T._norm_key("If you cannot state the problem in one sentence without using the word solution")
    assert T._sim(a, b) < 0.5, f"不同句子相似度过高：{T._sim(a, b)}"
    same = T._norm_key("Data is cheap and it will happily confirm you.")
    dup = T._norm_key("Data is cheap and it will happily confirm you. Data is cheap.")
    assert T._sim(same, dup) >= 0.86, f"真重复应判为高相似：{T._sim(same, dup)}"


def t_verify_quotes_real_transcript():
    """真实 TED 字幕（TED《Inside the Mind of a Master Procrastinator》）回归。

    这一条是把 P3 的真实踩坑固化成测试——全部来自那条真实字幕：
      1. 段落文本是 cue 的超集 → 索引必须**段落优先**，否则跨 cue 引语核不到
      2. SRT 破折号写成 "--"，卡片写 "—" → 三种形态必须归一
      3. cue 级引用与段落级引用都要支持
    语料为本地已抓取的 .srt 副本（video-run/sources），测试不联网。
    """
    src = external_ws("video-run/sources/arj7oStGLkU.en.srt")
    if src is None:
        skip_ws("t_verify_quotes_real_transcript", "video-run 的 .srt 副本")
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    with tempfile.TemporaryDirectory() as d:
        srt = Path(d) / "real.en.srt"
        srt.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        run(["transcript", str(srt)])
        md = Path(d) / "real.en.transcript.md"
        assert md.exists()
        idx = evals._index_by_timestamp(md.read_text(encoding="utf-8"), md)
        # 段落起点必须映射到整段（而不是 cue 的第一句）
        para = evals._index_by_timestamp(md.read_text(encoding="utf-8"), None)
        for key, text in list(para.items())[:5]:
            assert len(text) > 60, f"段落 {key} 文本过短，疑似只取了第一句：{text[:80]}"
        # 破折号三种形态归一
        assert evals._norm_frag("a -- b") == evals._norm_frag("a — b") == "a - b"
        # 真实长引语可核验
        card = Path(d) / "C.md"
        long_quote = None
        for key, text in idx.items():
            if len(text) > 200:
                long_quote = (key, text[:120])
                break
        assert long_quote, "逐字稿里找不到长段落"
        key, frag = long_quote
        card.write_text("---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
                        f"# C\n\n> 「{frag}」\n> —— [{key}]\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verified"] >= 1, f"真实长引语应核到：{r}"


def t_verify_quotes_accounting():
    """引用计数必须能加总还原，且长引语/多形态/并列定位都要能核到。

    这一条把第五轮 FIDELITY 前的一次误判固化成测试。当时 TED 卡
    「引用 44 个但只核到 3 条」，我一度以为是窗口收紧造成的漏检，逐条排查后
    发现是**统计口径 + 6 个工具缺陷**叠加，真实命中是 16/16。教训：
    **「引用数 ≠ 核验数」时必须先证明差额去哪了，否则就是在猜。**

    逐条固化的缺陷：
      #31 `_WINDOW_CAP=200` 把 216~248 字符的长引语切成半句→ 正则缺闭合符 → 整条丢
      #32 `if not cands: continue` 静默跳过 37 个引用 → 输出自相矛盾
      #33 窗口从时间戳位置起扫 → 闭合引号在时间戳之前同一行时永远扫不到
      #34 只认 `「」` 不认英文直引号 `"` → 直引号逐字引语全部漏核
      #35 英文语料里把中文 `「」`（作者行文）当引语 → 10 条必然假失败
      #36 更正记录 / front matter 里的时间戳被当真实引用
      #38 无条件开邻接 cue 窗口 → 串到隔壁 cue（引语与时间戳不匹配却判 pass）
      #39 并列时间戳 `[ts1]、[ts2]` 只核第一个 → 引语在第二个时误判 fail
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        srt = p / "a.srt"
        #cue1 故意含一段长句（>200 字符），cue2 是它的续句
        long_a = ("Procrastination is a very interesting thing because it is not really "
                  "about being lazy in the traditional sense of the word. " * 3).strip()
        srt.write_text(
            f"1\n00:00:00,000 --> 00:00:05,000\n{long_a}\n\n"
            "2\n00:00:10,000 --> 00:00:14,000\nThe second cue is a separate sentence here.\n\n"
            "3\n00:00:20,000 --> 00:00:24,000\nNow, the Dark Playground is a place that all of "
            "you procrastinators out there know very well.\n",
            encoding="utf-8")
        run(["transcript", str(srt)])
        md = p / "a.transcript.md"
        card = p / "C.md"
        # ① 长引语（#31）：完整一段 >200 字符，必须核到
        card.write_text(
            "---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
            f"# C\n\n> 「{long_a}」\n> —— [00:00:00.00]\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verified"] >= 1, f"长引语应核到（#31）：{r}"
        # ② 计数对账（#32）：任何引用都不许凭空消失
        rec = r.get("reconciliation", {})
        assert all(rec.values()), f"引用计数无法加总还原（#32）：{rec}"
        assert r["refs_by_kind"]["ts_quotes_checked"] + \
            r["refs_by_kind"]["ts_locator_only"] + \
            r["refs_by_kind"]["ts_unquoted"] == r["refs_by_kind"]["timestamp_refs"], \
            f"时间戳引用三态之和不等于总数：{r['refs_by_kind']}"
        # ③ 闭合引号在时间戳之前、同一行内（#33）
        card.write_text(
            "---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
            "# C\n\n> 「Now, the Dark Playground is a place that all of you procrastinators "
            "out there know very well.」——[00:00:20.00]\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verified"] == 1, f"同行闭合引语应核到（#33）：{r}"
        # ④ 英文直引号（#34）
        card.write_text(
            "---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
            "# C\n\n> 讲者原话是 \"Now, the Dark Playground is a place that all of you "
            "procrastinators out there know very well.\"（[00:00:20.00]）\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verified"] == 1, f"英文直引号引语应核到（#34）：{r}"
        # ⑤ 表格行里的中文「」不是引语（#35）：不得让 verdict 永远 fail
        card.write_text(
            "---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
            "# C\n\n| 概念 | 中文行文「每周一个盒子」的阶梯 | [00:00:20.00] | 描述列 |\n",
            encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verdict"] == "pass", f"表格里的中文行文不该判失败（#35）：{r}"
        assert r["refs_by_kind"]["ts_locator_only"] >= 1, \
            f"表格锚点应归入 locator_only（#35）：{r['refs_by_kind']}"
        # ⑥ front matter / 行内代码里的时间戳不是引用（#36）
        card.write_text(
            "---\nname: c\ndescription: |\n  描述里带时间戳 [00:00:20.00] 也不该被核。\n---\n"
            "# C\n\n> 「Now, the Dark Playground is a place that all of you procrastinators "
            "out there know very well.」\n> —— [00:00:20.00]\n"
            "> 更正：曾误标为 `[00:00:10.00]`。\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["refs_by_kind"]["timestamp_refs"] == 1, \
            f"front matter/行内代码的时间戳应被挖空（#36）：{r['refs_by_kind']}"
        # ⑦ 邻接 cue 不得串味（#38）：完整单句不得跨 cue 匹配
        card.write_text(
            "---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
            "# C\n\n> 「The second cue is a separate sentence here.」\n> —— [00:00:20.00]\n",
            encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verdict"] == "fail", f"引语与时间戳不匹配必须判失败（#38）：{r}"
        # ⑧ 并列时间戳（#39）：引语落在第二个 ts 上也要算命中
        card.write_text(
            "---\nname: c\ndescription: |\n  测试用卡片，描述足够长以通过长度检查。\n---\n"
            "# C\n\n| 招牌概念 | **Dark Playground**（\"Now, the Dark Playground is a place that all "
            "of you procrastinators out there know very well.\"） | [00:00:10.00]、"
            "[00:00:20.00] | 说明列 |\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert r["verified"] >= 1, f"并列时间戳任一命中即通过（#39）：{r}"


def t_verify_quotes_attribution_block():
    """缺陷 #40：**归属声明块**里的引号不是来源引语。

    卡片有一类专门说明"这段到底是谁说的"的块：

        > ⚠️ **归属拆分**：来源给了前半；
        > 但「把粒度缩到今晚能做完」这层**是本卡自加**——原文没给对策（[ts]）

    块里的「」引用的是**本卡要描述的做法名**，不是素材原话，按引语去核必然核不到
    → 卡片明明没错却被判"来源不实"。这是我第三次踩同一个坑，前两次都靠改卡片措辞
    躲过去（治标），本次改为让工具认得"归属声明块"这个结构。

    同时必须保证不误伤：**不含归属抬头的正文块里，中文引语仍要照常核**（否则会重演
    缺陷 #37——过滤太激进导致真问题被降级成 pass，由 t_verify_quotes_timestamp 守住）。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        corpus = d / "c.md"
        corpus.write_text(
            "[00:00:01.00] The first real sentence from the source material here.\n"
            "[00:00:05.00] The second real sentence, different from the first one.\n",
            encoding="utf-8")

        # ① 归属声明块 + 正文真引语：真引语应核到，归属块内的中文不得报错
        card = d / "card.md"
        card.write_text(
            "> ⚠️ **归属拆分**：素材给了判据（见 [00:00:01.00]）；\n"
            "> 但「把粒度缩到今晚能做完」这条做法**是本卡自加**——原文没给对策。\n"
            "\n"
            "> 「The first real sentence from the source material here.」\n"
            "> —— [00:00:01.00]\n",
            encoding="utf-8")
        r = evals.verify_quotes(card, corpus)
        assert r["verdict"] == "pass", f"归属块被误判为引语错误：{r}"
        assert r["verified"] >= 1, f"正文真引语反而没核到：{r}"

        # ② 对照组：同样的中文引号，放在**没有归属抬头的正文块**里，必须照常报错
        card2 = d / "card2.md"
        card2.write_text(
            "> 「这句话根本不在逐字稿里出现过。」\n"
            "> —— [00:00:05.00]\n",
            encoding="utf-8")
        r2 = evals.verify_quotes(card2, corpus)
        assert r2["verdict"] == "fail", (
            f"正文块里的中文引语必须仍能被检出（防止过度放宽导致 #37 重演）：{r2}")


def t_verify_quotes_book_block():
    """第三方测评 #2 / 报告 P1：书类引用块纳入候选 + 空集守卫（含出处信号区分）。

    书类语料（material_type: book）的引语写成 `> 「…」\n> —— 《书名》第N段` 或
    `> —— 同上`，**不带** `【第N条】` / `[ts]` 定位标记。工具必须把这类引用块当作
    引语候选去语料里核验，否则会空集假绿（与 anchor / audit-coverage 同源缺陷）。

    但卡片自己的行文也大量用「」（概念包装，如「七个可以回答的问题」），
    **没有出处信号**——若一律当引语去核 → 整篇必然 unverified（假红）。
    因此只认带出处信号的引用块为书类引语候选；无信号的一律视为作者行文跳过。

    同时验证空集守卫：卡片只含作者行文「」、无任何可识别出处/定位 → vacuous=True，
    不得印「✅ 全部核到」（那正是报告点名的"引用 0 → 通过"假绿）。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        corpus = d / "book.txt"
        corpus.write_text(
            "【第1段】兵者，國之大事，死生之地，存亡之道，不可不察也。"
            "故經之以五事，校之以計，而索其情。\n"
            "【第2段】凡此五者，將莫不聞，知之者勝，不知者不勝。"
            "多算勝，少算不勝，而況於無算乎！\n",
            encoding="utf-8")

        # ① 真实书类引语（带出处信号）+ 作者行文概念引号（无出处信号）
        card = d / "card.md"
        card.write_text(
            "> 「兵者，國之大事，死生之地，存亡之道，不可不察也。"
            "故經之以五事，校之以計，而索其情」\n"
            "> —— 《孫子兵法·計篇》第1段\n"
            "\n"
            "> 「凡此五者，將莫不聞，知之者勝，不知者不勝。」\n"
            "> —— 同上\n"
            "\n"
            "> 这套方法解决的是：**如何把「不确定」变成「七个可以回答的问题」**。"
            "它不预测结果。\n"
            "\n"
            "> 「多算勝，少算不勝，而況於無算乎！」\n"
            "> —— 《孫子兵法·計篇》第2段\n",
            encoding="utf-8")
        r = evals.verify_quotes(card, corpus)
        assert r["book_block"]["checked"] == 3, f"应核到 3 条书类引语：{r}"
        assert r["book_block"]["verified"] == 3, f"3 条书类引语应全部核到：{r}"
        assert r["book_block"]["no_provenance_blocks"] >= 1, (
            f"作者行文概念引号块应被记为无出处信号、跳过：{r}")
        assert not r["unverified"], f"作者行文概念引号不得被误判 unverified：{r}"
        assert r["verdict"] == "pass", f"真实书类引语应判 pass：{r}"

        # ② 空集守卫：只有作者行文「」、无任何可识别出处/定位 → vacuous
        card2 = d / "card2.md"
        card2.write_text(
            "> 这套方法解决的是：**如何把「七个可以回答的问题」变成可执行步骤**。\n",
            encoding="utf-8")
        r2 = evals.verify_quotes(card2, corpus)
        assert r2["vacuous"] is True, f"无出处信号且含引语候选应触发 vacuous：{r2}"
        assert r2["verdict"] == "vacuous", f"vacuous 不得判通过：{r2}"

        # ③ 带出处信号却是伪造引语 → 必须 fail（不能因"有出处"就放行）
        card3 = d / "card3.md"
        card3.write_text(
            "> 「这句原文根本不存在于语料里，是随手编的。」\n"
            "> —— 《孫子兵法·計篇》第3段\n",
            encoding="utf-8")
        r3 = evals.verify_quotes(card3, corpus)
        assert r3["book_block"]["checked"] == 1, f"伪造书类引语应被计入候选：{r3}"
        assert r3["verdict"] == "fail", f"伪造书类引语（带出处）必须 fail：{r3}"
        assert r3["unverified"], f"伪造引语应进 unverified：{r3}"


def t_no_unqualified_absence_claims():
    """C4/#42：卡片不得出现**无限定的"素材里没有 X"全称判断**。

    真实教训：卡片写过"逐字稿中**找不到**支持该论断的文本"，
    而评分员回原文一查——讲者本人就说过论文 very very bad、
    也说过无期限时 Panic Monster 不出现，两处都是该判断的文本支持。
    **这句全称断言被原文直接推翻**，而且本卡早先就在更正记录里写过
    "'素材里没有 X'这种全称判断极易翻车"这条教训——**写了教训还是复发**。

    断言刻意做成**语义级**而非字面级（字面级正是 #39 的教训）：
    只在正文中查找"找不到/查无 + 支持/依据/文本/证据"这类缺席型全称句式，
    并要求它要么带了范围限定（就该处/本处/此处/该句），要么位于元描述框内。
    """
    import re
    card = external_ws("video-run/skills/two-kinds-of-procrastination/SKILL.md")
    if card is None:
        skip_ws("t_no_unqualified_absence_claims", "video-run 的 TED 卡")
        return
    _ABSENCE = re.compile(r"(找不到|查无)[^。；\n]{0,16}(支持|依据|文本|证据)")
    _SCOPED = ("就该处", "本处", "此处", "该句", "这一处", "在本处")
    _META = ("措辞修正", "更正记录", "归属拆分", "口径统一", "本轮")
    offenders = []
    for i, ln in enumerate(card.read_text(encoding="utf-8").splitlines(), 1):
        if not _ABSENCE.search(ln):
            continue
        if any(k in ln for k in _SCOPED):
            continue            # 已限定范围，可接受
        if any(k in ln for k in _META):
            continue            # 元描述框内引用的是"被修正的说法"，不是当前主张
        offenders.append(f"L{i}: {ln.strip()[:90]}")
    assert not offenders, (
        "发现无限定的素材缺席型全称判断（应限定到具体一处，"
        f"或改写成『讲者给了事实，但没做这一步概括』）：\n  " + "\n  ".join(offenders))


def t_eval_freeze_integrity():
    """C7：评分期间冻结被评对象。

    上轮我在 FIDELITY 评分 Agent 读材料期间改了卡片，它在报告里写"提出时我已改好"——
    无法区分"一开始就错"与"中途被改"。现在用指纹快照把这件事变成可检项。
    素材不在包内时跳过。
    """
    import hashlib
    snap = external_ws("video-run/eval/FROZEN.snapshot.json")
    if snap is None:
        skip_ws("t_eval_freeze_integrity", "video-run 的冻结快照")
        return
    data = json.loads(snap.read_text(encoding="utf-8"))
    for key in ("card", "corpus"):
        item = data[key]
        p = Path(item["path"])
        if not p.exists():
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        assert h == item["sha256"], (
            f"{key} 在冻结后被改动：{h[:16]} != {item['sha256'][:16]}。"
            "评分期间不得修改被评对象；如需修改，先重跑答题与评分。")


def t_real_sample_artifacts():
    """真实样本（书籍 / 人物 / 视频）三处产物必须齐备且可核验。"""
    import json as _json
    # 孙子样本卡随包分发 → **在干净 clone 上也必须真跑**，不得因外部素材缺失而跳过。
    sunzi = ROOT / "examples" / "sample-bundle" / "skills" / "five-affairs-seven-questions" / "SKILL.md"
    assert sunzi.exists(), "样本卡应随包分发，缺失属打包事故"
    # 开放素材臂（P0-2）：論語卡随包分发（examples/open-bundle），干净 clone 上也必须真跑。
    # 它证明工具链不只吃小样本，也能吃 25 万字节级的公有领域典籍并产出可核验卡。
    lunyu = ROOT / "examples" / "open-bundle" / "skills" / "lunyu-conduct" / "SKILL.md"
    assert lunyu.exists(), "开放素材样本卡应随包分发，缺失属打包事故"
    r = run(["validate", str(lunyu.parent)])
    assert "error 0" in r.stdout, f"論語卡未通过静态校验：{r.stdout}"
    sources = lunyu.parent / "SOURCES.md"
    assert sources.exists(), "論語卡缺 SOURCES.md 来源声明"
    stext = sources.read_text(encoding="utf-8")
    assert "公有领域" in stext, "SOURCES.md 未声明公有领域来源"
    externals = [("人物(马斯克)", external_ws("musk-run/skills/musk-thinking/SKILL.md")),
                 ("视频(TED)", external_ws("video-run/skills/two-kinds-of-procrastination/SKILL.md"))]
    ok: dict[str, Path] = {}
    for name, pth in externals:
        if pth is None:
            skip_ws("t_real_sample_artifacts", f"{name} 卡片")
            continue
        r = run(["validate", str(pth)])
        assert "error 0" in r.stdout, f"{name} 卡片未通过静态校验：{r.stdout}"
        ok[name] = Path(pth)
    # 视频素材必须是真实抓取（声明里有 URL 与抓取日期）
    ted = ok.get("视频(TED)")
    if ted is not None:
        head = ted.read_text(encoding="utf-8")[:1200]
        assert "youtube.com/watch" in head, "视频卡缺来源 URL"
        assert "2026-10-04 抓取" in head, "视频卡缺抓取日期"
        qv = external_ws("video-run/eval/quote-verification.json")
        if qv is not None:
            d = _json.loads(Path(qv).read_text(encoding="utf-8"))
            assert d["verified"] > 0 and not d["unverified"], f"视频卡引语未全部核到：{d}"


def t_style_decoy_anonymity():
    """C8：盲测材料不得泄露哪个候选来自被测卡片。

    第二轮评分员指出：`style-decoys.md` 顶部写着"候选 B 由出题方撰写"，
    等于把答案告诉评分者——维度 2 的盲测因此不可信。
    """
    f = external_ws("video-run/eval/style-decoys.md")
    if f is None:
        skip_ws("t_style_decoy_anonymity", "video-run 的盲测材料")
        return
    text = f.read_text(encoding="utf-8")
    leak = [w for w in ("由出题方", "出题人", "主 Agent", "刻意写成", "不是**被测",
                        "对照样本", "作者披露") if w in text]
    assert not leak, f"盲测材料泄露了候选来源：{leak}"
    assert "候选 A" in text and "候选 B" in text, "两个候选都在？"


def t_disclosure_completeness():
    """C9：卡片的「素材未涉及 / 本卡自加」小节必须真的有内容。

    上一轮我写「逐条列明」却漏了 6 项——承诺不兑现等于虚假。
    这里做最低限度检查：小节存在、且列出 ≥5 条、且每条带出处或理由。
    """
    card = external_ws("video-run/skills/two-kinds-of-procrastination/SKILL.md")
    if card is None:
        skip_ws("t_disclosure_completeness", "video-run 的 TED 卡")
        return
    text = card.read_text(encoding="utf-8")
    assert "素材未涉及 / 本卡自加" in text, "缺少披露小节"
    sec = text.split("素材未涉及 / 本卡自加", 1)[1]
    rows = [ln for ln in sec.splitlines()
            if ln.strip().startswith("|") and "---" not in ln and "本卡自加" in ln or
            (ln.strip().startswith("|") and "第二轮评分指出的披露缺口" in sec)]
    listed = [ln for ln in sec.splitlines() if ln.strip().startswith("|")
              and "---" not in ln and "位置" not in ln and "性质" not in ln
              and "本卡" not in ln.split("|")[1]]
    # 断言**不能绑死在某一句措辞上**——刚吃过亏：卡片把"被关住的是焦虑，不是债"
    # 改成"代价没有被消除，只是被期限限制了范围"后，原先硬编码字符串
    # `assert "他没说被关住的是" in text` 立刻假失败，而卡片其实申报得很完整。
    # 改成语义判据：A1 可迁移点下的每一条自加概括都必须在披露表里有登记行。
    _mig_rows = [ln for ln in sec.splitlines()
                 if ln.strip().startswith("|") and "A1 可迁移点" in ln]
    assert len(_mig_rows) >= 2, (
        f"A1 可迁移点的自加概括未全部登记：只有 {len(_mig_rows)} 行。"
        "该处的概括（此前名句『被关住的是焦虑，不是债』即其中之一）"
        "曾引发答题者当素材内结论引用的泄漏，必须逐条申报。")
    assert all(("本卡" in ln and ("概括" in ln or "计算" in ln)) for ln in _mig_rows), (
        f"登记行缺少『本卡的概括 / 本卡计算』性质标注：{_mig_rows}")


def t_audit_coverage_runs():
    """audit-coverage 必须能跑通，且阈值敏感时输出分布而不是只给结论。

    背景：这个工具第一版默认阈值 0.30，对"中文卡片 + 英文语料"会给出
    **虚假的 100% 覆盖**——我差点据此交差。教训：度量工具的默认值也可能是错的。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    card = external_ws("video-run/skills/two-kinds-of-procrastination/SKILL.md")
    corpus = external_ws("video-run/sources/arj7oStGLkU.en.transcript.md")
    if card is None or corpus is None:
        skip_ws("t_audit_coverage_runs", "video-run 的 TED 卡与逐字稿")
        return
    loose = evals.audit_coverage(card, corpus, threshold=0.30)
    strict = evals.audit_coverage(card, corpus, threshold=0.60)
    assert strict["uncovered"] >= loose["uncovered"], "阈值提高后未覆盖数不该减少"
    assert strict["coverage_rate"] <= loose["coverage_rate"]
    assert "coverage_distribution" in loose and loose["coverage_distribution"]["max"] > 0
    assert strict["paragraphs_total"] == 34, strict["paragraphs_total"]

    # ↓ 这一组取代了旧断言 `assert strict["uncovered"] > 0`（"不可能 100%，否则阈值失效"）。
    # 旧断言是**拿结果反推**：它假设卡片永远做不到真覆盖，一旦卡片真的补到 100%
    # 就会误报成功→失败，逼着人去改卡片而不是信工具。而且它没有真正解决问题：
    # 0.30 与 0.60 都已分别给出过虚假 100%（同一类错误第三次）。
    #
    # 根治是把自检责任放进工具：**谁报 100%，谁负责证明这个 100% 站得住**。
    for name, r in (("loose", loose), ("strict", strict)):
        assert "threshold_fragile" in r, f"{name} 缺少阈值脆弱性标记"
        assert "threshold_sensitivity" in r, f"{name} 缺少阈值敏感性表"
        assert "strict_reference" in r, f"{name} 缺少更严格参考档"
        sens = r["threshold_sensitivity"]
        keys = [float(k) for k in sens]
        rates = [sens[k]["coverage_rate"] for k in sorted(sens, key=float)]
        assert rates == sorted(rates, reverse=True), (
            f"{name} 覆盖率必须随阈值单调不增，实际 {list(zip(sorted(keys), rates))}")

    # 关键契约：**报出 0 段未覆盖时，工具必须自己标记为脆弱**。
    # 这样"100% 覆盖"永远无法被单独引用，必须连同更严格档的读数一起呈现。
    if strict["uncovered"] == 0:
        assert strict["threshold_fragile"] is True, (
            "覆盖审计报出 0 段未覆盖，却未标记 threshold_fragile——"
            "这正是被虚假 100% 骗过两次的原因。达到满覆盖时必须显式声明结论脆弱。")
        assert strict["threshold_margin"] < 0.08, strict["threshold_margin"]
        assert strict["strict_reference"]["uncovered"] > 0 or strict["threshold_margin"] >= 0.08


def t_disclosure_covers_uncovered():
    """披露清单必须登记 audit-coverage 报出的未覆盖段落（穷举维护的闭环检查）。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals
    card = external_ws("video-run/skills/two-kinds-of-procrastination/SKILL.md")
    corpus = external_ws("video-run/sources/arj7oStGLkU.en.transcript.md")
    if card is None or corpus is None:
        skip_ws("t_disclosure_covers_uncovered", "video-run 的 TED 卡与逐字稿")
        return
    text = card.read_text(encoding="utf-8")
    res = evals.audit_coverage(card, corpus, threshold=0.60)
    sec = text.split("素材未涉及 / 本卡自加", 1)[-1]
    missing = [u["ts"] for u in res["uncovered_paragraphs"] if u["ts"] not in sec]
    assert not missing, f"这些未覆盖段落没在披露清单里登记：{missing}"


def t_ci_present():
    """CI 必须齐备：4 个 workflow 各管一类风险（对齐仓颉的 4 个）。

    仓颉的 4 个是 pipeline-check / registry-check / deploy-pages / update-star-history，
    其中后两个依赖它自己的 `website/`（Astro 站点）——**TD 没有该目录，按文件名照抄等于造假**。
    因此按**职能**对齐而非按文件名：
      pipeline-check  代码回归 + 红线扫描
      contract-check  契约合规 + vendored 上游完整性
      artifact-check  随包产物可核验（含 verify-quotes 防空集通过）
      docs-check      文档声明的数字与代码不漂移
    """
    wfdir = ROOT / ".github" / "workflows"
    for name in ("pipeline-check", "contract-check", "artifact-check", "docs-check"):
        assert (wfdir / f"{name}.yml").exists(), f"缺少 workflow：{name}.yml"
    text = (wfdir / "pipeline-check.yml").read_text(encoding="utf-8")
    assert "tests/e2e.py" in text, "CI 未跑回归"
    assert "--tiktoken" in text, "CI 未覆盖完整依赖模式"
    assert "td.py validate" in text, "CI 未做静态校验"
    assert "红线" in text or "grep -rnE" in text, "CI 未做红线扫描"


def _td_skip_rel(rel: Path) -> bool:
    """C11（2026-10-09 复审 #2）：已安装副本比对时跳过生成物/缓存。

    跑过 `td.py chunk` 后磁盘上会出现 `<src>.td/` 侧车目录，runs/、.snapshots/、
    .staging/ 也是运行留痕——这些已 gitignore，但 C11 比对的是磁盘实际文件，
    不跳过会误报"全局副本缺 N 个文件"。复审实测：在仓库跑一次 chunk 生成
    `sunzi-ji.txt.td/`，C11 立即以"缺 7 个文件"失败。
    """
    skip = {".git", "__pycache__", ".pytest_cache", "runs", ".snapshots", ".staging"}
    if set(rel.parts) & skip or rel.suffix == ".pyc":
        return True
    if any(p.endswith(".td") for p in rel.parts):  # chunk 侧车目录 <src>.td/
        return True
    return False


def t_installed_copy_in_sync():
    """C11：已安装副本（`~/.workbuddy/skills/rulai-distill`）必须与项目目录一致。

    缺陷 #44：本包在项目里开发，但**技能被调用时加载的是全局副本**。
    改完项目目录忘了同步 → 修复在真实使用中根本没生效，而且没有任何报错
    （回归测试跑的是项目目录，永远是绿的）。
    这次是我把 cross-review / 3 个 workflow / VENDOR.sha256 全补在项目里，
    全局副本还停在改名前那一版 —— 门禁写了等于没写。
    """
    import filecmp
    installed = Path(os.path.expanduser("~/.workbuddy/skills/rulai-distill"))
    if not installed.exists():
        # 未安装（CI / 别人的机器）不是缺陷，但要说清楚，不能静默跳过
        assert os.environ.get("TD_SKIP_INSTALL_CHECK") is None, "检查逻辑异常"
        return
    diffs, missing = [], []
    for src in sorted(ROOT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(ROOT)
        if _td_skip_rel(rel):
            continue
        dst = installed / rel
        if not dst.exists():
            missing.append(str(rel))
        elif not filecmp.cmp(src, dst, shallow=False):
            diffs.append(str(rel))
    assert not missing, f"全局副本缺 {len(missing)} 个文件（改完没同步？）：{missing[:8]}"
    assert not diffs, f"全局副本有 {len(diffs)} 个文件与项目不一致（改完没同步？）：{diffs[:8]}"


def t_c11_skips_generated_artifacts():
    """C11（复审 #2）：生成物必须被跳过，不能误报「全局副本缺 N 个文件」。

    复审实测：在仓库跑一次 chunk 生成 `sunzi-ji.txt.td/`，C11 立即以「缺 7 个文件」失败——
    而 .gitignore 当时只写 `*.md.td/`，源码是 .txt 时漏掉（项目自己的样本就是 .txt）。
    """
    assert _td_skip_rel(Path("sunzi-ji.txt.td/chunks.jsonl")), \
        "chunk 侧车目录 *.td/ 必须被 C11 跳过"
    assert _td_skip_rel(Path("runs/x.json")), "runs/ 必须被跳过"
    assert _td_skip_rel(Path(".snapshots/y")) and _td_skip_rel(Path(".staging/z")), \
        ".snapshots/ 与 .staging/ 必须被跳过"
    assert not _td_skip_rel(Path("scripts/td.py")), "正常源码文件不能被跳过"
    assert not _td_skip_rel(Path("SKILL.md")), "正常文档不能被跳过"
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.td/" in gi, ".gitignore 必须忽略 *.td/（源码是 .txt 时也覆盖）"


def t_validate_exempts_references():
    """复审 #4：references/ 下的 .md 是参考资料，不是技能卡。

    当成卡片校验会因缺 frontmatter 而误判「不允许发布」（guoxue 的 bazi/zhouyi 实测中招）。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import validate as V
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        sk = base / "skills" / "demo"
        (sk / "references").mkdir(parents=True)
        (sk / "SKILL.md").write_text(
            "---\nname: demo\ndescription: 用于演示校验豁免。不做：通用问答。\n---\n\n"
            "# E — 可执行步骤\n\n**Step 1 · 做**\n\n完成标准：做完。\n\n"
            "# B — 边界\n\n失败模式：无。\n", encoding="utf-8")
        (sk / "references" / "yijing.md").write_text(
            "# 参考\n\n这是参考资料，不是卡片，没有 frontmatter。\n", encoding="utf-8")
        problems, stats = V.validate_path(base)
    errs = [p for p in problems if p[0] == "error"]
    assert not any("references" in p[1] for p in errs), \
        f"references/ 下的 .md 不应按卡片校验：{[p for p in errs if 'references' in p[1]]}"
    assert stats["docs"] >= 1, \
        f"references/*.md 应被记为 docs（不是卡片）：{stats}"


def t_publish_source_url_rulai():
    """复审 #4：registry 元数据的 source_url 不能硬编码成上游 cangjie 仓库。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import publish as P
    entry = P._registry_entry(
        {}, {"slug": "demo", "fidelity_score": 90, "fidelity_grade": "A"},
        {}, "pack", Path("/nonexistent-staging"))
    assert entry["source_url"] == "https://github.com/yihexiang/rulai-distill", \
        f"source_url 应为本项目仓库，实际 {entry['source_url']}"
    assert "cangjie" not in entry["source_url"], "source_url 不得指向上游 cangjie 仓库"


def t_verify_quotes_display_merges_book_block():
    """复审 #3：头部「引用 N 个」必须把书类引用块算进去。

    否则会出现「引用 0 个」与「逐字引语核验 3 条」并列的矛盾读感。
    """
    card = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md"
    corpus = ROOT / "examples/sample-bundle/sources/sunzi-ji.txt"
    proc = run(["verify-quotes", str(card), str(corpus)], expect=0)
    line = next((l for l in proc.stdout.splitlines()
                 if "引用" in l and "个" in l and "书类" in l), "")
    assert line, f"引用行未计入书类引用块：{proc.stdout[:400]}"
    assert "书类引用块 3" in line, f"书类引用块计数应为 3：{line!r}"


def t_anchor_book_corpus():
    """复审 #1：anchor 必须原生支持书类 `【第N段】` 语料 + 书类引用块写法。

    此前 split_paragraphs 只认 [时间戳]，书类语料直接 ValueError；
    且书类卡把段号写在**下一行**的出处行（`> —— 《书》第N段`），必须向后看绑定。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor as A
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        corpus = base / "book.txt"
        corpus.write_text(
            "【第1段】\n兵者，國之大事，死生之地，存亡之道，不可不察也。"
            "故經之以五事，校之以計，而索其情。\n\n"
            "【第2段】\n凡此五者，將莫不聞，知之者勝，不知者不勝。\n",
            encoding="utf-8")
        paras = A.split_paragraphs(corpus.read_text(encoding="utf-8"))
        assert set(paras) == {1, 2}, \
            f"书类语料应按显式段号切成 {{1, 2}}，实际 {set(paras)}"
        corpora = A.load_corpora([corpus])
        # 书类卡写法：引语在前、出处（第N段）在下一行；后续引语用「同上」跨块沿用
        card = base / "card.md"
        card.write_text(
            "# 卡片\n\n"
            "> 「兵者，國之大事，死生之地，存亡之道，不可不察也。」\n"
            "> —— 《孙子兵法·計篇》第1段\n\n"
            "> 「故經之以五事，校之以計，而索其情」\n"
            "> —— 同上\n\n", encoding="utf-8")
        rep = A.verify_file(card, corpora)
        assert rep["quotes_seen"] >= 2, \
            f"书类引用块里的引语必须被抽出来（含同上那块）：{rep['quotes_seen']}"
        assert rep["anchored_checked"] >= 2, \
            ("「同上」必须继承上一个显式段号（否则会退化成未标注段号）："
             f"verdict={rep['tally']} {rep['failures']}")
        assert rep["verdict"] == "PASS", f"书类卡应判 PASS：{rep['tally']} {rep['failures']}"
        # 挂错段号必须仍然能抓出来（加了书类支持不能让门槛变松）
        bad = base / "bad.md"
        bad.write_text(
            "> 「兵者，國之大事，死生之地，存亡之道，不可不察也。」\n"
            "> —— 《孙子兵法·計篇》第2段\n", encoding="utf-8")
        rep2 = A.verify_file(bad, corpora)
        assert rep2["verdict"] == "FAIL", \
            f"声明第2段、实际在第1段必须判 FAIL（挂错段号）：{rep2['tally']}"


def t_corpus_anchor_command():
    """复审 #1：corpus-anchor 把书类原文规整成 anchor 可读的【第N段】形式。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor as A
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        src = base / "raw.txt"
        src.write_text("第一段文字在这里。\n\n第二段文字在这里。\n", encoding="utf-8")
        out = base / "norm.txt"
        run(["corpus-anchor", str(src), "-o", str(out)], expect=0)
        text = out.read_text(encoding="utf-8")
    assert "【第1段】" in text and "【第2段】" in text, f"应产出连续段号：{text!r}"
    paras = A.split_paragraphs(text)
    assert set(paras) == {1, 2}, f"规整后应可被 anchor 切出 2 段：{set(paras)}"


def t_anchor_verifier():
    """引语段号锚定：必须能抓到「引语真实存在但挂错段号」（缺陷 #46）。

    背景（2026-10-05）：`verify-quotes` 验的是「引语在语料里存在吗」——全文搜，能过就算过。
    于是这条编造引用一路绿灯：
        §232 提到 "except with Uber"（他承认那是例外）
    它在 §233（`except with Uber Lilith` 是《暗黑破坏神》的 boss），
    而 §232 讲的是"我总是会做到"。**引语真实存在，只是挂错了段号与论点。**

    这是**门槛设计错误**，不是实现 bug。所以这个测试的第一条断言就是：
    **用那条真实的编造引用当输入，必须判 FAIL 且指出真实段号。**

    另含四条守卫（都是本模块开发时真实踩的坑）：
      - 空语料/无时间戳必须显式报错，不能静默返回 0 段 → 那样会对任何引语都 PASS
      - 段号只在**自己的来源内**解释（多份语料各有 §0~§275）
      - 并列锚点 §N/§N+1 都要认
      - 短引语（3 词）不许因低于 n-gram 下限而被跳过
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor

    d = Path(tempfile.mkdtemp())
    # 造一份两段语料，内容取自真实案例的结构
    corp = d / "t.md"
    corp.write_text(
        "[00:00:00.00] I would say that I am pathologically optimistic on schedule\n\n"
        "[00:00:30.00] but um while I am sometimes late I always l in the end uh except with Uber Lilith\n\n",
        encoding="utf-8")
    paras = anchor.split_paragraphs(corp.read_text(encoding="utf-8"))
    assert len(paras) == 2, f"段号切分失败：{len(paras)}（应为2）"

    # ① 核心：真实编造引用必须被抓到，且报出真实段号
    bad = d / "bad.md"
    bad.write_text('- **多选项概率决策**——§0 提到 "except with Uber"（他承认那是例外）\n',
                   encoding="utf-8")
    r = anchor.verify_file(bad, {"t": paras})
    assert r["verdict"] == "FAIL", "编造引用未被抓到——本测试存在的意义就是防这个"
    assert r["failures"], "FAIL 但没给出失配明细"
    assert r["failures"][0]["claimed_at"] == 0
    assert r["failures"][0]["found_at"] == 1, \
        f"未指出真实段号 §1：{r['failures'][0]}"

    # ② 短引语不许被跳过（3 词 < 5-gram 下限）
    r2 = anchor.check_quote_in_para("except with Uber", paras, target=0)
    assert r2["verdict"] == "SPAN_HIT", \
        f"短引语被跳过或误判：{r2['verdict']}（应抓到它其实在 §1）"

    # ③ 正确段号必须放行
    good = d / "good.md"
    good.write_text('- **时间表**——§0 "pathologically optimistic on schedule"\n', encoding="utf-8")
    assert anchor.verify_file(good, {"t": paras})["verdict"] == "PASS"

    # ④ 并列锚点 §0/§1 都要认
    both = d / "both.md"
    both.write_text('- **跨段**——§0/§1 "I am pathologically optimistic on schedule but um while I am sometimes late I always l in the end"\n',
                    encoding="utf-8")
    assert anchor.verify_file(both, {"t": paras})["anchored_checked"] == 1, \
        "并列锚点未被识别"

    # ⑤ 无时间戳的语料必须显式报错，不能静默 0 段 → 那样会对任何引语都 PASS
    broken = d / "broken.md"
    broken.write_text("no timestamp here at all\njust plain text\n", encoding="utf-8")
    try:
        anchor.split_paragraphs(broken.read_text(encoding="utf-8"))
        raise AssertionError("无时间戳语料未报错——会静默判0段然后对所有引语 PASS")
    except ValueError as e:
        assert "时间戳" in str(e)

    # ⑥ 来源解析：别名与实际键名必须同源（第一版带 .md 而键是 stem → 静默跳过整个来源）
    corp2 = d / "u.md"
    corp2.write_text("[00:00:00.00] second source marker line here now\n", encoding="utf-8")
    corpora = anchor.load_corpora([corp, corp2])
    assert anchor._resolve_src("t", corpora) == "t"
    assert anchor._resolve_src(None, corpora) in corpora
    # 解析不到时不得静默跳过
    assert anchor._resolve_src("src-99", corpora) is None or \
        anchor._resolve_src("src-99", corpora) not in corpora


def t_overlap_detector():
    """换素材重蒸馏前，「素材不重复」必须是可复现的数字，不能靠记忆判断。

    背景（2026-10-05）：第一轮用 17,144 条推文蒸馏，第二轮换三份访谈逐字稿重蒸，
    用户明确要求"资料来源和内容不要跟昨天重复"。若只凭"我换了三个来源"这句话，
    这条要求无法证伪。这个测试把 overlap 检测器钉住，且**必须能抓到 FAIL**——
    一个只会说 PASS 的检测器比没有更危险。

    2026-10-07（#47）：这条测试此前**从未被运行过**（漏登记，见 #45），
    一登记就红——原因不在检测器，而在夹具：`sentences()` 按 `[.!?]` 或空行切句，
    而我造的无标点单段文本被当成**一整句**，所以"整句复制"根本没形成两句。
    真实逐字稿是有标点的。这里改用真实语料形态，并补一条**无标点场景**的断言：
    即使切不出句子，8-gram 包含率也必须把重复抓出来（两层防护不能只测一层）。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import overlap

    d = Path(tempfile.mkdtemp())
    A1 = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"
    A2 = "the quick brown fox jumps over the lazy dog repeatedly every single day"
    B1 = "quantum photon lattice nucleus isotope meson baryon fermion gluon neutrino quark"
    B2 = "completely unrelated content about superconducting magnets and cryogenic plants"

    def w(name: str, *paras: str) -> Path:
        p = d / name
        p.write_text("\n\n".join(paras) + "\n", encoding="utf-8")
        return p

    a = w("a.md", A1 + ".", A2 + ".")
    b = w("b.md", B1 + ".", B2 + ".")

    r = overlap.compute(a, b)
    assert r["overlap_verdict"] == "PASS", f"不重叠语料被判FAIL：{r}"
    assert r["containment"] == 0.0
    assert r["exact_duplicate_sentences"] == 0
    assert r["new_sentences"] == 2, f"夹具本身就该切成 2 句：{r}"

    # 自身对自身：必须 FAIL，否则检测器是假的
    same = overlap.compute(a, a)
    assert same["overlap_verdict"] == "FAIL", "自身重叠未被判FAIL——检测器无效"
    assert same["containment"] > 0.99
    assert same["exact_duplicate_sentences"] >= 1

    # 整句复制（真实形态：有标点、能切成句子）必须被逐句检查抓到
    c = w("c.md", A1 + ".", "brand new sentence that never appeared in the old corpus at all")
    rc = overlap.compute(c, a)
    assert rc["overlap_verdict"] == "FAIL", f"整句复制未被检出：{rc}"
    assert rc["exact_duplicate_sentences"] >= 1, f"逐句重复未被抓到：{rc}"

    # 无标点场景：切不出句子，但 8-gram 包含率仍必须判FAIL（第二层防护）
    np_a = w("na.md", A1 + "\n" + A2)
    np_c = w("nc.md", A1 + "\n" + "entirely different tail words that were never in the source")
    rn = overlap.compute(np_c, np_a)
    assert rn["overlap_verdict"] == "FAIL", f"无标点的整段复制未被检出：{rn}"
    assert rn["containment"] > 0.005

    # 空集不得判 PASS（呼应「空集假绿」的老教训）
    empty = d / "e.md"
    empty.write_text("", encoding="utf-8")
    assert overlap.compute(empty, b)["new_shingles"] == 0, "空语料应产生 0 个 shingle"


def t_vendor_integrity():
    """C6：vendored 上游文件不得被改动——从文档承诺升级为机器校验。

    PROVENANCE.md 一直写「不修改上游文件」，但此前只是一条**人工审查项**：
    真改了没人会发现。这里用 `scripts/vendor/VENDOR.sha256` 基线做 sha256 比对。
    """
    import hashlib
    base = ROOT / "scripts" / "vendor"
    manifest = base / "VENDOR.sha256"
    assert manifest.exists(), "缺少 vendored 完整性基线：scripts/vendor/VENDOR.sha256"
    bad = []
    n = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        n += 1
        digest, rel = line.split(None, 1)
        rel = rel.strip()
        p = base / rel
        if not p.exists():
            bad.append(f"文件缺失：{rel}")
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(f"内容被改动：{rel}")
    assert n >= 20, f"基线条目过少（{n}），疑似生成不全"
    assert not bad, ("vendored 上游与基线不一致；若确为版本升级，请重新生成 VENDOR.sha256：\n  "
                     + "\n  ".join(bad))


def t_defect_ledger_stats():
    """CONSTRAINTS.md 声明的缺陷总数与分布，必须与台账实际一致。

    2026-10-05 实测：正文仍写「迄今 30 个缺陷」「11 个已知缺陷」，而实际台账 42 条。
    **台账自己也会腐烂**，且 t_defect_regression_ledger 只查表格行、查不到正文里的数字。
    这条把正文声明也纳入校验。
    """
    doc = (ROOT / "CONSTRAINTS.md").read_text(encoding="utf-8")
    _head, body = doc.split("## 已发现的自身缺陷台账", 1)
    actual = len([ln for ln in body.splitlines() if re.match(r"\| \d+ \|", ln)])
    # 分布表就在台账小节内（标题之后），所以只在 body 里找正文声明
    m = re.search(r"本项目迄今\s*\**\s*(\d+)\s*\**\s*个缺陷", body)
    assert m, "CONSTRAINTS.md 未声明缺陷总数，无法校验是否腐烂"
    assert int(m.group(1)) == actual, (
        f"声明总数 {int(m.group(1))} 与实际台账 {actual} 不一致——文档又腐烂了")
    cats = ["验证/度量工具自身", "生产侧代码", "我的判断方向错误（非代码）",
            "卡片内容真错", "vendored 上游代码"]
    total, found = 0, 0
    for name in cats:
        mc = re.search(r"\|\s*\**" + re.escape(name) + r"\**\s*\|\s*\**(\d+)\**\s*\|", body)
        if mc:
            found += 1
            total += int(mc.group(1))
    assert found == len(cats), f"分布表缺项：只找到 {found}/{len(cats)} 类"
    assert total == actual, f"分布表各项之和 {total} != 台账总数 {actual}"


def t_docs_no_drift():
    """文档声明的数字必须与代码一致，章节不得重复。

    2026-10-05 实测三处漂移：CONSTRAINTS.md 写「30 个 / 11 个」而实际 42；
    CAPABILITIES.md 写「46 项回归」而实际 58；「机制说明」整节重复了两遍。
    这些都是**纯文档缺陷**，没有任何测试能抓到，所以补这一条。
    """
    src = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    n_tests = len(re.findall(r"^def t_[a-z0-9_]+\(", src, re.M))
    cap = (ROOT / "CAPABILITIES.md").read_text(encoding="utf-8")
    m = re.search(r"\*{0,2}(\d+)\*{0,2}\s*项回归", cap)
    assert m, "CAPABILITIES.md 未声明回归项数"
    assert int(m.group(1)) == n_tests, (
        f"CAPABILITIES.md 声明 {m.group(1)} 项回归，实际 {n_tests} 项")
    con = (ROOT / "CONSTRAINTS.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", con, re.M)
    dup = [h for h in set(heads) if heads.count(h) > 1]
    assert not dup, f"CONSTRAINTS.md 有重复章节：{dup}"

    # 版本号：SKILL.md 是入口文件，它的 metadata.version 必须与 README 标题一致。
    # 2026-10-05 实测：SKILL.md 停在 1.1.0、README 标题停在 v1.2.0，而 changelog 已到 1.6.0——
    # **建完 docs-check 的当天就发现它漏了最该查的字段**，所以补在这里。
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    mv = re.search(r'^\s*version:\s*"?(\d+\.\d+\.\d+)"?', skill, re.M)
    assert mv, "SKILL.md 未声明 metadata.version"
    ver = mv.group(1)
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    mh = re.search(r"^#\s.*?v?(\d+\.\d+\.\d+)", rd, re.M)
    assert mh, "README.md 标题未标注版本号"
    assert mh.group(1) == ver, (
        f"版本号漂移：SKILL.md 是 {ver}，README.md 标题是 {mh.group(1)}")

    # 2026-10-07（#48）：**代码里的版本号**也必须跟着走。
    # 上面两条只管文档，但 `tdlib/util.py` 曾硬编码 `VERSION = "1.1.0"`——
    # 于是 `td.py doctor` 在 1.6.0 的包上打印「v1.1.0」。
    # **用户看到的就是错的那个**，所以版本号必须只有一个真源（SKILL.md）。
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib.util import VERSION as RUNTIME_VERSION
    assert RUNTIME_VERSION == ver, (
        f"运行时版本号 {RUNTIME_VERSION} 与 SKILL.md 的 {ver} 不一致"
        "——`td.py doctor` 会打印错的版本")

    # 2026-10-05 第二轮实测：上面那条只查了 CAPABILITIES.md / CONSTRAINTS.md / 两处版本号，
    # 结果 SKILL.md 自己写着「回归 29 项」、README 写着「25 项」（实际 63）都没被抓到，
    # README 能力对齐表的表头还停在 v1.1.0，且 v1.6.0 的段落整段重复两遍。
    # **守卫守卫了三个文件，漏了它自己所在技能的主入口。**
    #注意：实际写法是「回归：`python3 tests/e2e.py`（63 项」——数字前面隔着代码 span，
    # 所以不能只匹配「回归<数字>项」，必须按行取该行里的「N 项」。
    for name, text in (("SKILL.md", skill), ("README.md", rd)):
        for line in text.splitlines():
            if "回归" not in line or "e2e.py" not in line:
                continue
            for num in re.findall(r"(\d+)\s*项", line):
                assert int(num) == n_tests, (
                    f"{name} 声明回归 {num} 项，实际 {n_tests} 项：{line.strip()[:60]}")
    # 能力对齐表的表头版本必须等于当前版本（它列的是"本包现状"，不是历史版本）
    mtab = re.search(r"^\| 能力 \| 来源 \| rulai-distill v(\d+\.\d+\.\d+) \|", rd, re.M)
    assert mtab, "README.md 能力对齐表缺少版本标注"
    assert mtab.group(1) == ver, (
        f"README 能力对齐表表头是 v{mtab.group(1)}，实际当前版本是 v{ver}")

    # 通用扫描：所有 .md 里出现「N 项回归」的总项数声明（排除「第 N 项回归测试」这种
    # 特指某一条测试的写法）必须等于 n_tests。补这条是因为 73 / 63 这类漂移曾多次出现，
    # 且散落在 GUIDE.md / OPEN-SOURCE-ASSESSMENT.md 等"主守卫"没扫到的文件里。
    for md in sorted(ROOT.glob("**/*.md")):
        if "node_modules" in str(md) or md.name == "node_modules":
            continue
        for line in md.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "项回归" not in line or "第" in line or "e2e.py" in line:
                continue
            for num in re.findall(r"(\d+)\s*项回归", line):
                assert int(num) == n_tests, (
                    f"{md.name} 声明回归 {num} 项，实际 {n_tests} 项：{line.strip()[:60]}")

    # 2026-10-09（第三方测评 #2 / 报告 P2）：子命令数量纳入守卫。
    # README 与 cheatsheet 曾分别写 25 / 22，而实际新增命令后已到 34——
    # 典型的"文档声称 ≠ 代码行为"。现在用 argparse 解析实际子命令数强制一致。
    sys.path.insert(0, str(ROOT / "scripts"))
    import td as _td
    n_cmds = len(_td.build_parser()._subparsers._group_actions[0].choices)
    cheat = (ROOT / "references" / "command-cheatsheet.md").read_text(encoding="utf-8")
    for name, text in (("README.md", rd),
                       ("references/command-cheatsheet.md", cheat)):
        m = re.search(r"（(\d+)\s*个子命令）", text)
        assert m, f"{name} 未声明子命令数量（格式：『（N 个子命令）』）"
        assert int(m.group(1)) == n_cmds, (
            f"{name} 声明 {m.group(1)} 个子命令，实际 {n_cmds} 个：数字由各文件同步到 argparse")
    # README 首屏目录树里的 e2e 项数也要跟着走（形式：『端到端回归（N 项…）』）
    m_e2e = re.search(r"端到端回归（(\d+)\s*项", rd)
    assert m_e2e, "README.md 未标注 e2e 回归项数"
    assert int(m_e2e.group(1)) == n_tests, (
        f"README 声明 e2e {m_e2e.group(1)} 项，实际 {n_tests} 项")

    # 段落级重复：README 首屏的版本说明整段重复过一次（同样是在 docs-check 之后才出现）
    for para in re.findall(r"^(?:\*\*v\d+\.\d+\.\d+[^\n]*\n(?:\*\*[^\n]*\n|[^\n*][^\n]*\n){1,4})",
                           rd, re.M):
        assert rd.count(para) <= 1, f"README.md 有整段重复：{para[:40]!r}"


def t_schema_and_help():
    assert "bundle.schema.json" in run(["schema", "bundle"]).stdout
    h = run(["--help"]).stdout
    for cmd in ("chunk", "transcript", "research", "strategy", "trigger", "diff", "count"):
        assert cmd in h, f"--help 缺 {cmd}"


def t_token_savings_benchmark():
    """P0-3：token 节省实测脚本必须**不产假数字**。

    这个脚本的第一版量错了东西（读了 `document.json` 的 elements、字段名也不存在），
    算出的"省了 0.56 倍"（比整本还贵）却毫无报错——**量具坏了比没有量具更坏**。
    本条守住它最容易再次坏掉的几处：

    ① **没装 tiktoken 必须报"未运行"并以退出码 2 结束**，不许用字数估算顶替；
    ② **邻块必须去重**（命中块已在窗口里，相邻的命中块不能重复加）；
    ③ **退化样本要被标出来**：关键词只命中一个只有标题的块时，倍数会飙到四位数，
       那是"没读到正文"而不是"省得多"，必须置为退化、不进区间；
    ④ 命中 0 块不给倍数（0/0 写不成数字）；
    ⑤ **重复 --corpus 不能只保留最后一本**（argparse 的 `nargs='+'` 默认后者覆盖前者，
       曾导致报告里少一本书却零报错）。
    """
    sys.path.insert(0, str(ROOT / "benchmarks" / "token-savings"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "tk_save", ROOT / "benchmarks" / "token-savings" / "measure.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)

    # ① 没装 tiktoken → 明确未运行，退出码 2（用零依赖解释器模拟）
    proc = subprocess.run(
        [sys.executable, "-S", str(ROOT / "benchmarks" / "token-savings" / "measure.py"),
         "--corpus", str(ROOT / "README.md")],
        capture_output=True, text=True)
    # 有 tiktoken 时会正常跑完；没有时必须是 rc=2 且明说未运行。两者都不许给数字。
    if proc.returncode == 2:
        assert "未运行" in proc.stdout, f"必须明说未运行：{proc.stdout[-300:]}"
    else:
        assert proc.returncode == 0, f"装了 tiktoken 就该跑通：{proc.stderr[-500:]}"

    # ② 邻块去重：5 块里第 1、2 块连续命中 → 窗口 = 2×TOK，
    #    邻块是 0 与 3（1、2 互相是邻居但已在命中集合里，**不能再加一次**）
    #块大小必须 ≥200 token，否则会被「退化命中」判据接管（那是另一条守卫）
    TOK = 300
    rows = [{"id": f"ck-{i:04d}", "title": "t", "chars": TOK, "tokens": TOK,
             "text": "关键词命中" if i in (1, 2) else "无关正文"} for i in range(5)]
    r = M.measure(rows, lambda s: len(s), ["关键词"], 5 * TOK)
    assert r["tokens"]["window_hit_only"] == 2 * TOK, r["tokens"]
    assert r["tokens"]["window_with_neighbours"] == 4 * TOK, \
        f"邻块计数不对：{r['tokens']}（命中块被当邻块再加一次 = 6×TOK）"

    # 反向：全部命中时，邻块**不得**再加一遍（首版就错在这里，
    # 算出「窗口比整本还贵」的 0.56×）
    allhit = [{"id": f"ck-{i:04d}", "title": "t", "chars": TOK, "tokens": TOK,
               "text": "关键词命中"} for i in range(5)]
    r_all = M.measure(allhit, lambda s: len(s), ["关键词"], 5 * TOK)
    assert r_all["tokens"]["window_with_neighbours"] == 5 * TOK, \
        f"邻块重复计数了：{r_all['tokens']}"
    assert r_all["saving_vs_whole"]["window_with_neighbours"] == 1.0, \
        "全命中时窗口=整本，倍数必须是 1.0（不是 0.56 那种「越读越贵」）"

    # ③ 退化样本：命中块全是 7 token 的标题块 → 窗口倍数必须是 None 而非四位数
    tiny = [{"id": "ck-0000", "title": "五行元理消息赋", "text": "五行元理消息赋",
             "chars": 7, "tokens": 7}]
    r2 = M.measure(tiny, lambda s: len(s), ["五行元理消息"], 89614)
    assert r2["degenerate_hit_blocks"], "只有标题的命中块必须被标为退化"
    assert r2["saving_vs_whole"]["window_hit_only"] is None, \
        f"退化样本不该给倍数：{r2['saving_vs_whole']}"

    # ④ 一个都不命中 → hits_none，不许出现 0 或 None 混进区间
    r3 = M.measure(rows, lambda s: len(s), ["不存在的词"], 500)
    assert r3.get("hits_none") and r3["saving_vs_whole"] == {}, r3

    # ⑤ 重复 --corpus 必须都保留
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, nargs="+", action="extend")
    got = ap.parse_args(["--corpus", "A", "B", "--corpus", "C"]).corpus
    assert got == ["A", "B", "C"], f"重复 --corpus 丢了参数：{got}"


def t_shell_scripts_safe():
    """shell 脚本里三类「看起来正常、实际会静默出错」的写法（bash 实测判据）。

    本项目在同一个文件上栽了两次：`echo "…（$rc）"` 里全角括号紧跟变量名，
    bash 把多字节字符当成变量名的一部分 → 变量取空、**打印乱码、退出码仍是 0**。
    这比报错危险得多：**报错会停下，乱码会继续**。

    判据不是猜的，每条都跑过 bash：
    · `$VENV）` → 变量内容丢失（真错）
    · `$dest 是` → **后面有空格，安全**（首版把这两种混为一谈，一次报 8 处、
      其中 6 处假阳性——**误报的守卫等于没有守卫**）
    """
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "shell_safety.py")],
        capture_output=True, text=True)
    assert proc.returncode == 0, f"shell 脚本有不安全写法：\n{proc.stdout[-900:]}"
    assert "个 shell 脚本" in proc.stdout, proc.stdout[-300:]

    # 负向探针：造一个真的会静默出错的片段，扫描器必须抓到。
    #（只跑正向等于"检查器永远绿"——本项目吃过这个亏，#65）
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.sh"
        bad.write_text('#!/bin/bash\nVENV=/x/y\necho "找到（$VENV）"\n',
                       encoding="utf-8")
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ss", ROOT / "scripts" / "shell_safety.py")
        S = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(S)
        found = S.scan(bad)
        assert found, "扫描器没抓到 `$VENV）` —— 它对真错是瞎的"
        # 而 `$dest 是`（有空格）必须**不报**
        ok = Path(d) / "ok.sh"
        ok.write_text('#!/bin/bash\ndest=/x\necho "  $dest 是目录"\n',
                      encoding="utf-8")
        assert not S.scan(ok), \
            f"误报了安全的写法：{S.scan(ok)}——误报的守卫等于没有守卫"


def t_corpus_anchor_splits_by_structure():
    """#70：`corpus-anchor` 必须**按结构**切段，不能只按空行。

    真实公版典籍（维基文库导出）是「一行一段、无空行」格式。旧实现按空行切，
    628 行只切出 6 段（每段近万字）——而 CLI 照常打印「✅ 规整完成」。
    **这是比"切错"更隐蔽的失效**：它给出的是一个看起来合法的段号体系，
    没有异常、没有报错，可段号已经失去定位意义。

    本条守三件事：①按 markdown 标题切；②过长的段会被再切且**不丢内容**；
    ③段数过少时 CLI 必须警告。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib.anchor import normalize_book_corpus

    # 一行一段、无空行、每节一个标题——真实公版典籍的形状
    lines = ["---", "source_id: src-01", "---", ""]
    for vol in range(1, 31):
        lines += [f"## 卷{vol}", f"起著雍攝提格，盡玄黓困敦。凡三十五年。{'說' * 200}。"]
    text = "\n".join(lines)

    out, stats = normalize_book_corpus(text)
    assert stats["split_by"] == "headings", stats
    assert stats["segments"] >= 30, \
        f"31 个标题只切出 {stats['segments']} 段——又退回按空行了"
    assert out.startswith("【第1段】"), out[:40]
    # 段号连续、无跳号
    nums = [int(x) for x in re.findall(r"【第(\d+)段】", out)]
    assert nums == list(range(1, len(nums) + 1)), f"段号不连续：{nums[:10]}…"

    # ② --max-chars：超长段再切，且**一个字符都不许丢**。
    #    上限取 150（每节约 226 字）→ 必须触发再切。
    #    首版这里写 300，结果每节 226 字根本没超限，测试"通过"了却没测到东西
    #    ——**测试自身也要先确认它在测**。
    out2, st2 = normalize_book_corpus(text, max_chars=150)
    assert st2["segments"] > stats["segments"], \
        f"过长的段没有被再切（{stats['segments']} → {st2['segments']}）"
    def strip_marks(s):
        return re.sub(r"【第\d+段】\n?", "", s)
    # 比较时**忽略空白**：再切必然在切点补换行，正文一个字都不该变。
    # 直接比原文会因换行差异失败——那不是内容丢失，是切段留下的接缝。
    assert re.sub(r"\s+", "", strip_marks(out2)) == \
           re.sub(r"\s+", "", strip_marks(out)), \
        "再切之后正文变了——切段必须只拆不丢（忽略切点换行后应完全相同）"
    longest = max(len(b) for b in out2.split("【第")[1:])
    assert longest < 1000, f"仍有 {longest} 字的段（再切后应远小于 226）"

    # ③ CLI：段数过少必须警告（不警告 = 又一次静默失效）
    import tempfile as _tf
    with _tf.TemporaryDirectory() as d:
        f = Path(d) / "flat.md"
        f.write_text("一行一段。\n" * 900, encoding="utf-8")   # 无标题无空行
        proc = run(["corpus-anchor", str(f)], expect=0)
        assert "段号已失去定位意义" in proc.stdout, \
            f"段数过少时必须警告：{proc.stdout[-400:]}"


def t_claims_have_evidence():
    """P0-4：每条对外声称必须有**真实存在**的证据，数字不许腐烂。

    本项目最高频的病是「声称 ≠ 实际」：文档里写「12 张卡」而实际只有 9 张、
    写「2 张卡跑过交叉复核」而实际已经有 6 份报告——**都没有任何东西会红**。
    本条把「文档一致性」从自律变成门禁。

    关键在于**校验器自己也必须被校验**：
    首版把「数字腐烂」写成找 `{tests} = N`，而文档里根本没有这种写法，
    于是那条检查**永远匹配不到**——看上去有这一项，实际从不触发（#54 同一个病）。
    所以下面第③段用负向探针证明它真的会红。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "vc", ROOT / "docs" / "verify_claims.py")
    V = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V)

    claims_md = ROOT / "docs" / "CLAIMS.md"
    assert claims_md.exists(), "缺少 docs/CLAIMS.md——对外声称没有台账"
    text = claims_md.read_text(encoding="utf-8")

    # ① 正常状态必须全绿
    proc = subprocess.run([sys.executable, str(ROOT / "docs" / "verify_claims.py")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"声称台账核验未通过：\n{proc.stdout[-800:]}"
    claims = V.parse_claims()
    assert len(claims) >= 10, f"声称台账只有 {len(claims)} 条，太少等于没有"

    # ② 每条声称都必须有证据，且引用的测试名真实存在
    tests = V.registered_tests()
    for c in claims:
        assert c["evidence"] not in ("", "—", "-", "无"), \
            f"声称「{c['claim'][:30]}」没有证据"
        for t in re.findall(r"\bt_\w+", c["evidence"]):
            assert t in tests, f"声称引用了不存在的测试 `{t}`"

    # ③ 负向探针：篡改一个数字 → 必须报错。**这条守卫自己必须是红的**，
    #    否则"数字校验"又是一段永不触发的代码。
    with tempfile.TemporaryDirectory() as d:
        bak = Path(d) / "CLAIMS.md"
        bak.write_text(text, encoding="utf-8")
        try:
            broken = text.replace("tests = ", "tests = 9", 1)
            broken = re.sub(r"^tests = \d+", "tests = 999999", broken, count=1, flags=re.M)
            claims_md.write_text(broken, encoding="utf-8")
            bad = subprocess.run(
                [sys.executable, str(ROOT / "docs" / "verify_claims.py")],
                capture_output=True, text=True)
            assert bad.returncode != 0, \
                "篡改 facts 数字后校验器仍然通过——数字校验是死代码"
            assert "数字腐烂" in bad.stdout or "实际" in bad.stdout, \
                f"报错要说清是数字对不上：{bad.stdout[-300:]}"
        finally:
            claims_md.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")

    # ④ 事实数字只由 facts 段承载，并已同步到其他文档
    facts = V.read_facts()
    for k in ("tests", "subcommands", "defects"):
        assert k in facts, f"facts 段缺 {k}"
    m = re.search(r"<!-- facts:begin -->(.*?)<!-- facts:end -->", text, re.S)
    assert m, "缺少 <!-- facts:begin --> 段"
    # facts 段的数字必须与其他文档一致（不一致时 verify_claims 已会报，
    # 这里再钉一道，防止有人绕过脚本只手改某一份文档）
    for f in ("README.md", "SKILL.md", "GUIDE.md", "CAPABILITIES.md"):
        body = (ROOT / f).read_text(encoding="utf-8")
        for n in set(re.findall(r"(\d+)\s*项回归", body)):
            assert int(n) == facts["tests"], \
                f"{f} 写「{n} 项回归」，实际 {facts['tests']}（跑 verify_claims.py --sync）"


def t_guide_walkthrough():
    """GUIDE.md 写的黄金路径必须**端到端真的能跑通**，且每步都有实质产出。

    2026-10-07（#51）—— 这条是针对一整类缺陷的根治，不是又打一只地鼠：
    #48（doctor 打印过期版本）、#49（index 只搜标题）、#50（count 单文件报 0）
    **三条是同一个病**：我一直没按用户的实际路径把命令完整跑一遍。
    写了实现、写了测试、写了文档，却从没走过一次「init → chunk → index →
    count → validate → strategy → output-eval → prompt」这串用户真正会走的路。

    这个测试把那条路钉死。它的断言不是「没崩」，而是**每步都要有实质产出**：
    数字不能是 0、命中不能是空、产物必须非空。静默假绿在这里会变红。
    """
    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)

        # ① doctor：打印的版本必须等于 SKILL.md 的版本（否则用户看到的是错的）
        o = run(["doctor"], cwd=wd).stdout
        sk = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        ver = re.search(r'^\s*version:\s*"?(\d+\.\d+\.\d+)"?', sk, re.M).group(1)
        assert f"v{ver}" in o, f"doctor 没打印当前版本 v{ver}：{o[:200]}"

        # ② init：骨架必须真的落盘
        run(["init", "book"], cwd=wd)
        assert (wd / "book/bundle.json").exists(), "init 没生成 bundle.json"
        assert list((wd / "book/skills").glob("*.md")), "init 没生成能力卡骨架"

        # ③ chunk：造一份**带标点的真实形态**语料，正文里放一个只出现在正文的词
        src = wd / "src.md"
        src.write_text(
            "# 第一章 总纲\n\n"
            "本段讨论的是判断如何依赖前提，前提一旦变化结论就随之变化，因此要先固定前提。\n\n"
            "## 第一节 分述\n\n"
            "另一段讲完全不同的内容，用来验证分块边界与索引检索都落在正确的位置上。\n",
            encoding="utf-8")
        o = run(["chunk", str(src)], cwd=wd).stdout
        assert re.search(r"(\d+) 块", o) and int(re.search(r"(\d+) 块", o).group(1)) >= 2, \
            f"分块数不合理：{o[:200]}"

        # ④ index --grep：正文里的词必须能搜到（#49 回归；这个词不在任何标题里）
        o = run(["index", str(src) + ".td", "--grep", "前提"], cwd=wd).stdout
        assert "命中 0 块" not in o, f"正文关键词搜不到——又只搜了标题：{o[:200]}"
        assert re.search(r"命中 [1-9]\d* 块", o), f"命中数为空或异常：{o[:200]}"

        # ⑤ count：单个文件不能被算成 0（#50 回归）
        o = run(["count", str(src)], cwd=wd).stdout
        assert re.search(r"语料总量[^\d]*0\s*$", o, re.M) is None, \
            f"单文件语料总量被算成 0（静默假绿）：{o[:300]}"

        # ⑥ validate：骨架应零错误
        o = run(["validate", "book"], cwd=wd).stdout
        assert "error 0" in o, f"validate 报告了错误：{o[:300]}"

        # ⑦ strategy：必须给出一个明确推荐，不能空转
        o = run(["strategy", "book", "--purpose", "workflow"], cwd=wd).stdout
        assert ("推荐形态" in o) and ("pack" in o or "single" in o), f"strategy 没给结论：{o[:200]}"

        # ⑧ output-eval：对骨架卡做体检，必须真的报出规模与段数
        o = run(["output-eval", "book/skills/example-capability.md"], cwd=wd).stdout
        assert "六段" in o, f"output-eval 没报六段结构：{o[:200]}"

        # ⑨ prompt 编译：产物必须非空
        out = wd / "p.md"
        run(["prompt", str(ROOT / "SKILL.md"), "--out", str(out), "--mode", "entry"], cwd=wd)
        assert out.exists() and out.stat().st_size > 200, "prompt 产物为空"

        # ⑩ overlap：自身对自身必须判 FAIL（只会说 PASS 的检测器比没有更危险）
        run(["overlap", "--new", str(src), "--old", str(src)], expect=1, cwd=wd)


def t_no_control_chars():
    """仓库里的文本文件不得含控制字符（\\n \\t \\r 除外）。

    2026-10-07（#54）：我用 `re.sub(pat, '66\\2', text)` 做批量替换改回归项数，
    Python 把 `\\2` 当成**八进制转义**（chr(2)）而不是组引用——
    于是 `SKILL.md` 里「 项，零依赖」整段被一个不可见字符吃掉，
    而 `t_docs_no_drift` **只校验数字**，67 项全绿、没有任何人发现。
    **文档守卫只钉住了它关心的那几个数字，周围文字它可以被悄悄毁掉。**

    这类损坏肉眼极难发现（终端里它就是一段空白），只能靠字节级扫描。
    """
    import subprocess as _sp
    tracked = _sp.run(["git", "-C", str(ROOT), "ls-files"],
                      capture_output=True, text=True)
    if tracked.returncode != 0:      # 非 git 环境（如解压后的副本）不误判
        return
    bad = []
    for f in tracked.stdout.split():
        p = ROOT / f
        try:
            text = p.read_bytes().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for idx, ch in enumerate(text):
            if ord(ch) < 32 and ch not in "\n\t\r":
                bad.append(f"{f}:{text[:idx].count(chr(10)) + 1} {ch!r}")
                break
    assert not bad, f"以下文件含控制字符（多半是替换时转义写错）：{bad}"


def t_transcript_lossless():
    """逐字稿正文必须**严格等于字幕原文**——它是引语核验的真值来源，不许被改写。

    2026-10-07（#55）：`SPEAKER_RE` 把「X：」里的 X 一律当说话人，
    而中文「我想通一件事：听众其实…」这种句式极常见 → 逐字稿被写成
    `**那半分钟里我想通一件事**： 听众其实…`（插入了原文没有的 `**` 与空格）。
    后果链：卡片**逐字引用原话** → `verify-quotes` 判「❌ 未在语料中找到，
    这类来源不实必须修掉」→ 用户为"修好"只能把 `**` 抄进卡片，
    **等于教用户伪造引语**。实测真实英文 TED 字幕 315 条 cue 零误判，
    纯中文必中——又是一次「英文成立、中文崩」（同类见 #52）。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import transcript as T

    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        srt = wd / "zh.srt"
        # ① 中文从句冒号（会被旧实现误判）② 重复出现的真说话人标签
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\n那半分钟里我想通一件事：听众不介意你停顿。\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\n主持人：欢迎来到今天的分享。\n\n"
            "3\n00:00:09,000 --> 00:00:12,000\n主持人：我们先从第一个问题开始。\n\n"
            "4\n00:00:13,000 --> 00:00:16,000\n我的答案是：先从最小的一步做起。\n",
            encoding="utf-8")
        run(["transcript", str(srt), "--gap", "0"], cwd=wd)
        md = wd / "zh.transcript.md"
        t = md.read_text(encoding="utf-8")

        # ① 不许出现任何被工具加进去的 markdown 强调标记
        body_lines = [l for l in t.splitlines() if l.strip().startswith("[")]
        assert body_lines, "逐字稿没有生成任何段落"
        for l in body_lines:
            assert "**" not in l, f"逐字稿里出现了原文没有的 ** 强调标记：{l[:80]}"

        # ② 正文必须与字幕原文逐字一致（无损）
        bodies = [l.split("] ", 1)[1] for l in body_lines]
        src_texts = ["那半分钟里我想通一件事：听众不介意你停顿。",
                     "主持人：欢迎来到今天的分享。",
                     "主持人：我们先从第一个问题开始。",
                     "我的答案是：先从最小的一步做起。"]
        for b in bodies:
            assert b in src_texts, f"逐字稿正文被改写了：{b!r}"

        # ③ 单次出现的中文短语**永远不算说话人**（哪怕它长得像候选）。
        #    「那半分钟里我想通一件事」11 字 → 连候选都不是；
        #    「我的答案是」5 字 → 是候选，但只出现一次，不得被确认。
        who, _ = T.speaker_of("那半分钟里我想通一件事：听众不介意你停顿。")
        assert who == "", f"中文从句被当成说话人候选：{who!r}"
        assert "我的答案是" not in T.collect_speakers(
            [{"text": "我的答案是：先从最小的一步做起。"}]), \
            "只出现一次的短语被确认为说话人"
        meta = json.loads((wd / "zh.transcript.json").read_text(encoding="utf-8"))
        assert meta.get("speakers") == ["主持人"], \
            f"说话人元数据应只认重复出现的标签：{meta.get('speakers')}"

        # ④ 端到端：卡片逐字引用中文原话必须核得到（旧实现下会被判"来源不实"）
        rdoc = ROOT / "scripts"
        card = wd / "c.md"
        card.write_text(
            "---\nname: demo-card\ndescription: |\n  用于验证中文引语核验，"
            "描述写够长度以通过检查。\n---\n\n# C\n\n> 「那半分钟里我想通一件事："
            "听众不介意你停顿。」\n> —— [00:00:01.00]\n", encoding="utf-8")
        sys.path.insert(0, str(rdoc))
        from tdlib import evals
        r = evals.verify_quotes(card, md)
        assert r["verified"] >= 1, f"中文原话引用应核到，实际：{r}"


def t_anchor_chinese_not_vacuous():
    """`anchor` 必须能核中文引语，且**空集不得判 PASS**。

    2026-10-07（#56）：`anchor` 有三处英文假设——分词只认 `[a-z0-9']+`、
    引语抽取要求 `[A-Za-z]{2}`、只认 `"…"` 不认 `「…」`。
    结果：**专门为防「伪造引语」而建的命令，对中文卡片一条引语都抽不出来**，
    然后打印「引语 0 条」+「✅ 判定 PASS」——绿色的假安心。
    这是同一类假设的第三例（#52 overlap、#55 transcript）。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor

    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        src = wd / "zh.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\n我小时候特别怕在课上被点名。\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\n后来我发现把想说的话先写下来就会好很多。\n",
            encoding="utf-8")
        run(["transcript", str(src), "--gap", "0"], cwd=wd)
        md = wd / "zh.transcript.md"

        # ① 中文分词必须切得出东西（旧实现返回空表 → 全篇 TOO_SHORT）
        paras = anchor.split_paragraphs(md.read_text(encoding="utf-8"))
        assert anchor.norm_words(list(paras.values())[0]), "中文段落切不出任何词"
        assert anchor.norm_words("我小时候特别怕在课上被点名") , "中文引语切不出词"

        # ② 段号约定是 0 起（§0 = 第一段），挂对必须 ANCHOR_HIT
        good = wd / "good.md"
        good.write_text(
            "---\nname: g\ndescription: |\n  测试卡片，描述写够长度以通过检查。\n---\n\n"
            "> 「我小时候特别怕在课上被点名。」——§0\n", encoding="utf-8")
        run(["anchor", str(good), "--corpus", str(md)])
        rep = anchor.verify_file(good, anchor.load_corpora([md]))
        assert rep["anchored_checked"] == 1, f"挂对段号的引语应命中：{rep['tally']}"
        assert not rep["vacuous"], "有引语时不应判为空集"

        # ③ 挂错段号必须被抓到（真话但段号写成 §1，实际在 §0）
        bad = wd / "bad.md"
        bad.write_text(
            "---\nname: b\ndescription: |\n  测试卡片，描述写够长度以通过检查。\n---\n\n"
            "> 「后来我发现把想说的话先写下来就会好很多。」——§0\n", encoding="utf-8")
        p = run(["anchor", str(bad), "--corpus", str(md)], expect=None)
        assert p.returncode != 0, f"挂错段号必须判失败，实际退出码 {p.returncode}"
        rep2 = anchor.verify_file(bad, anchor.load_corpora([md]))
        assert rep2["tally"].get("SPAN_HIT") == 1, f"应判 SPAN_HIT：{rep2['tally']}"

        # ④ 空集假绿：有 §N 标注却一条引语都抽不出来 → 不许判 PASS
        empty = wd / "empty.md"
        empty.write_text(
            "---\nname: e\ndescription: |\n  测试卡片，描述写够长度以通过检查。\n---\n\n"
            "这里引用了 §0 的观点，但没有用引号把原文括起来，所以抽不出引语。\n",
            encoding="utf-8")
        rep3 = anchor.verify_file(empty, anchor.load_corpora([md]))
        assert rep3["vacuous"], f"有标注但 0 条引语，必须自报空集：{rep3}"
        p3 = run(["anchor", str(empty), "--corpus", str(md)], expect=None)
        assert p3.returncode != 0, "空集假绿必须判失败，不能打印 PASS"


def t_anchor_unanchored_not_fail():
    """复审 #1：无 §N 标注的引语 = **不可定位**，不得判失败（口径与 verify-quotes/lint 一致）。

    此前 anchor 的注释写「只检查带 §N 标注的引语」，实现却把无标注引语计入 miss 判 FAIL——
    官方样例卡因此 exit 1（3 条 R 段引语带 §，另 3 条正文/语言信号引语不带 §）。
    **注释与行为不符**是"声称≠实际"的典型；本条测试把二者钉在一起。

    同时守住反方向：口径放宽**不得**把"带 §N 但挂错段号"也放过——那才是本命令的第一性目的。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor

    card = ROOT / "examples/sample-bundle/skills/five-affairs-seven-questions/SKILL.md"
    src = ROOT / "examples/sample-bundle/sources/sunzi-ji.txt"
    rep = anchor.verify_file(card, anchor.load_corpora([src]))
    assert rep["verdict"] == "PASS", f"无标注引语不得判失败：{rep['tally']} {rep['failures']}"
    assert rep["anchored_checked"] >= 3, f"带 §N 的引语应照旧核验：{rep['tally']}"
    assert rep["unanchored"] >= 1, "无标注引语必须如实计数（不静默）"
    assert len(rep["unanchored_quotes"]) == rep["unanchored"], \
        f"无标注明细条数应与计数一致：{len(rep['unanchored_quotes'])} vs {rep['unanchored']}"
    # 对账必须平：seen = 各 verdict 之和（分区严丝合缝）
    rec = rep["reconciliation"]
    assert sum(v for kk, v in rec.items() if kk != "seen") == rec["seen"], \
        f"对账不平（分区漏项）：{rec}"
    # 反方向：带 §N 但挂错段号仍必须判 FAIL
    bad = Path(tempfile.mkdtemp()) / "bad.md"
    bad.write_text("> 「兵者，國之大事，死生之地，存亡之道，不可不察也。」——§2\n",
                   encoding="utf-8")
    assert anchor.verify_file(bad, anchor.load_corpora([src]))["verdict"] == "FAIL", \
        "带 §N 但挂错段号必须仍判 FAIL（放宽口径不得放过真问题）"
    # CLI 端到端：样例卡 exit 0
    run(["anchor", str(card), "--corpus", str(src)], expect=0)


def t_sample_report_consistent():
    """被取代的历史报告不得与权威 FIDELITY.json 在同一字段上互相矛盾（复审 5）。

    实测：`eval/fidelity-report.md` 的 frontmatter 写 `cross_grader_gap: 8`（指向**第二**轮），
    正文却写「cross_grader_gap 为空」（**第一**轮确为单评分）——**同一字段在同一文件里两种说法**。
    历史文件要保留历史真相（字段不回填新数字），指针放正文。
    """
    sb = ROOT / "examples/sample-bundle"
    hist = sb / "eval" / "fidelity-report.md"
    auth = sb / "skills" / "five-affairs-seven-questions" / "FIDELITY.json"
    assert hist.exists() and auth.exists(), "样例 bundle 的历史报告或权威报告缺失"

    text = hist.read_text(encoding="utf-8")
    m = re.search(r"(?m)^cross_grader_gap:\s*(.+?)\s*$", text)
    assert m, "历史报告应保留 cross_grader_gap 字段（说明性的）"
    val = m.group(1)
    assert not re.match(r"^\d", val), (
        f"历史报告的 cross_grader_gap 不得回填分数：{val!r}"
        "——第一轮是单评分，8 分属于第二轮交叉复核，应放在正文指针里")
    assert "已被" in text or "superseded" in text.lower(), \
        "历史报告必须显式标注已被取代，否则读者会把它当现状"
    # 数字的唯一真源是权威报告
    auth_d = json.loads(auth.read_text(encoding="utf-8"))
    assert auth_d.get("cross_grader_gap") == 8.0, auth_d
    assert len(auth_d.get("graders") or []) >= 2, auth_d


def t_anchor_cjk_short_quotes():
    """#61 + 复审 5 建议：中文短引语必须被认出、可定位，且**带 §N 的短候选可核验**。

    旧实现两道闸门都卡在英文尺度上：抽取正则 `{12,600}` 的下限、`_is_quote` 的 `len(q) < 12`。
    于是「天行健，君子以自強不息」(11 字)、「不可為典要，唯變所適」(10 字)、
    「窮理盡性以至於命」(8 字) 这些最经典的引语**从未进入核验**，还被计入 noise 静默消失。

    ⚠️ 复审 5（测试环境耦合）：本测试此前跑的是作者工作区里的真实卡片（`../guoxue-skills` +
    `../yijing-run/corpus`），只在两个目录都存在时才断言——**本机缺语料就假红，CI 两个都没有就静默跳过**
    （绿是"跳过"而非"跑过"）。现已改为 **fixture 驱动**（`tests/fixtures/cjk-short-quotes/`），
    与任何外部工作区无关。

    非对称规则（复审 5 建议）也要守住：短引语**命中计入核验数**，**失配只报警不判失败**
    （≤7 字短语在多引用行上归属含糊，硬判会假阳性）；而 ≥8 字的引语失配照旧硬判 FAIL。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor as A

    fx = ROOT / "tests" / "fixtures" / "cjk-short-quotes"
    assert fx.exists(), f"fixture 缺失：{fx}"
    corpora = A.load_corpora([fx / "corpus.md"])
    rep = A.verify_file(fx / "card.md", corpora)

    # ① 短引语必须被认出来（旧实现在这里只认出 3 条长引语）
    assert rep["quotes_seen"] == 6, f"引语数不对：{rep['quotes_seen']}（期望 6）"
    # ② 「厚德載物」（4 汉字）逐字见于语料且挂了 §2 → 计入核验并命中
    assert rep["anchored_checked"] == 4, f"锚定命中数不对：{rep['anchored_checked']}（期望 4）"
    sq = rep["short_quotes"]
    assert sq["verified"] == 1, f"短引语命中应计入核验：{sq}"
    # ③ 短引语挂错段号（§1 而实际 §2）：只报警，**不进 failures、不判 FAIL**
    assert len(sq["misplaced"]) == 1, f"短引语失配应单列报警：{sq}"
    assert sq["misplaced"][0]["claimed_at"] == 1 and sq["misplaced"][0]["found_at"] == 2, sq
    assert rep["failures"] == [], f"短引语失配不得进硬失败：{rep['failures']}"
    assert rep["verdict"] == "PASS", f"短引语失配不应判 FAIL：{rep['tally']}"

    # ④ 抽取层对账必须平：候选 = 认出 + 噪声 + 中文太短跳过
    er = rep["extraction_reconciliation"]
    assert er["balanced"], f"抽取层对账不平：{er}"
    # ⑤ 判定层对账也必须平
    rec = rep["reconciliation"]
    assert sum(v for kk, v in rec.items() if kk != "seen") == rec["seen"], f"对账不平：{rec}"

    # ⑥ 短术语（语料里没有）仍不得被当引语
    assert "缺啥补啥" not in [r["quote"] for r in []] + \
        [s["quote"] for s in rep["short_but_in_corpus"]], "短术语不该被算作引语"
    assert rep["skipped_cjk_short"] == 1, f"短术语应记入 skipped：{rep['skipped_cjk_short']}"

    # ⑦ 反方向：≥8 汉字的引语挂错段号，仍必须硬判 FAIL（放宽短引语不得连坐长引语）
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.md"
        bad.write_text("> 「天行健，君子以自強不息」——§1\n", encoding="utf-8")
        r2 = A.verify_file(bad, corpora)
        assert r2["verdict"] == "FAIL", f"长引语挂错段号必须 FAIL：{r2['tally']}"
        assert r2["failures"], "FAIL 但没给失配明细"

    # ⑧ CLI 端到端：fixture 卡 exit 0（短引语失配不阻断）
    run(["anchor", str(fx / "card.md"), "--corpus", str(fx / "corpus.md")], expect=0)


def t_anchor_verse_locators():
    """#71：anchor 必须原生支持《論語》式「篇-章号」（一之三）细粒度定位。

    正例（fixture card.md）：三种卡片侧形状都要锚定成功——
      (a) 块引用行首 `> 一之三 「…」`；
      (b) 引语在前、出处（篇-章号）隔空行在下一行 `> —— 四之十六`；
      (c) 同上承接（含同行 `—— 同上`）。
    且短引语（「巧言令色，鮮矣仁。」7 汉字）一旦显式以篇-章号定位，必须进入核验并命中——
    不能用通用短候选阈值把它静默丢弃（那等于"标了段号却没核验"）。

    反例（fixture card-bad.md）：声明「一之三」却引「一之四」之文 → SPAN_HIT → FAIL，
    且必须报出「声明 vs 实际」两个标签（一之三 / 一之四），不能假绿。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor as A

    fx = ROOT / "tests" / "fixtures" / "lunyu-verse"
    assert fx.exists(), f"fixture 缺失：{fx}"
    corpora = A.load_corpora([fx / "corpus.md"])

    # —— 正例 ——
    rep = A.verify_file(fx / "card.md", corpora)
    assert rep["verdict"] == "PASS", f"篇-章号正例应判 PASS：{rep['tally']} {rep['failures']}"
    assert rep["anchored_checked"] >= 3, \
        f"篇-章号三种形状都应锚定（≥3）：{rep['tally']}"
    # (a)(b)(c) 各自命中：5 条 locatable 引语全 ANCHOR_HIT
    assert rep["tally"].get("ANCHOR_HIT", 0) >= 3, f"ANCHOR_HIT 数不够：{rep['tally']}"
    # 对账必须平
    rec = rep["reconciliation"]
    assert sum(v for kk, v in rec.items() if kk != "seen") == rec["seen"], f"对账不平：{rec}"
    er = rep["extraction_reconciliation"]
    assert er["balanced"], f"抽取层对账不平：{er}"
    # 设计护栏：正文提到篇-章号但无引号 → 不得计入 citations / 不得判失败
    assert rep["unresolved_sources"] == [], f"反误报：正文篇-章号不得当来源缺失：{rep['unresolved_sources']}"

    # —— 反例：挂错篇-章号必须 FAIL ——
    bad = A.verify_file(fx / "card-bad.md", corpora)
    assert bad["verdict"] == "FAIL", f"篇-章号挂错必须判 FAIL：{bad['tally']}"
    assert bad["failures"], "FAIL 但没给失配明细"
    f0 = bad["failures"][0]
    assert f0["claimed_label"] == "一之三" and f0["found_label"] == "一之四", \
        f"必须报出声明/实际标签：{f0}"
    assert f0["verdict"] == "SPAN_HIT", f"应判 SPAN_HIT（引语在别的段）：{f0}"

    # CLI 端到端：正例 exit 0、反例 die（exit≠0）
    run(["anchor", str(fx / "card.md"), "--corpus", str(fx / "corpus.md")], expect=0)
    run(["anchor", str(fx / "card-bad.md"), "--corpus", str(fx / "corpus.md")], expect=1)


def t_anchor_zero_anchor_is_na():
    """#71：三态收口——卡片有引语但**零条可核验**（无任何 §N/段号/篇-章号/时间戳），
    必须判 UNVERIFIED 而非 PASS（软 PASS 假绿），且 CLI 必须 die（exit≠0）。

    这是"声称≠实际"的钉子：旧实现只要"没核验出错误"就印 ✅，等于默认所有引语都没标段号。
    UNVERIFIED ≠ PASS——它明确说"这批引语我一件都没法核对"，把决定权交回人。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import anchor as A

    fx = ROOT / "tests" / "fixtures" / "lunyu-verse"
    corpora = A.load_corpora([fx / "corpus.md"])
    with tempfile.TemporaryDirectory() as d:
        card = Path(d) / "na.md"
        # 两处引语都**没标段号**——有引用但零可核验
        card.write_text(
            "# 仅有无标注引语\n\n"
            "> 「學而時習之，不亦說乎？」此句见于論語，但未标篇-章号。\n\n"
            "> 「有朋自遠方來，不亦樂乎？」同样无标注。\n",
            encoding="utf-8")
        rep = A.verify_file(card, corpora)
        assert rep["quotes_seen"] >= 2, f"引语应被抽出：{rep['quotes_seen']}"
        assert rep["checked"] == 0, \
            f"零条可核验（无任何定位标记）：{rep['checked']}"
        assert rep["verdict"] == "UNVERIFIED", \
            f"零核验必须判 UNVERIFIED 而非 PASS：{rep['verdict']} {rep['tally']}"
        # 反方向：一旦有一条标了段号并核验通过，立刻回到 PASS（不连坐）
        ok = Path(d) / "ok.md"
        ok.write_text(
            "# 混编：一条无标注 + 一条篇-章号标注\n\n"
            "> 「學而時習之，不亦說乎？」无标注。\n\n"
            "> 一之三 「巧言令色，鮮矣仁。」\n",
            encoding="utf-8")
        rep2 = A.verify_file(ok, corpora)
        assert rep2["verdict"] == "PASS", \
            f"有一条可核验通过即 PASS（不连坐无标注）：{rep2['tally']}"
    # CLI 端到端：UNVERIFIED 必须 die（exit≠0）
    with tempfile.TemporaryDirectory() as d:
        card = Path(d) / "na.md"
        card.write_text(
            "> 「學而時習之，不亦說乎？」无标注。\n", encoding="utf-8")
        run(["anchor", str(card), "--corpus", str(fx / "corpus.md")], expect=1)


def t_lunyu_card_no_overclaim():
    """#72：論語卡（及文档）不得做出无法佐证的「已核验」声称。

    进度研判（2026-10-10）点名：論語卡 A1 段写「评分 Agent 核查确认：叙事出现次数为 0」，
    但实际没有评分 Agent 做过这件事；SOURCES/scale-evidence 写「引语逐字锚定」暗示自动段级锚定，
    而当时 anchor 根本不认篇-章号。这是本项目最高频的「声称≠实际」，必须钉死：
    ① 卡片不得再出现「评分 Agent 核查确认」这个无法佐证的措辞；
    ② 必须改为诚实的「建卡时…全库检索确认」；
    ③ 文档不得用「引语逐字锚定」这种过度声称（段级锚定改由 `td.py anchor` 真实跑出并写明命令）。
    """
    skill = (ROOT / "examples/open-bundle/skills/lunyu-conduct/SKILL.md") \
        .read_text(encoding="utf-8")
    assert "评分 Agent 核查确认" not in skill, \
        "論語卡 A1 仍含无法佐证的「评分 Agent 核查确认」——应改为「建卡时…全库检索确认」"
    assert "建卡时对 anchored 语料全库检索确认" in skill, \
        "論語卡 A1 应改为诚实的「建卡时…全库检索确认」"
    sources = (ROOT / "examples/open-bundle/skills/lunyu-conduct/SOURCES.md") \
        .read_text(encoding="utf-8")
    assert "引语逐字锚定" not in sources, \
        "SOURCES 不得用「引语逐字锚定」过度声称（段级锚定见 `td.py anchor` 记录）"
    scale = (ROOT / "docs" / "scale-evidence-open-material-2026-10-10.md") \
        .read_text(encoding="utf-8")
    assert "引语逐字锚定" not in scale, \
        "scale-evidence 不得用「引语逐字锚定」过度声称"


def t_no_external_fixture_deps():
    """P0-1c：回归测试**不得静默依赖作者工作区**（`ROOT.parent` 之外的路径）。

    #65 的教训：`if notxxx.exists(): return` 让测试在缺素材时"跳过"，
    跳过的数量还会随机器而变——本机有 sibling 仓库时跑、CI 里整体跳过，
    **绿是"跳过"而非"跑过"**。本条把这条纪律变成可机校验的：

    ① **仓库外路径只能经 `external_ws()` 这一个入口取得**，且该入口必须同时
       检查 `RULAI_WORKSPACE=1` 与路径存在——裸的 `ROOT.parent` 只允许出现在
       `external_ws()` 函数体内（多处出现 = 有人绕过守卫）；
    ② 白名单非空，且每条声明都在代码里真的被引用
       （防止「登记了但没这依赖」或反之）；
    ③ **自足性**：把仓库复制到临时目录（**没有任何 sibling 仓库**）后，
       关键测试仍须全绿——这才是「新机器 clone 后全绿」的可判定义。
    """
    src = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    fn_start = src.index("def external_ws(")
    fn_end = src.index("SKIPPED: list", fn_start)
    fn_start_line = src[:fn_start].count("\n") + 1
    fn_end_line = src[:fn_end].count("\n") + 1

    # ① ROOT.parent 只允许出现在 external_ws() 函数体内。
    # 用 AST 而不是文本扫描：**注释与文档字符串里提到 ROOT.parent 不算引用**
    # （否则这条守卫会被自己的说明文字触发——#64 的同一个坑）。
    tree = ast.parse(src)
    stray = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "parent" \
                and isinstance(node.value, ast.Name) and node.value.id == "ROOT":
            if not (fn_start_line <= node.lineno <= fn_end_line):
                stray.append(node.lineno)
    assert not stray, \
        f"仓库外路径只能经 external_ws() 取得；这些行绕过了守卫：{sorted(stray)}"
    fn = src[fn_start:fn_end]
    assert "RULAI_WORKSPACE" in fn, \
        "external_ws() 必须检查 RULAI_WORKSPACE —— 否则它不再是守卫"
    assert ".exists()" in fn, \
        "external_ws() 必须检查路径存在 —— 否则缺素材时硬失败而非如实报未运行"

    # ② 白名单：每条登记都必须在代码里真的被引用
    assert EXTERNAL_DEPS_WHITELIST, "白名单为空——真有外部依赖时应登记，不该悄悄删掉"
    code = src[fn_end:]
    unused = [k for k in EXTERNAL_DEPS_WHITELIST
              if not any(seg in code for seg in k.split("/")[-2:] if len(seg) > 6)]
    assert not unused, f"白名单登记了但代码里找不到对应引用：{unused}"

    # ③ 自足性：干净副本（无任何 sibling 仓库）里关键测试仍须全绿
    with tempfile.TemporaryDirectory() as d:
        clean = Path(d) / "clean"
        shutil.copytree(ROOT, clean, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc"))
        assert (clean / "scripts" / "td.py").exists(), "复制后 td.py 缺失"
        env = dict(os.environ)
        env.pop("RULAI_WORKSPACE", None)
        proc = subprocess.run(
            [sys.executable, str(clean / "tests" / "e2e.py"), "--only",
             "t_anchor_cjk_short_quotes,t_validate_bundle,t_lint_quotes"],
            capture_output=True, text=True, env=env)
        assert proc.returncode == 0, \
            f"干净副本里fixture 测试未全绿：\n{proc.stdout[-1500:]}"
        assert "需要作者工作区" not in proc.stdout, \
            f"干净副本仍在靠外部素材：\n{proc.stdout[-800:]}"


def t_verify_quotes_misplaced_vs_fabricated():
    """「引语挂错位置」与「引语是编造的」必须分开报，且都判失败。

    2026-10-07（#57）：旧实现把两者一律报成「未在语料中找到」。
    而引语明明在语料里、只是位置标错时，用户看到那句话会去**删掉一条真引语**——
    核验器反而在破坏卡片。这两件事对用户的意义完全相反：
    一个要「改引用位置」，一个要「删掉并追查怎么编出来的」。

    ⚠️ 拆分时最容易犯的错：把 misplaced 排除出 unverified 却忘了改 verdict，
    整批挂错位置的引语会变成 PASS。**本条测试就是这个假绿的守卫。**
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals

    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        srt = wd / "zh.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\n第一句讲的是完全独立的一个话题内容。\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\n第二句换成了另一个毫不相干的说法。\n",
            encoding="utf-8")
        run(["transcript", str(srt), "--gap", "0"], cwd=wd)
        md = wd / "zh.transcript.md"
        txt = md.read_text(encoding="utf-8")
        # 取第二段的正文，把它标到第一段的时间戳上（= 位置不符）
        second = [l.split("] ", 1)[1] for l in txt.splitlines()
                  if l.strip().startswith("[")][1]
        first_ts = [l.split("] ", 1)[0].strip("[") for l in txt.splitlines()
                    if l.strip().startswith("[")][0]

        card = wd / "c.md"
        card.write_text(
            "---\nname: c\ndescription: |\n  测试卡片，描述写够长度以通过检查。\n---\n\n"
            f"> 「{second}」—— [{first_ts}]\n\n"
            "> 「这句在语料里完全不存在，用来模拟凭空编造的引语内容。」\n"
            f"> —— [{'00:00:05.00'}]\n", encoding="utf-8")
        r = evals.verify_quotes(card, md)

        assert len(r["misplaced"]) == 1, \
            f"挂错位置的引语应归入 misplaced：{r.get('misplaced')} / {r['unverified']}"
        assert len(r["unverified"]) == 1, \
            f"编造的引语应归入 unverified：{r['unverified']}"
        assert r["verdict"] == "fail", \
            "misplaced 与 unverified 都必须判失败——分开只是提示更准，不是放宽判定"

        p = run(["verify-quotes", str(card), str(md)], expect=None)
        assert p.returncode != 0, "存在两类问题时必须非零退出"
        assert "位置不符" in p.stdout, f"输出必须区分「位置不符」：{p.stdout[-600:]}"
        assert "疑似编造" in p.stdout, f"输出必须标出「疑似编造」：{p.stdout[-600:]}"


def t_chinese_unit_count_and_honest_capability():
    """中文必须按「字」计数；算不出结论时不许给结论；查不到的能力必须明说。

    2026-10-07 两条同类缺陷一起守：
    · #58 `audit-coverage` 用 `len(norm.split())` 判「是否实质段落」——中文整段只算
      1 个词 → **每个中文段落都被当衔接语跳过**，报告写「语料段落 3（实质 0）」。
      老实读的人以为卡片很差；**扫一眼的人把「未覆盖 0」读成"全都覆盖了"**。
    · #59 `research merge` 的 `conflicts` 只看得见「措辞高度重叠」的条目对，
      而真正的对立主张相似度实测 0.000~0.077，永远进不了那个分支，
      摘要却打印「冲突 0 处」——**在那件工具自称要干的事上假绿**。
      确定性脚本无法判定语义矛盾 → 改为在输出里明说这个能力不存在。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals, research as R

    # ① 中文词数：按字计，不再靠空白切词（「决策要先把前提固定下来」= 11 个字）
    assert evals._unit_count("决策要先把前提固定下来") == 11, \
        f"中文应按字计数：{evals._unit_count('决策要先把前提固定下来')}"
    assert evals._unit_count("alpha beta gamma") == 3

    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        srt = wd / "zh.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:06,000\n"
            "第一条讲的是决策要先把前提固定下来，前提一变结论就跟着变，所以要反复确认前提。\n\n"
            "2\n00:00:07,000 --> 00:00:12,000\n"
            "第二条讲的是遇到分歧时先找共同点，共同点找不到就缩小范围继续找，直到能对上。\n\n"
            "3\n00:00:13,000 --> 00:00:18,000\n"
            "第三条讲的是记录的重要性，把每次判断的依据写下来，事后才能复盘对错在哪里。\n",
            encoding="utf-8")
        run(["transcript", str(srt), "--gap", "0"], cwd=wd)
        md = wd / "zh.transcript.md"
        card = wd / "c.md"
        card.write_text(
            "---\nname: c\ndescription: |\n  覆盖率探针卡片，只覆盖前两条。描述长度写够。\n---\n\n"
            "决策要先把前提固定下来，前提一变结论就跟着变，所以要反复确认前提。\n\n"
            "遇到分歧时先找共同点，共同点找不到就缩小范围继续找，直到能对上。\n",
            encoding="utf-8")
        res = evals.audit_coverage(card, md)
        assert res["substantive"] == 3, \
            f"中文段落不该被当成衔接语跳过，实质应为 3：{res['substantive']}"
        assert not res["vacuous"], "有实质段落时不应判空集"
        assert res["uncovered"] == 1, \
            f"第 3 段没被覆盖，应报 1 段未覆盖，实际 {res['uncovered']}"
        assert res["uncovered_paragraphs"][0]["ts"].startswith("00:00:13"), \
            f"未覆盖的应是第 3 段：{res['uncovered_paragraphs'][0]['ts']}"

        # ② 空集守卫：一个段落都算不出来时，不许给覆盖结论
        tiny = wd / "tiny.srt"
        tiny.write_text("1\n00:00:01,000 --> 00:00:02,000\n嗯。\n", encoding="utf-8")
        run(["transcript", str(tiny), "--gap", "0"], cwd=wd)
        res2 = evals.audit_coverage(card, wd / "tiny.transcript.md")
        assert res2["vacuous"], f"全被跳过时必须自报空集：{res2['paragraphs_total']}/{res2['substantive']}"

    # ③ 对立主张：必须显式声明「查不到」，且不提供会误导的计数字段
    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        (wd / "a.md").write_text(
            "---\nlane: 01\nstatus: ok\none_hand_weight: 0.9\n---\n\n"
            "- 决策必须先把前提固定下来，前提一变结论就跟着变。出处：自传第 3 章 [一手]\n",
            encoding="utf-8")
        (wd / "b.md").write_text(
            "---\nlane: 02\nstatus: ok\none_hand_weight: 0.9\n---\n\n"
            "- 决策不需要先固定前提，先做起来再随时调整。出处：2024 访谈 [一手]\n",
            encoding="utf-8")
        out = wd / "merged.md"
        run(["research", "merge", str(wd / "a.md"), str(wd / "b.md"), "--out", str(out)])
        txt = out.read_text(encoding="utf-8")
        assert "本工具查不到对立主张" in txt, \
            "必须显式声明「对立主张查不到」，否则「冲突 0 处」会被读成「没矛盾」"
        assert "必须由 Agent/人工逐条对照" in txt, "必须给出必须人工做的下一步"
        assert "对立候选" not in txt, "失效的启发式不该留在输出里（它会读成「0 处=没问题」）"


def t_verify_quotes_lang_filter_not_silent():
    """语言过滤可以「不核验」，但**绝不能静默**。

    2026-10-07（#60）：`_keep()` 对「语料判为英文 + 作者行文行」的中文候选直接
    `continue` 扔掉 → `cands` 变空 → 被下面误归类成「表格行=纯定位锚点，不承载引语」。
    实测同一位置放一条编造的**英文**引语会判 FAIL，放**中文**则打印
    「✅ 全部引语在语料中核到」通过——**在「防伪造引语」这件事上假绿**，
    而这正是本命令存在的理由。

    修法不是硬把它判失败（中文作者行文在英文语料里是常态，#35 已证明硬判会让
    工具不可用），而是**记账 + 显式打出来 + 不再给一句干净的 ✅**。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from tdlib import evals

    with tempfile.TemporaryDirectory() as d:
        wd = Path(d)
        # 英文为主（CJK < 20%）的语料 → 触发语言过滤
        srt = wd / "mix.srt"
        srt.write_text(
            "1\n00:00:01,000 --> 00:00:06,000\n"
            "The first principle is that you must fix your premises before you reason.\n\n"
            "2\n00:00:07,000 --> 00:00:12,000\n"
            "When you argue, find the common ground first, then narrow the scope step by step.\n\n"
            "3\n00:00:13,000 --> 00:00:18,000\n"
            "Keeping a written record of every judgement lets you review where you went wrong.\n",
            encoding="utf-8")
        run(["transcript", str(srt), "--gap", "0"], cwd=wd)
        md = wd / "mix.transcript.md"
        txt = md.read_text(encoding="utf-8")
        cjk = len(re.findall(r"[\u4e00-\u9fff]", txt))
        assert cjk / len(txt) < 0.20, "夹具应是英文为主的语料"

        # 表格行里放一条语料中不存在的**中文**引语
        card = wd / "zh-row.md"
        card.write_text(
            "---\nname: c\ndescription: |\n  探针卡片，描述写够长度以通过检查。\n---\n\n"
            "| 主张 | 逐字引语 | 出处 |\n|---|---|---|\n"
            "| 讲者主张先固定前提 | 「我在早上总是先跑步五公里再开始工作」 | [00:00:01.00] |\n",
            encoding="utf-8")
        r = evals.verify_quotes(card, md)
        assert len(r["lang_skipped"]) == 1, \
            f"被语言过滤的候选必须单独记账，不能混进 locator_only：{r.get('lang_skipped')}"
        p = run(["verify-quotes", str(card), str(md)])
        assert "未核验" in p.stdout, f"必须显式打出「未核验」：{p.stdout[-500:]}"
        assert "✅ 全部引语在语料中核到" not in p.stdout, \
            "有未核验候选时不许打印一句干净的 ✅（那正是假绿）"
        assert "引用计数无法加总还原" not in p.stdout, \
            "lang_skipped 必须进对账表，否则计数守卫会红"

        # 对照：同位置放**英文**编造引语，必须照旧判失败（行为不能被放松）
        card_en = wd / "en-row.md"
        card_en.write_text(
            "---\nname: e\ndescription: |\n  对照卡片，描述写够长度以通过检查。\n---\n\n"
            "| 主张 | 逐字引语 | 出处 |\n|---|---|---|\n"
            "| 讲者主张先固定前提 | \"I run five kilometres every single morning\" "
            "| [00:00:01.00] |\n", encoding="utf-8")
        pe = run(["verify-quotes", str(card_en), str(md)], expect=None)
        assert pe.returncode != 0, "英文编造引语必须仍然判失败"
        assert not evals.verify_quotes(card_en, md)["lang_skipped"], \
            "英文候选不该走语言过滤"


def t_errors_are_human():
    assert "路径不存在" in run(["validate", "/nonexistent-xyz"], expect=1).stdout
    assert "FIDELITY 报告不存在" in run(["gate", "/nonexistent-xyz.md"], expect=1).stdout
    assert "字幕文件不存在" in run(["transcript", "/nonexistent-xyz.srt"], expect=1).stdout
    assert "源文件不存在" in run(["chunk", "/nonexistent-xyz.md"], expect=1).stdout
    assert "未找到 index" in run(["index", "/tmp/definitely-not-here"], expect=1).stdout


def t_no_unregistered_tests():
    """任何 `def t_*` 都必须出现在 main() 的运行清单里。

    2026-10-07 实测（#45）：`t_overlap_detector` 定义了却忘了登记进清单，
    于是「素材零重叠」这条要求**从来没被执行过**——
    **写了不跑，比不写更坏**：它给读README 的人虚假的安全感。
    文档守卫 `t_docs_no_drift` 数的是「定义数」，运行器数的是「清单数」，
    两者不等时文档数字会漂移，但没人知道少跑了一项。
    """
    src = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    defined = set(re.findall(r"^def (t_[a-z0-9_]+)\(", src, re.M))
    main_src = src[src.index("def main() -> int:"):]
    used = set(re.findall(r'\("[^"]+",\s*(t_[a-z0-9_]+)\)', main_src))
    assert defined == used, (
        f"定义了但没进运行清单：{sorted(defined - used)}；"
        f"清单里有但没定义：{sorted(used - defined)}")


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiktoken", action="store_true")
    ap.add_argument("--only", default="",
                    help="只跑给定函数名（逗号分隔），供 CI 分层使用；逻辑只在测试里写一份")
    args = ap.parse_args()

    if args.tiktoken:
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            print("⚠️  未安装 tiktoken，跳过该路径")
            args.tiktoken = False

    print(f"rulai-distill 端到端回归（解释器：{sys.executable}）\n")
    tests = [
        ("doctor 环境自检与能力矩阵", t_doctor),
        ("init 生成 bundle + 六路调研骨架", t_init),
        ("chunk 结构分块/缓存/索引", t_chunk),
        ("chunk 超长段落二次切分", t_chunk_oversize),
        ("transcript SRT 去重与时间戳", t_transcript),
        ("research 六路合并去重与冲突标记", t_research),
        ("validate 合格 bundle 零错误", t_validate_bundle),
        ("死链检查：正常相对链接不误报（#63）", t_dead_link_relative_within_root),
        ("仓库自身 validate + 文档结构自检（#64）", t_self_validate_clean_and_doc_structure),
        ("validate 拦截步骤禁令/完成标准/失败模式", t_validate_catches),
        ("output-eval 产物体检", t_output_eval),
        ("gate 门槛与自测降级", t_gate),
        ("gate 默认要求交叉复核记录（复审 P0）", t_gate_requires_cross_review),
        ("eval-kit 独立质检闭环（复审 P0）", t_eval_kit),
        ("lint-quotes 引语体检（复审 P1）", t_lint_quotes),
        ("lint-quotes 技术 token 与节引标注（#62）", t_lint_quotes_technical_and_sectional),
        ("eval-kit 加固·失败产物/同名评分者（复审 G1）", t_g1_evalkit_hardening),
        ("validate 豁免根级辅助文档（复审）", t_validate_exempts_aux_docs),
        ("CI 样例 gate 步骤（复审 G2）", t_ci_artifact_gate),
        ("validate 扁平布局 skills/*.md 恒为卡片（复审 #4）", t_validate_flat_layout),
        ("registry 结构化 fidelity + 报告随包（复审 #2/#3）", t_registry_structured_fidelity_and_reports),
        ("with-reports 未找到报告不得宣称已发布（复审 #2）", t_compile_with_reports_honest),
        ("compile 能找到卡片同级 FIDELITY.json（复审 #2）", t_compile_finds_card_json_report),
        ("strategy single/pack 决策", t_strategy),
        ("compile 原子发布 + 手改检测 + 回滚", t_compile_and_publish),
        ("compile single 模式", t_compile_single_mode),
        ("compile 拒绝低等级 + --force 留痕", t_compile_blocks_low_grade),
        ("trigger build/record/score 全链路", t_trigger),
        ("count token 计量", t_count),
        ("prompt 单文件编译", t_prompt),
        ("diff/impact/repair/patch/update", t_diff_impact_repair_patch_update),
        ("vendored 上游可运行（chunk 实跑）", t_upstream_vendor),
        ("缓存键含实现版本与契约版本", t_cache_versioning),
        ("每次运行独立留痕（runs/）", t_run_traceability),
        ("WriterLock 并发写保护", t_writer_lock),
        ("fetch-subtitle 默认 dry-run 不联网", t_fetch_subtitle_dryrun),
        ("分词器双向回归（CJK bigram / 英文整词）", t_bigram_tokenizer),
        ("lexindex 中英文都能检索", t_lexindex_both_scripts),
        ("lexindex FTS5 + 中文 bigram + 邻接块", t_lexindex),
        ("lexindex 单字 CJK 查询不崩（P0-2）", t_lexindex_single_char_cjk),
        ("FIDELITY 解析严格化（漏维度+总分不一致）", t_fidelity_parse_strictness),
        ("trigger split/prepare + P/R/F1 + 兄弟混淆率", t_trigger_split_metrics),
        ("判分器归一化字符串 none/null", t_answer_normalization),
        ("C3 契约清单完整可查", t_contract_list),
        ("C3 chunk 产物合 source-document", t_contract_source_document),
        ("C3 registry 合 registry-entry-v2", t_contract_registry_entry),
        ("C3 调研产出 source-manifest", t_contract_source_manifest),
        ("C3 diff 产出 change-set", t_contract_change_set),
        ("C3 eval-suite + failure-case 契约", t_contract_eval_suite_and_failure),
        ("C1 字幕获取能力存在且默认 dry-run", t_fetch_subtitle_exists),
        ("C2 上游能力逐项有归属", t_upstream_coverage),
        ("C4 约束表无静默缺口", t_contract_ledger_no_silent_gap),
        ("C4 缺陷台账每条有回归测试", t_defect_regression_ledger),
        ("缺陷3/4/5 引语核验方向与编号", t_verify_quotes_direction),
        ("缺陷6 调研车道覆盖审计", t_research_lane_coverage),
        ("缺陷7/8 兼容上游产物格式", t_validate_upstream_format),
        ("缺陷9 人物卡不要求 E 段", t_persona_no_e_section),
        ("引语核验支持时间戳定位（视频卡片）", t_verify_quotes_timestamp),
        ("真实 TED 字幕回归（段落优先+破折号归一）", t_verify_quotes_real_transcript),
        ("引语核验计数对账与多形态（#31~#39）", t_verify_quotes_accounting),
        ("英文字幕去重精度（n-gram）", t_transcript_dedupe_precision),
        ("引语核验·归属声明块不误判", t_verify_quotes_attribution_block),
        ("引语核验·书类引用块（出处信号+空集守卫）", t_verify_quotes_book_block),
        ("引语核验·头部计数并入书类引用块（复审#3）", t_verify_quotes_display_merges_book_block),
        ("validate 豁免 references/ 下资料（复审#4）", t_validate_exempts_references),
        ("publish registry source_url 指向本项目（复审#4）", t_publish_source_url_rulai),
        ("无限定的素材缺席全称判断", t_no_unqualified_absence_claims),
        ("C7 评分期冻结完整性", t_eval_freeze_integrity),
        ("C8 盲测材料匿名性", t_style_decoy_anonymity),
        ("C9 披露小节完整性", t_disclosure_completeness),
        ("覆盖审计可用且阈值敏感", t_audit_coverage_runs),
        ("披露清单覆盖全部未覆盖段落", t_disclosure_covers_uncovered),
        ("三类素材真实产物齐备", t_real_sample_artifacts),
        ("CLI 子命令与库函数无丢失", t_cli_handlers_intact),
        ("nuwa 第三铁律·交叉复核门禁（#43）", t_cross_review_gate),
        ("CI 四个 workflow 齐备", t_ci_present),
        ("C6 vendored 上游完整性（sha256 基线）", t_vendor_integrity),
        ("C11 已安装副本与项目一致（#44）", t_installed_copy_in_sync),
        ("C11 跳过生成物/侧车目录（复审#2）", t_c11_skips_generated_artifacts),
        ("引语段号锚定（#46）", t_anchor_verifier),
        ("anchor 无 §N 引语不计失败（复审 #1）", t_anchor_unanchored_not_fail),
        ("anchor 中文短引语不被丢（#61）", t_anchor_cjk_short_quotes),
        ("anchor 支持篇-章号定位（#71 正例/反例）", t_anchor_verse_locators),
        ("anchor 零核验收口为 UNVERIFIED（#71）", t_anchor_zero_anchor_is_na),
        ("論語卡无过度声称（#72）", t_lunyu_card_no_overclaim),
        ("回归不得依赖作者工作区（P0-1/#65）", t_no_external_fixture_deps),
        ("token 节省实测不产假数字（P0-3）", t_token_savings_benchmark),
        ("corpus-anchor 按结构切段（#70）", t_corpus_anchor_splits_by_structure),
        ("对外声称有据且数字不腐烂（P0-4）", t_claims_have_evidence),
        ("shell 脚本无静默出错写法", t_shell_scripts_safe),
        ("样例历史报告与权威报告不矛盾（复审 5）", t_sample_report_consistent),
        ("anchor 支持书类【第N段】语料（复审#1）", t_anchor_book_corpus),
        ("corpus-anchor 书类语料规整（复审#1）", t_corpus_anchor_command),
        ("素材零重叠检测（8-gram 包含率）", t_overlap_detector),
        ("测试不许漏注册（#45）", t_no_unregistered_tests),
        ("GUIDE 黄金路径端到端（#51）", t_guide_walkthrough),
        ("文本文件无控制字符（#54）", t_no_control_chars),
        ("逐字稿无损且中文可核（#55）", t_transcript_lossless),
        ("anchor 中文可核且不空集假绿（#56）", t_anchor_chinese_not_vacuous),
        ("引语「错位」与「编造」分开报（#57）", t_verify_quotes_misplaced_vs_fabricated),
        ("中文按字计数·查不到要明说（#58/#59）", t_chinese_unit_count_and_honest_capability),
        ("语言过滤不静默（#60）", t_verify_quotes_lang_filter_not_silent),
        ("缺陷台账正文数字不腐烂", t_defect_ledger_stats),
        ("文档数字与代码不漂移", t_docs_no_drift),
        ("schema 与 --help 完整", t_schema_and_help),
        ("错误信息人话化", t_errors_are_human),
    ]
    if args.only:
        keep = {x.strip() for x in args.only.split(",") if x.strip()}
        tests = [t for t in tests if t[1].__name__ in keep]
        missing = keep - {t[1].__name__ for t in tests}
        assert not missing, f"--only 未匹配到任何测试：{sorted(missing)}"
        print(f"（--only 过滤：{len(tests)} 项）")

    for name, fn in tests:
        check(name, fn)

    print(f"\n{'─' * 60}")
    print(f"通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    if SKIPPED:
        # #65：跳过必须**如实打印**，不能混进「通过」里冒充跑过。
        print(f"\n⚠️未运行 {len(SKIPPED)} 项（需要作者工作区的真实素材，"
              f"设 RULAI_WORKSPACE=1 才会跑）：")
        for name, what in SKIPPED:
            print(f"  · {name} —— 缺 {what}")
        print("  这一栏**不是失败**，但也不等于「这些检查通过了」。")
    if FAIL:
        print("\n失败明细：")
        for n, e in FAIL:
            print(f"  ❌ {n}\n     {e[:400]}")
        return 1
    print("🎉 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
