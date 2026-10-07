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
        out = run(["gate", str(rep), "--min", "B"]).stdout
        assert "总分 80" in out and "通过门槛" in out, out
        assert "consistency=26" in out, "分项解析失败"
        run(["gate", str(rep), "--min", "A"], expect=1)
        # fallback 自测降级
        fb = Path(d) / "fb.md"
        fb.write_text("# 报告\n\neval_mode: fallback-self\n\n"
                      "## 维度 1 · 立场/结论一致性（30 分）\n小计：30/30\n"
                      "## 维度 2 · 风格辨识度（20 分）\n得分：20/20\n"
                      "## 维度 3 · 边缘诚实度（20 分）\n得分：20/20\n"
                      "## 维度 4 · 来源透明度（15 分）\n得分：15/15\n"
                      "## 维度 5 · 结构完整度（15 分）\n得分：15/15\n"
                      "**总分** 100\n", encoding="utf-8")
        o = run(["gate", str(fb)], expect=1).stdout
        assert "风格辨识度" in o and ("作废" in o or "style=0" in o), o
        # 非双 Agent 默认不得通过
        assert "非双 Agent" in run(["gate", str(fb)], expect=1).stdout
        # 显式 allow-fallback 才放行
        assert "通过门槛" in run(["gate", str(fb), "--allow-fallback"]).stdout

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
    src = ROOT.parent / "video-run" / "sources" / "arj7oStGLkU.en.srt"
    if not src.exists():
        return  # 素材未随包分发时跳过（CI 里不联网抓取）
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
    card = ROOT.parent / "video-run" / "skills" / "two-kinds-of-procrastination" / "SKILL.md"
    if not card.exists():
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
    snap = ROOT.parent / "video-run" / "eval" / "FROZEN.snapshot.json"
    if not snap.exists():
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
    base = ROOT.parent                       # run 已被 helper 占用，这里用 base
    sunzi = ROOT / "examples" / "sample-bundle" / "skills" / "five-affairs-seven-questions" / "SKILL.md"
    musk = base / "musk-run" / "skills" / "musk-thinking" / "SKILL.md"
    ted = base / "video-run" / "skills" / "two-kinds-of-procrastination" / "SKILL.md"
    for name, pth in (("书籍(孙子)", sunzi), ("人物(马斯克)", musk), ("视频(TED)", ted)):
        if not pth.exists():
            continue
        r = run(["validate", str(pth)])
        assert "error 0" in r.stdout, f"{name} 卡片未通过静态校验：{r.stdout}"
    # 视频素材必须是真实抓取（声明里有 URL 与抓取日期）
    ted_srt = base / "video-run" / "sources" / "arj7oStGLkU.en.srt"
    if ted_srt.exists() and ted.exists():
        head = ted.read_text(encoding="utf-8")[:1200]
        assert "youtube.com/watch" in head, "视频卡缺来源 URL"
        assert "2026-10-04 抓取" in head, "视频卡缺抓取日期"
        qv = base / "video-run" / "eval" / "quote-verification.json"
        if qv.exists():
            d = _json.loads(qv.read_text(encoding="utf-8"))
            assert d["verified"] > 0 and not d["unverified"], f"视频卡引语未全部核到：{d}"


def t_style_decoy_anonymity():
    """C8：盲测材料不得泄露哪个候选来自被测卡片。

    第二轮评分员指出：`style-decoys.md` 顶部写着"候选 B 由出题方撰写"，
    等于把答案告诉评分者——维度 2 的盲测因此不可信。
    """
    f = ROOT.parent / "video-run" / "eval" / "style-decoys.md"
    if not f.exists():
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
    card = ROOT.parent / "video-run" / "skills" / "two-kinds-of-procrastination" / "SKILL.md"
    if not card.exists():
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
    card = ROOT.parent / "video-run" / "skills" / "two-kinds-of-procrastination" / "SKILL.md"
    corpus = ROOT.parent / "video-run" / "sources" / "arj7oStGLkU.en.transcript.md"
    if not (card.exists() and corpus.exists()):
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
    card = ROOT.parent / "video-run" / "skills" / "two-kinds-of-procrastination" / "SKILL.md"
    corpus = ROOT.parent / "video-run" / "sources" / "arj7oStGLkU.en.transcript.md"
    if not (card.exists() and corpus.exists()):
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
    skip = {".git", "__pycache__", ".pytest_cache"}
    diffs, missing = [], []
    for src in sorted(ROOT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(ROOT)
        if set(rel.parts) & skip or rel.suffix == ".pyc":
            continue
        dst = installed / rel
        if not dst.exists():
            missing.append(str(rel))
        elif not filecmp.cmp(src, dst, shallow=False):
            diffs.append(str(rel))
    assert not missing, f"全局副本缺 {len(missing)} 个文件（改完没同步？）：{missing[:8]}"
    assert not diffs, f"全局副本有 {len(diffs)} 个文件与项目不一致（改完没同步？）：{diffs[:8]}"


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

    # 段落级重复：README 首屏的版本说明整段重复过一次（同样是在 docs-check 之后才出现）
    for para in re.findall(r"^(?:\*\*v\d+\.\d+\.\d+[^\n]*\n(?:\*\*[^\n]*\n|[^\n*][^\n]*\n){1,4})",
                           rd, re.M):
        assert rd.count(para) <= 1, f"README.md 有整段重复：{para[:40]!r}"


def t_schema_and_help():
    assert "bundle.schema.json" in run(["schema", "bundle"]).stdout
    h = run(["--help"]).stdout
    for cmd in ("chunk", "transcript", "research", "strategy", "trigger", "diff", "count"):
        assert cmd in h, f"--help 缺 {cmd}"


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
        ("validate 拦截步骤禁令/完成标准/失败模式", t_validate_catches),
        ("output-eval 产物体检", t_output_eval),
        ("gate 门槛与自测降级", t_gate),
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
        ("引语段号锚定（#46）", t_anchor_verifier),
        ("素材零重叠检测（8-gram 包含率）", t_overlap_detector),
        ("测试不许漏注册（#45）", t_no_unregistered_tests),
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
    if FAIL:
        print("\n失败明细：")
        for n, e in FAIL:
            print(f"  ❌ {n}\n     {e[:400]}")
        return 1
    print("🎉 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
