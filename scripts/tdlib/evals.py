# -*- coding: utf-8 -*-
"""tdlib.evals — 触发评测执行器 / 输出评测 / token 计量 / 基准。

对标 cangjie-skill 的 run_trigger_evals.py、run_output_evals.py、benchmark.py、count_tokens.py。

**关键设计：Agent 负责回答，脚本负责判分。**
本包零网络，因此不代替模型调用 LLM。命令分两步：
  1. `td.py trigger record`  生成待答问卷（含整包 name+description，强制选择题而非判断题）
  2. （Agent 或人工作答，填 answers.json）
  3. `td.py trigger score`   机械判分 → 通过率 + 失败用例定位
这样既保留了 cangjie 盲测防作弊的设计意图，又不引入网络依赖与 API key。
"""
from __future__ import annotations

import json
import re
import statistics
import time
from pathlib import Path

from . import contracts
from .util import (ToolError, count_tokens, ensure_dir, info, jaccard, ngrams, now_iso,
                   ok, read_json, read_text, token_source, warn, write_json)

TRIGGER_SUITE_SCHEMA = "rulai-distill/testsuite/v1"


# --------------------------------------------------------------------------
# 触发测试
# --------------------------------------------------------------------------
def build_suite(bundle_dir: Path, out: Path | None = None, runs: int = 3) -> dict:
    """从 bundle 生成触发评测套件，**按上游 eval-suite 契约**产出。

    契约字段：case_id / prompt / expected(枚举) / sibling_target / runs。
    expected 枚举只有四个值，本包按下列规则映射：
        expect 为空            → should_not_trigger（诱饵）
        expect 等于自身        → should_trigger
        期望另一个兄弟能力      → sibling（并写 sibling_target）
    附加字段（契约 additionalProperties 未设 false，允许）：difficulty / why / pairwise_with。
    """
    bundle = read_json(Path(bundle_dir) / "bundle.json")
    skills = [{"name": s.get("slug"), "description": s.get("description", "")}
              for s in bundle.get("skills", [])]
    cases: list[dict] = []
    for s in skills:
        # target_slug：契约的 expected 是枚举（should_trigger/sibling/…），
        # 不带"应该是哪个技能"。这是本包附加字段（契约允许），**盲测包会剥掉它**。
        cases.append({
            "case_id": f"t-{len(cases) + 1:02d}", "prompt": "",
            "expected": "should_trigger", "target_slug": s["name"],
            "difficulty": "easy", "why": ""})
    cases.append({"case_id": f"d-{len(cases) + 1:02d}", "prompt": "",
                  "expected": "should_not_trigger", "difficulty": "medium",
                  "why": "书摘/摘要需求 → 不该触发本包"})
    cases.append({"case_id": f"d-{len(cases) + 1:02d}", "prompt": "",
                  "expected": "should_not_trigger", "difficulty": "medium",
                  "why": "紧急止损 → 卡片明确声明不适用"})
    if len(skills) >= 2:
        for i, (a, b) in enumerate(((0, 1), (1, 0))):
            cases.append({
                "case_id": f"x-{i + 1:02d}", "prompt": "",
                "expected": "sibling", "sibling_target": skills[b]["name"],
                "difficulty": "hard", "pairwise_with": [skills[a]["name"]],
                "why": f"跨技能混淆：应判给 {skills[b]['name']} 而非 {skills[a]['name']}"})

    suite = {
        "schema_version": 1,
        "suite_id": f"suite-{Path(bundle_dir).name}",
        "target": ",".join(s["name"] for s in skills),
        "split_seed": 42,
        "train_ratio": 0.6,
        "trigger_cases": cases,
        "rules": [
            "prompt 必须用真实用户口语，不要写成规范任务书",
            "至少 1 条 sibling 用例（A→B 与 B→A 各一条，单向通过不算）",
            "诱饵必须是真实需求，只是不该由本包回答",
            "测试时把 skills_in_scope 全部给被测 Agent，让它做选择题",
        ],
        "skills_in_scope": skills,
    }
    res = contracts.validate("eval-suite", suite)
    if not res["ok"]:
        raise ToolError("生成的评测套件不符合上游 eval-suite 契约",
                        *(res["errors"][:6]))
    p = Path(out) if out else Path(bundle_dir) / "eval-suite.json"
    write_json(p, suite)
    return suite


def _cases_of(suite: dict) -> list[dict]:
    """取用例列表：契约用 trigger_cases，本包旧格式用 cases。"""
    return suite.get("trigger_cases") or suite.get("cases") or []


def _case_id(c: dict) -> str:
    """兼容两种 case 键：契约用 case_id，本包旧格式用 id。"""
    return str(c.get("case_id") or c.get("id"))


def _case_expect(c: dict) -> str | None:
    """从两种格式里取出期望的 slug（None = 不该触发）。"""
    if "expected" in c and c["expected"] in ("should_trigger", "should_not_trigger", "sibling", "edge_case"):
        if c["expected"] == "should_not_trigger":
            return None
        if c["expected"] == "sibling":
            return c.get("sibling_target") or c.get("expect")
        return c.get("target_slug") or c.get("expect")   # should_trigger
    return c.get("expect")


def split_cases(suite: dict, seed: int | None = None, train_ratio: float | None = None) -> dict:
    """固定种子做 train/validation 切分。

    为什么要切：全量用例反复用于调 prompt 会过拟合。validation 在选版前保持隐藏，
    选完版只跑一次。方法学对齐上游 kangarooking/cangjie-skill 的 run_trigger_evals.py。
    """
    import random
    seed = seed if seed is not None else suite.get("split_seed", 42)
    ratio = train_ratio if train_ratio is not None else suite.get("train_ratio", 0.6)
    cases = list(_cases_of(suite))
    rng = random.Random(seed)
    rng.shuffle(cases)
    k = round(len(cases) * ratio)
    train = [_case_id(c) for c in cases[:k]]
    val = [_case_id(c) for c in cases[k:]]
    return {"schema": "rulai-distill/trigger-split@1", "split_seed": seed,
            "train_ratio": ratio, "train": train, "validation": val,
            "note": "validation 在选版前保持隐藏；选版后只跑一次，否则结果没有意义"}


def record_sheet(suite: dict, out: Path, case_ids: list[str] | None = None) -> Path:
    """生成待答问卷（Agent 把选择填进 actual 字段）。

    case_ids 为空则给全部；用于只暴露 train 集、把 validation 留到选版后再测。
    约定：表里的「期望」列同时显示契约枚举与目标 slug——枚举给机器看，slug 给人看。
    """
    lines = ["# 触发测试答卷", "",
             "> 规则：把下面候选技能的**全部** name+description 给被测 Agent，",
             "> 让它做「该激活哪一个」的**选择题**。不要告诉它每个用例测什么。", "",
             "## 候选技能（注入被测 Agent）", ""]
    for s in suite.get("skills_in_scope", []):
        lines.append(f"- `{s['name']}`：{s['description'][:120]}")
    lines += ["", "## 用例", "",
              "| id | 契约枚举 | 目标 slug | prompt | actual（待填） |",
              "|---|---|---|---|---|"]
    for c in _cases_of(suite):
        cid = _case_id(c)
        if case_ids and cid not in case_ids:
            continue
        exp = _case_expect(c)
        lines.append(f"| {cid} | {c.get('expected','-')} | {exp or 'null'} | "
                     f"{c.get('prompt','')} |  |")
    path = Path(out)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def prepare_blind(suite: dict, case_ids: list[str], out_dir: Path) -> Path:
    """生成盲测任务包：只含 prompt + 候选技能清单，**不含 expect / why**。"""
    out_dir = ensure_dir(Path(out_dir))
    all_cases = _cases_of(suite)
    cases = [c for c in all_cases if not case_ids or _case_id(c) in case_ids]
    payload = {
        "schema": "rulai-distill/trigger-blind@1",
        "instruction": "对每条 prompt，从候选技能中选出唯一应激活的一项；都不适用则选 none。只输出 JSON。",
        "skills_in_scope": suite.get("skills_in_scope", []),
        "cases": [{"case_id": _case_id(c), "prompt": c.get("prompt", "")} for c in cases],
    }
    p = out_dir / "blind-tasks.json"
    write_json(p, payload)
    with (out_dir / "answers-template.jsonl").open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps({"case_id": _case_id(c), "run": 1, "selected_skill": "<slug|none>"},
                               ensure_ascii=False) + "\n")
    return p


NULL_TOKENS = {"none", "null", "nil", "n/a", "na", "-", "", "无", "不适用"}


def _norm_answer(v) -> str | None:
    """把被测 Agent 的作答归一化。

    实测踩坑：Agent 普遍会返回字符串 "none"，而不是 JSON null。
    第一版没做这个归一化，导致两条"正确判断为不触发"的诱饵被误判成误触发（FP=2），
    诱饵通过率显示 0% —— 而实际是 100%。盲测跑一次才发现。
    """
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in NULL_TOKENS else s


def score_suite(suite: dict, answers: dict) -> dict:
    """机械判分：precision / recall / F1 + 兄弟混淆率 + 诱饵通过率，容错 0。

    指标定义（与上游 run_trigger_evals.py 同口径）：
      正例 = expect 非 null 的用例；诱饵 = expect 为 null
      TP   选了正确的那个            FP  诱饵被激活（误触发，最致命）
      FN   正例选错或没选            兄弟混淆 = 选中的也是候选技能之一，但选错了邻居
      sibling_confusion_rate = 兄弟混淆数 / 正例数
    """
    cases = _cases_of(suite)
    if not cases:
        raise ToolError("测试套件里没有用例", "先 `td.py trigger build`")
    empty = [c for c in cases if not c.get("prompt")]
    if empty:
        raise ToolError(f"有 {len(empty)} 条用例 prompt 为空，无法判分",
                        "补齐 prompt 后再判分——空 prompt 的用例会让通过率虚高")
    scope = {s["name"] for s in suite.get("skills_in_scope", [])}
    results, tp = [], 0
    fp = fn = sibling = decoy = decoy_ok = 0
    for c in cases:
        cid = _case_id(c)
        expect = _case_expect(c)
        if cid not in answers:
            results.append({"id": cid, "status": "unanswered", "expect": expect})
            fn += 1 if expect else 0
            continue
        actual = _norm_answer(answers[cid])
        if expect is None:
            decoy += 1
            if actual is None:
                decoy_ok += 1
                results.append({"id": cid, "status": "pass", "expect": None, "actual": None,
                                "kind": "decoy", "why": c.get("why", "")})
            else:
                fp += 1
                results.append({"id": cid, "status": "fail", "expect": None, "actual": actual,
                                "kind": "decoy", "why": c.get("why", "")})
            continue
        if actual == expect:
            tp += 1
            results.append({"id": cid, "status": "pass", "expect": expect, "actual": actual,
                            "kind": "sibling" if c.get("pairwise_with") else "trigger",
                            "why": c.get("why", "")})
        else:
            fn += 1
            kind = "sibling" if (actual in scope and actual != expect) else "trigger"
            if kind == "sibling":
                sibling += 1
            results.append({"id": cid, "status": "fail", "expect": expect, "actual": actual,
                            "kind": kind, "why": c.get("why", "")})

    pos = tp + fn
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / pos if pos else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    passed = sum(1 for r in results if r["status"] == "pass")
    unanswered = [r["id"] for r in results if r["status"] == "unanswered"]
    by_kind: dict[str, dict] = {}
    for r in results:
        k = r.get("kind", "unanswered")
        agg = by_kind.setdefault(k, {"pass": 0, "total": 0})
        agg["total"] += 1
        if r["status"] == "pass":
            agg["pass"] += 1
    return {
        "schema": "rulai-distill/trigger-eval@1",
        "generated_at": now_iso(),
        "suite_id": suite.get("suite_id") or suite.get("package"),
        "target": suite.get("target"),
        "total": len(cases),
        "passed": passed,
        "pass_rate": round(passed / len(cases), 3) if cases else 0,
        "metrics": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "decoy_total": decoy, "decoy_pass_rate": round(decoy_ok / decoy, 3) if decoy else 1.0,
            "sibling_confusion": sibling,
            "sibling_confusion_rate": round(sibling / pos, 3) if pos else 0.0,
        },
        "by_kind": by_kind,
        "unanswered": unanswered,
        "verdict": "pass" if passed == len(cases) else "fail",
        "results": results,
    }


# --------------------------------------------------------------------------
# 输出评测（对产物做机械体检）
# --------------------------------------------------------------------------
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


def failure_case(skill: str, prompt: str, actual: str, expected: str, severity: str,
                 category: str | None = None, evidence: str = "",
                 planned: list[str] | None = None, attachments: list[str] | None = None) -> dict:
    """记录一条失败用例，**按上游 failure-case 契约**。

    这不是形式主义：本项目迄今 15 个缺陷里有 11 个在验证/度量环节，
    每一条都应能被"复现"——failure-case 就是把"当时怎么错的"沉淀成可回放的记录。
    """
    if severity not in SEVERITY_ORDER:
        raise ToolError(f"severity 必须是 {sorted(SEVERITY_ORDER)}，收到 {severity!r}")
    fc = {
        "schema_version": 1,
        "skill": skill,
        "failure_case": {
            "prompt": prompt,
            "actual": actual,
            "expected": expected,
            "severity": severity,
            "attachments": attachments or [],
        },
        "diagnosis": {
            "category": category,
            "evidence": evidence,
            "planned_changes": planned or [],
        },
    }
    res = contracts.validate("failure-case", fc)
    if not res["ok"]:
        raise ToolError("失败用例不符合上游 failure-case 契约", *(res["errors"][:6]))
    return fc


def export_failure_cases(cases: list[dict], out: Path) -> dict:
    """导出失败用例集（逐条契约校验后才写）。"""
    ok, bad = [], []
    for c in cases:
        r = contracts.validate("failure-case", c)
        (ok if r["ok"] else bad).append(c if r["ok"] else {"case": c, "errors": r["errors"]})
    report = {
        "schema": "rulai-distill/failure-set@1",
        "generated_at": now_iso(),
        "total": len(cases),
        "valid": len(ok),
        "invalid": len(bad),
        "by_severity": {k: sum(1 for c in ok if c["failure_case"]["severity"] == k)
                        for k in SEVERITY_ORDER},
        "by_category": {k: sum(1 for c in ok if c["diagnosis"].get("category") == k)
                        for k in ("activation_miss", "false_activation", "knowledge_gap",
                                  "execution_gap", "boundary_gap", "structure_gap",
                                  "tool_gap", "preprocessing_gap", "eval_gap")},
        "cases": ok,
        "invalid_cases": bad,
    }
    write_json(Path(out), report)
    return report


def output_eval(card: Path) -> dict:
    from .validate import check_card
    text = read_text(card)
    base = card.parent
    problems = check_card(card, base)
    errors = [m for lvl, m in problems if lvl == "error"]
    warns = [m for lvl, m in problems if lvl == "warn"]
    quote = re.findall(r"^>\s*[「\"](.+?)[」\"]", text, re.M)
    return {
        "schema": "rulai-distill/output-eval@1",
        "generated_at": now_iso(),
        "card": str(card),
        "chars": len(text),
        "tokens": count_tokens(text),
        "sections": {k: bool(re.search(pat, text, re.M)) for k, pat in (
            ("R", r"(?m)^#+\s*R\s*[—-]"), ("I", r"(?m)^#+\s*I\s*[—-]"),
            ("A1", r"(?m)^#+\s*A1"), ("A2", r"(?m)^#+\s*A2"),
            ("E", r"(?m)^#+\s*E\s*[—-]"), ("B", r"(?m)^#+\s*B\s*[—-]"))},
        "quotes_found": len(quote),
        "errors": errors,
        "warns": warns,
        "verdict": "fail" if errors else ("warn" if warns else "pass"),
    }


# --------------------------------------------------------------------------
# token 计量
# --------------------------------------------------------------------------
_TS_LINE = re.compile(r"^[\[【](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)[\]】]\s*(.+)$", re.M)


def _index_by_timestamp(corpus_text: str, corpus: Path | None = None) -> dict[str, str]:
    """从逐字稿建 `时间戳 → 文本` 索引。

    **顺序很关键：段落优先，cue 补充。**
    段落是 cue 的超集（同一段落起点下，段落文本含整段合并后的内容）。
    实测踩过两次：
      · 先收 cue 时，段落起点时间戳只映射到 cue 的第一句 → 跨 cue 的引语一律判"核不到"
        （TED 那份逐字稿 5/6 条都这样丢的）
      · 只收段落时，卡片按单句（cue 级）引用又核不到
    两个层级都收，且段落优先。
    """
    out: dict[str, str] = {}
    for m in _TS_LINE.finditer(corpus_text):
        out.setdefault(m.group(1).replace(",", "."), _norm_frag(m.group(2)))
    if corpus is not None:
        # 注意：corpus.stem 对 "x.transcript.md" 是 "x.transcript"，
        # 而 with_suffix 只替换最后一段后缀 → 两者都会拼出 "x.transcript.transcript.json"。
        # 这里显式按文件名去后缀拼接（实测踩过）。
        base = corpus.name[: len(corpus.name) - len(corpus.suffix)] if corpus.suffix else corpus.name
        for cand in (corpus.parent / (base + ".transcript.json"),
                     corpus.parent / (base + ".json")):
            if not cand.exists():
                continue
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for c in data.get("cues", []) or []:
                out.setdefault(hhmmss(c["start_ms"]), _norm_frag(c.get("text", "")))
            break
    return out


def hhmmss(ms: int) -> str:
    s, m = ms // 1000, (ms % 1000) // 100 * 10
    h, m2 = s // 3600, (s % 3600) // 60
    return f"{h:02d}:{m2:02d}:{s % 60:02d}.{m:02d}"


def _norm_frag(s: str) -> str:
    s = s.replace("&amp;", "&").replace("**", "").replace("*", "")
    # 破折号统一：SRT 里破折号常写成 "--"，卡片里我写成 "—"（em dash）或 "-"
    # 三者必须归一到同一形态，否则核验器会把完全一致的引语判成"核不到"
    # （TED 那份逐字稿的 self-starter -- something 正是这种）
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    s = re.sub(r"-{2,}", "-", s)
    # 省略号统一：卡片里 `We can visualize the future… make long-term plans`
    # 用 `…` 合并了原文里由句号分隔的两个分句。语料侧是 `. `，不归一就核不到
    # （实测：这条真引语被误判 unverified）。
    s = s.replace("…", " ").replace("...", " ")
    return re.sub(r"\s+", " ", s).strip()


def _blank_non_ref_regions(text: str) -> str:
    """把**非引用区域**（YAML front matter / 围栏代码块 / 行内代码）里的
    【第N条】与 [HH:MM:SS] 定位标记替换成等长空白，使它们不参与核验。

    为什么必须有：卡片里的 front matter `source_locator`、更正记录里
    "引语挂在 [00:02:27.20] 上是错的"、以及文档里讲解工具用法时写的示例时间戳，
    都是**元信息而不是引用**。不挖空就会产生假失败——同一类问题连犯三次，
    只改措辞是治标。
    """
    # 1) YAML front matter
    text = re.sub(r"\A---\n.*?\n---\n",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    # 2) 围栏代码块 ```...```
    text = re.sub(r"```.*?```",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    # 3) 行内代码 `...`
    text = re.sub(r"`[^`\n]*`",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return text


def _looks_truncated(frag: str, body: str) -> bool:
    """判断引语是否**在当前 cue 处被截断**（因此才需要看邻接 cue）。

    只有真正被截断的引语才允许跨 cue 匹配。判据：引语的前若干字符在 body 里，
    但**尾部不在** —— 说明后半句落到了下一个 cue。
    完整落在单 cue 里的引语一律不跨 cue（否则会串到隔壁 cue，是回归测试 D 用例
    专门要防的失败模式）。
    """
    if not frag or not body:
        return False
    if frag in body:
        return False  # 完整命中，无需邻接
    head = frag[:max(12, len(frag) // 2)]
    tail = frag[max(12, len(frag) // 2):]
    return bool(head) and bool(tail) and head in body and tail not in body


def _loose_match(frag: str, body: str, min_run: int = 18) -> bool:
    """引语在语料里**分段命中**也算核到（跨 cue / 跨句省略场景）。

    为什么需要：字幕把一句话切进多个 cue，卡片常把跨 cue 的引语用 `…` 合并成一行。
    严格子串匹配会判"核不到"，但它是真引语——**假阴性比假阳性危险**，
    会让人把正确引用误删。判据：把引语按标点切成片段，**命中片段数 ≥ 2**
    （或单片段已够长）即视为核到。
    """
    if not frag or not body:
        return False
    if frag in body:
        return True
    parts = [p.strip() for p in re.split(r"[,;:!?]|\.\s", frag) if len(p.strip()) >= 8]
    if not parts:
        return False
    hits = [p for p in parts if p in body]
    return len(hits) >= 2 or any(len(h) >= min_run for h in hits)


def _clean_frag(q: str) -> str:
    return _norm_frag(q)[:60]


def verify_quotes(card: Path, corpus: Path) -> dict:
    """机械核验卡片里的引语是否真在语料中（对标 nuwa 的来源占比检查）。

    实现踩过的坑（务必保留这个教训）：
      **第一版核验脚本只看引用编号【第N条】之前的窗口** → 16/18 条引语报"未核到"，
      而其中多数实际上完全命中。原因是卡片里的写法是
      `2016-06-17【第2509条】「Turns out ...」` —— **引号在编号之后**，不在之前。
      假阴性比假阳性危险：它会让人把正确的引用误删。

    规则：
      1. 找出卡片里所有【第N条】引用的**全部出现位置**（同一编号可能引用多次）；
      2. 在每个位置**向后**取窗口，收集该窗口内的「…」引号片段；
      3. 片段规范化（去空白）后在语料对应条目中做子串匹配；
      4. 报 unverified（核不到）与 orphaned（语料里没这个编号）。
    """
    text = read_text(card)
    corpus_text = read_text(corpus)
    # 语料索引：**按表头位置切片**，不用带前瞻的大正则。
    # 实测：`【第N条\|…】(.+?)(?=\n\n【第|\Z)` 在 3.3MB 上只匹配到 27/17144 条（前瞻在
    # 超长文本上退化），导致大量编号被误报"语料中不存在"。位置切片 100% 覆盖且 O(n)。
    def _norm(s: str) -> str:
        """两侧统一归一化：HTML 实体、markdown 强调、直/弯引号与破折号、空白。"""
        s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
        s = s.replace("**", "").replace("*", "")
        s = (s.replace("’", "'").replace("‘", "'")
               .replace("“", '"').replace("”", '"')
               .replace("—", "-").replace("–", "-").replace(" ", " "))
        return re.sub(r"\s+", " ", s).strip()

    entries: dict[str, str] = {}
    # ── 时间戳定位（视频/播客/逐字稿来源）──
    # 真实缺口：卡片从逐字稿蒸馏时，引语定位是 `[00:00:16.10]` 而不是 `【第N条】`，
    # 原来的核验器对这类卡片完全失效。两种定位现在都支持。
    entries.update(_index_by_timestamp(corpus_text, corpus))
    # 表头只匹配到分隔符 `|` 为止。曾用 `【第(\d+)条\s*\|[^\]]*】`，在 17144 条的真实
    # 语料上只命中 27 条（超长文本下该模式退化），导致大量编号被误报"语料中不存在"。
    # `【第(\d+)条 \|` 实测 17144/17144 全覆盖，且不受表头内日期/ID 格式影响。
    heads = list(re.finditer(r"【第(\d+)条 \|", corpus_text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(corpus_text)
        entries[m.group(1)] = _norm(corpus_text[m.end():end])
    norm_corpus = entries

    refs = re.findall(r"【第(\d+)条", text)
    ts_refs = re.findall(r"[\[【](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)", text)
    checked, verified, unverified, unquoted, orphaned = 0, [], [], [], []
    all_ref_pos = [m.start() for m in re.finditer(r"【第\d+条", text)]
    for rid in dict.fromkeys(refs):
        for m in re.finditer(rf"【第{rid}条", text):
            # 窗口必须止于**下一个引用**——否则会把下一条引语算到本条头上
            # （实测：320 字符固定窗口会把后面引语错配到前面编号上）
            nxt = [p for p in all_ref_pos if p > m.start()]
            # 窗口 120 字符且止于下一个引用：只认「紧跟引用之后的引号」，
            # 否则会把作者自己的行文（也用「」）误当成来源引语。
            end = min([m.start() + 120] + nxt[:1])
            window = text[m.start():end]
            quotes = re.findall(r"「(.+?)」", window, re.S)
            if not quotes:
                # 引用了但没给逐字引语（概述式引用）——**必须留痕**，不能静默跳过，
                # 否则"覆盖率"会被悄悄高估。
                unquoted.append({"ref": rid, "note": "引用附近无引号片段（概述式引用）"})
                continue
            if rid not in norm_corpus:
                orphaned.append(rid)
                break
            body = norm_corpus[rid]
            # 归一化后逐个尝试；**任一命中即算该引用被核实**。
            # 区分两种情况（实测踩过：作者自己的行文也用「」）：
            #   · 引用附近没有任何 ≥8 字的引号片段 → unquoted（提示级，不算失败）
            #   · 有引号片段但全部核不到 → unverified（失败级）
            cands = []
            for q in quotes:
                frag = re.sub(r"\s+", " ", q).replace("&amp;", "&")
                frag = frag.replace("**", "").replace("*", "")
                frag = re.sub(r"\s+", " ", frag).strip()[:60]
                if len(frag) >= 8:
                    cands.append(frag)
            if not cands:
                unquoted.append({"ref": rid, "note": "引用附近无逐字引语（可能是概述式引用）"})
                continue
            checked += 1
            hit = next((c for c in cands if c in body), None)
            if hit:
                verified.append({"ref": rid, "quote": hit})
            else:
                unverified.append({"ref": rid, "quote": cands[0]})
    # 时间戳型引语：逐条核验
    ts_checked, ts_verified, ts_unverified = 0, [], []
    locator_only: list[str] = []
    if ts_refs:
        ts_index = _index_by_timestamp(corpus_text, corpus)
        # 邻接 cue 索引：字幕常把一句话切进多个 cue，卡片引的是合并后的整句。
        # 只按单 cue 匹配 → 跨 cue 引语一律核不到（实测 `a place that all of you
        # procrastinators out there know very well` 就横跨两个 cue）。
        # 这里显式建 `本 ts → 紧随其后 2 个 ts`，匹配时允许在窗口内命中。
        _ts_keys = list(ts_index.keys())
        _ts_next: dict[str, list[str]] = {}
        for _i, _k in enumerate(_ts_keys):
            _ts_next[_k] = _ts_keys[_i + 1: _i + 3]
        # **先把非引用区域挖空再核验**（缺陷 #36，同一坑第 3 次出现）。
        # 更正记录里写"某引语挂在 `[00:02:27.20]` 上是错的"、或 front matter 里
        # 写 `source_locator: ...[00:02:00.10]...`，这些都是**元信息不是引用**。
        # 前两次只改卡片措辞（把方括号去掉），第三次同样的错又冒出来——说明必须
        # 在工具侧根治：代码块 / 行内代码 / front matter 内的时间戳不参与核验。
        text = _blank_non_ref_regions(text)
        # 时间戳引用数必须按**挖空后**的文本统计，否则 front matter / 代码块里
        # 被挖掉的那些仍计入分母 → 对账恒等式不成立（16+25+1=42 ≠ 43）。
        ts_refs = re.findall(r"[\[【](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)", text)
        # **并列时间戳分组**：同一行内 `[ts1]、[ts2]` 是同一条引语的多个定位。
        # 预先按「两时间戳之间只隔 `、`/`,`/空白」建组，核验时一并纳入 body。
        _ts_grouped: dict[tuple[str, str], bool] = {}
        for _ln in text.split("\n"):
            _ms = list(re.finditer(r"[\[【](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)", _ln))
            for _a in range(len(_ms)):
                for _b in range(_a + 1, len(_ms)):
                    _gap = _ln[_ms[_a].end():_ms[_b].start()]
                    # gap 里必然含前一个时间戳的**闭合括号**（`]` / `】`），
                    # 实测形如 `]、`。漏掉它会导致并列分组永不成立（踩过一次）。
                    if re.fullmatch(r"[\]】\s、,，/和及]*", _gap):
                        _ts_grouped[(_ms[_a].group(1).replace(",", "."),
                                     _ms[_b].group(1).replace(",", "."))] = True
        # 窗口必须止于**下一个时间戳引用**——否则会把下一条引语（或作者自己的行文）
        # 算到本条头上。这与 【第N条】 的处理是同一个坑，已犯两次。
        ts_marks = [m.start() for m in
                    re.finditer(r"[\[【]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?", text)]
        for m in re.finditer(r"[\[【](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)", text):
            key = m.group(1).replace(",", ".")
            nxt = [p for p in ts_marks if p > m.start()]
            prv = [p for p in ts_marks if p < m.start()]
            # **并列多时间戳 = 同一条引语的多个定位**（缺陷 #39）。
            # 卡片里写 `| Dark Playground（"a place that all of you..."）| [00:06:17.50]、
            # [00:06:43.90] |` 时，引语只落在第二个时间戳上。只按第一个核 → 误判 fail
            # （实测就是这样被判 unverified 的，而引语确实在语料里）。
            # 规则：同一逻辑行内、用 `、` 或 `,` 紧邻连接的后续时间戳，一并纳入 body。
            _cls0 = text.rfind("\n", 0, m.start()) + 1
            _cln0 = text.find("\n", m.end())
            _cur0 = text[_cls0: len(text) if _cln0 == -1 else _cln0]
            _body_keys = [key]
            for _m2 in re.finditer(r"[\[【](\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)", _cur0):
                _k2 = _m2.group(1).replace(",", ".")
                if _k2 != key and _ts_grouped.get((key, _k2)):
                    _body_keys.append(_k2)
            body = " ".join(ts_index.get(k, "") for k in _body_keys)
            # 两种引用写法都要支持：
            #   【00:00:30.60】「quote」   编号在前（与 【第N条】 一致）
            #   「quote」 —— [00:00:30.60]  时间戳在后（逐字稿常见排版）
            # 窗口不得跨入/跨出**表格行**。
            # 表格里每行都以 | 开头、含自己的时间戳与引语；跨行取窗会让相邻两行互相串味
            # （同一类边界错误第 5 次出现）。而引用块内多行（都以 > 开头）必须允许跨行，
            # 否则「引语占 3 行 + 第 4 行是 `> —— [时间戳]`」这种正常排版会被切断。
            def _line_at(txt: str, pos: int) -> str:
                nl = txt.rfind("\n", 0, pos)
                end = txt.find("\n", nl + 1)
                return txt[nl + 1: end if end != -1 else len(txt)]

            def _expand(txt: str, pos: int, step: int) -> int:
                in_table = _line_at(txt, pos).lstrip().startswith("|")
                while True:
                    if step < 0:
                        p_nl = txt.rfind("\n", 0, pos - 1)
                        # 上一行的范围永远是 [prev_start, pos-1)：
                        # p_nl < 0 表示**上一行就是文本开头**，它不是"没有上一行"，
                        # 仍必须检查它属不属于同一引用块。
                        # 踩过的坑（缺陷 #41）：`> 「…」\n> —— [00:00:05.00]`
                        # 这种两行引用块，第一行之前没有换行 → 旧代码
                        # `if p_nl <= 0: break` 直接返回，于是**第一行（真正的引语行）
                        # 永远进不了窗口** → 中文引语整条漏检，且没有任何提示。
                        prev_start = (p_nl + 1) if p_nl >= 0 else 0
                        if prev_start >= pos - 1:
                            break            # 确实没有上一行了
                        cand, nxt_pos = txt[prev_start: pos - 1], prev_start
                    else:
                        n_nl = txt.find("\n", pos)
                        if n_nl == -1:
                            break
                        nxt_pos = n_nl + 1
                        e2 = txt.find("\n", nxt_pos)
                        cand = txt[nxt_pos: e2 if e2 != -1 else len(txt)]
                    st = cand.strip()
                    if not (st.startswith(">") or st.startswith("<br>")):
                        break
                    if st.lstrip().startswith("|") != in_table:
                        break
                    pos = nxt_pos
                return pos

            # 先把窗口对齐到**当前行**的首尾（引语常与时间戳同行），
            # 再向两侧扩展——顺序反了会把同行引语切掉（实测踩过：排版 B 核到 0 条）。
            _ls = text.rfind("\n", 0, m.start()) + 1
            _le_nl = text.find("\n", m.end())
            _le = len(text) if _le_nl == -1 else _le_nl
            # 传 `_ls`（当前行起点）而不是 `_ls - 1`：让"上一行"的范围对上
            # `[prev_start, pos-1)`，否则会少取一个字符、恰好切掉闭合的 `」`
            # （同一个 bug 的另一半，见 _expand 内 #41 的注释）。
            line_start = _expand(text, _ls, -1)
            line_end = _expand(text, _le, +1)
            # 窗口用**已算好的逻辑行边界**（line_start/line_end），不再叠固定字符上限。
            # 实测踩过（缺陷 #31）：TED 卡的引语行普遍 216~248 字符，而 `m.start() - 200`
            # 会把长引语切掉一半 → `「(.+?)」` 缺闭合符匹配失败 → 整条被**静默跳过**，
            # 44 个时间戳引用只核到 3 个。逻辑行边界本身已是正确约束，再叠字符上限
            # 是自相矛盾；此处只保留一个宽松上限防跑飞。
            _WINDOW_CAP = 2000
            # 窗口从**当前逻辑行首**起算，而不是从时间戳位置 m.start() 起算。
            # 实测踩过（缺陷 #33）：`> 「...in the end, it works**。」——[00:09:43.10]`
            # 这种排版的闭合 `」` 在**时间戳之前**同一行内，从 m.start() 起扫永远扫不到
            # → 一条真引语被误判成"概述式引用"。改为从行首扫，同行闭合引语即可命中。
            fwd = text[max(line_start, _ls - _WINDOW_CAP): min(line_end, _le + _WINDOW_CAP)]
            bwd = text[max(line_start, m.start() - _WINDOW_CAP): m.start()]
            # 引号形式要**两种都认**：`「」` 与英文直引号 `"`。
            # 实测踩过（缺陷 #34）：卡片里 `讲者原话是 "That's one box for every week of a
            # 90-year life."（[00:13:08.30]）` 是逐字引语，却因只用 `「」` 抓取而被记成
            # "无逐字引语" → 引语被漏核。中文卡片里两种引号混用是常态。
            # 直引号只取**不含换行**的短片段，避免把跨行的对话引号整段吞进来。
            _pats = [r"「(.+?)」", r'"([^"\n]{8,300})"']
            # **引语语言必须与语料一致**（缺陷 #35）。TED / 英文播客的卡片语料是英文，
            # 卡片里那些用 `「」` 括的中文（`「每周一个盒子」的阶梯`、`「像自己人生的旁观者」`）
            # 是**作者自己的行文与概述**，不是来源引语。此前一律当引语去核 →
            # 10 条必然 unverified，verdict 永远 fail，工具等于不可用。
            # 判据：语料整体 CJK 占比低（<20%）= 非中文语料 → 丢弃纯中文候选片段。
            _cjk = len(re.findall(r"[\u4e00-\u9fff]", corpus_text))
            _corpus_is_en = len(corpus_text) > 200 and _cjk / len(corpus_text) < 0.20
            # **但不能连检出能力一起丢**（缺陷 #37，由 t_verify_quotes_timestamp 抓出）：
            # 一旦对所有中文候选无条件过滤，"中文引语在英文语料里根本没出现过"这种
            # **真问题**会被降级成 unquoted → verdict 变 pass，工具反而漏检了
            # （回归测试直接挂掉：卡片 C 应判 fail 却变成 pass）。
            # 正确边界：只在**表格行 / 出处标注**这类"作者行文重灾区"做语言过滤；
            # 正文引用块（`> 「…」——[ts]`）里的中文候选仍按引语核，核不到就 fail。
            _voice_line = _line_at(text, m.start())
            _in_author_voice = (_voice_line.lstrip().startswith("|")
                                or "出处" in _voice_line)
            # 第三类作者行文（缺陷 #40）：**归属声明块**。
            # 卡片里有一类专门说明"这段到底是谁说的"的块，形如
            #   `> ⚠️ **归属拆分**：……他只诊断到「Panic Monster 是唯一机制」这一层（[ts]）`
            # 块里的「」引用的是**本卡描述的对象**（一个做法名、一个概念），
            # 不是来源引语；按引语去核必然核不到 → 卡片明明没错却被判"来源不实"。
            # 这是我第三次踩同一个坑（前两次都是靠改卡片措辞躲过去，属治标）。
            # 根治办法是让工具认得这个结构：块内出现归属声明标记即视为作者行文区。
            # 判据刻意保守（只认明确的归属块抬头），以免误伤含真引语的正文块。
            # 元描述框也会写成**列表项**（`- step` / `3. xxx`），而 `_expand` 只连 `>`/`<br>`
            # 开头的行，所以 line_start..line_end 可能只有单行、漏掉抬头标记。
            # 检测范围因此取**整个 Markdown 块**（由空行分隔），而不是单行。
            # 也不要用固定字符窗口——实测 600 字符会把相邻的正文引语块一起吞进来，
            # 导致真引语被误判成元描述而漏核（回归用例直接挂）。空行才是块的正确边界。
            _bs = text.rfind("\n\n", 0, _ls)
            _block_start = _bs + 2 if _bs != -1 else 0
            _be = text.find("\n\n", _le)
            _block = text[_block_start: _be if _be != -1 else len(text)]
            # 标记清单包含所有"卡片在谈论自己"的元描述框：归属拆分、措辞修正、
            # 口径统一、更正记录。它们的共同点是引用的是**被讨论的说法**，
            # 而不是来源引语。每加一类标记，都是因为又踩了一次同一个坑。
            _in_attrib_block = any(tag in _block for tag in
                                   ("归属拆分", "**归属**", "归属：", "归属标注",
                                    "措辞修正", "口径统一", "更正记录"))

            def _keep(qs: list[str]) -> list[str]:
                out = []
                for q in qs:
                    q = _clean_frag(q)
                    if len(q) < 8:
                        continue
                    # 归属声明块：块内所有引号内容都是被描述的对象，不是引语。
                    if _in_attrib_block:
                        continue
                    if _corpus_is_en and _in_author_voice:
                        q_cjk = len(re.findall(r"[\u4e00-\u9fff]", q))
                        if q_cjk / max(len(q), 1) > 0.30:
                            continue  # 英文语料里的中文「」= 作者行文，不是引语
                    out.append(q)
                return out

            cands = _keep([q for p in _pats
                           for q in (re.findall(p, fwd, re.S) + re.findall(p, bwd, re.S))])
            if not cands:
                # **绝不能静默跳过**（缺陷 #32）。曾用 `continue` 把 37/44 个时间戳引用
                # 直接丢掉，报告只显示"引用 44 个但只核到 3 条"却不说明其余 37 条为何没核
                # —— 引语覆盖率被悄悄高估，且输出自相矛盾（评分员抓过同类问题）。
                # 进一步区分两类，避免把「表格里的纯定位锚点」和「概述式引用」混为一谈：
                #   · locator_only：表格 / 披露表里的时间戳锚点（如 `| [00:03:04.30] | MRI 对比 |`），
                #     它本来就不承载引语，不该混进引语统计；
                #   · unquoted：正文引用了时间戳却没给逐字引语 → 提示级，留痕待复核。
                _cls = text.rfind("\n", 0, m.start()) + 1
                _cln = text.find("\n", m.end())
                _cur = text[_cls: len(text) if _cln == -1 else _cln]
                if _cur.lstrip().startswith("|") or _cur.lstrip().startswith("-") \
                        or "出处" in _cur:
                    locator_only.append(key)
                else:
                    unquoted.append({"ref": f"@{key}",
                                     "note": "正文引用了时间戳但附近无逐字引语（概述式引用）"})
                continue
            ts_checked += 1
            # 语料侧取**该时间戳段落 + 后续邻接段落**（字幕常把一句话切进多个 cue，
            # 卡片引的是合并后的整句）。此前只取单 cue，导致跨 cue 引语一律核不到
            # （`a place that all of you procrastinators...` 正是如此）。
            hit = next((c for c in cands if _loose_match(c, body)), None)
            #邻接窗口**只在候选自身带省略/跨句痕迹时**才开（缺陷 #38，
            # 由 t_verify_quotes_timestamp 的 D 用例抓出：曾把
            # "The second sentence, which is different." 判为核到 00:00:20.00，
            # 而它其实是 00:00:05.50 的内容——**串到隔壁 cue**正是这条测试要防的）。
            # 判据：候选里含省略号痕迹，或单 cue 里只命中了候选的前半段。
            # 完整单句候选绝不允许跨 cue 匹配。
            if hit is None and _ts_next:
                _need_adj = any(_looks_truncated(c, body) for c in cands)
                if _need_adj:
                    _win = " ".join([body] + [ts_index.get(k2, "")
                                              for k2 in _ts_next.get(key, [])])
                    hit = next((c for c in cands if _loose_match(c, _win)), None)
            if hit:
                ts_verified.append({"ref": key, "quote": hit})
            else:
                ts_unverified.append({"ref": key, "quote": cands[0]})
        for u in ts_unverified:
            unverified.append({"ref": f"@{u['ref']}", "quote": u["quote"]})
        verified.extend({"ref": f"@{v['ref']}", "quote": v["quote"]} for v in ts_verified)

    return {
        "schema": "rulai-distill/quote-verification@1",
        # 引用总数必须能**加总还原**，否则报告会自相矛盾（评分员抓过：
        # "核验通过 9 条但 quotes_checked=0"）。恒等式：
        #   refs_total = entry_refs + timestamp_refs
        #   timestamp_refs = ts 引语核验数 + 未核 + locator_only 数
        # 任何一个引用都不允许"凭空消失"。
        "generated_at": now_iso(),
        "card": str(card), "corpus": str(corpus),
        "refs_total": len(set(refs)) + len(ts_refs),
        "refs_by_kind": {
            "entry_refs": len(set(refs)),
            "timestamp_refs": len(ts_refs),
            # 时间戳引语的三种归宿，逐项可加总核对
            "ts_quotes_checked": ts_checked,
            "ts_locator_only": len(locator_only),
            "ts_unquoted": len([u for u in unquoted if u["ref"].startswith("@")]),
        },
        "quotes_checked": checked + ts_checked,
        "verified": len(verified),
        "unverified": unverified,
        "unquoted_refs": unquoted,
        "locator_only_refs": sorted(set(locator_only)),
        "orphaned_refs": sorted(set(orphaned)),
        "verdict": "pass" if not unverified and not orphaned else "fail",
        "reconciliation": {
            "entry_refs_accounted": len(set(refs)) == checked + len(
                [u for u in unquoted if not u["ref"].startswith("@")]),
            "timestamp_refs_accounted": len(ts_refs) == ts_checked + len(locator_only) + len(
                [u for u in unquoted if u["ref"].startswith("@")]),
        },
        "note": ("locator_only_refs 是表格/披露表里的纯时间戳锚点，不承载引语，"
                 "不计入引语分母；unquoted_refs 是提示级：引用处没有逐字引语（概述式引用），不判失败"),
    }


# 逐字稿段落行：[HH:MM:SS.ss] 正文
_PARA_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2}[.,]\d+)\]\s*(.+)$", re.M)
# 明显是衔接/笑声/无实质内容的段落，不计入覆盖缺口
_FILLER_RE = re.compile(
    r"^\W*$|\(laughter\)|\(applause\)|\(sigh\)|\(music\)|^thank you|"
    r"^you know\b|^okay\b|^so\b\s*$|^and\b\s*$", re.I)


def audit_coverage(card: Path, corpus: Path, threshold: float = 0.60,
                   min_words: int = 8) -> dict:
    """**穷举语料，列出卡片没有覆盖的段落**（把"人工穷举"变成一条命令）。

    为什么需要它：第四轮 FIDELITY 评分暴露出——披露清单靠"按需补"永远补不完
    （漏项从 6 涨到 11），因为补的是**清单**而不是**全集**。
    本函数用字符 3-gram 覆盖率客观判定"这段内容在卡片里有没有出现过"，
    把漏项从主观劳动变成可复算的输出。

    覆盖率 = |段落 3-gram ∩ 卡片 3-gram| / |段落 3-gram|
    低于 threshold 视为未覆盖。min_words 以下的短段（衔接语、笑声）忽略。
    """
    card_text = _norm_frag(read_text(card))
    card_grams = ngrams(card_text)
    ctext = read_text(corpus)
    paras = [(m.group(1), m.group(2)) for m in _PARA_RE.finditer(ctext)]
    covered, uncovered, skipped = [], [], 0
    for ts, raw in paras:
        norm = _norm_frag(raw)
        if _FILLER_RE.match(norm.strip()) or len(norm.split()) < min_words:
            skipped += 1
            continue
        g = ngrams(norm)
        cov = (len(g & card_grams) / len(g)) if g else 0.0
        item = {"ts": ts, "coverage": round(cov, 3),
                "chars": len(norm), "text": norm[:220]}
        (covered if cov >= threshold else uncovered).append(item)
    uncovered.sort(key=lambda x: x["coverage"])
    all_cov = [i["coverage"] for i in covered] + [i["coverage"] for i in uncovered]
    all_cov.sort()
    dist = {
        "min": round(all_cov[0], 3) if all_cov else 0.0,
        "p25": round(all_cov[len(all_cov) // 4], 3) if all_cov else 0.0,
        "median": round(all_cov[len(all_cov) // 2], 3) if all_cov else 0.0,
        "p75": round(all_cov[3 * len(all_cov) // 4], 3) if all_cov else 0.0,
        "max": round(all_cov[-1], 3) if all_cov else 0.0,
    }
    # ── 阈值脆弱性自检（必须由工具算，不能靠人记得去看分布）────────────
    # 这是同一个错误第三次发生：默认阈值 0.30 → 虚假 100%；改 0.60 → 仍然虚假 100%
    # （min=0.61 紧贴阈值，改一个小数点就塌）。所以不能再靠"调一个默认值"兜：
    # 工具必须在给出结论的同时算出"这个结论离翻车有多远"。
    _all_items = [(i["coverage"]) for i in covered] + [i["coverage"] for i in uncovered]
    _min_cov = min(_all_items) if _all_items else 0.0
    _margin = round(_min_cov - threshold, 3)
    _FRAGILE_BOUND = 0.08
    _fragile = (len(uncovered) == 0 and _margin < _FRAGILE_BOUND) or _margin < 0.0

    def _count_at(th: float) -> dict:
        n_co = sum(1 for c in _all_items if c >= th)
        return {"threshold": round(th, 2), "covered": n_co,
                "uncovered": len(_all_items) - n_co,
                "coverage_rate": round(n_co / max(1, len(_all_items)), 3)}

    _sens = {round(t, 2): _count_at(t)
             for t in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)}
    _strict = _count_at(round(threshold + 0.10, 2))
    if _fragile:
        _headline = (f"当前阈值 {threshold} 下覆盖 {len(covered)}/{len(paras)} 段"
                     f"（{round(len(covered) / max(1, len(paras) - skipped), 3):.0%}），"
                     f"但最低覆盖段落 cov={_min_cov}，距阈值仅 {_margin}——"
                     f"**这个结论脆弱，不能只引用当前数字**。"
                     f"阈值提到 {_strict['threshold']} 会降到 {_strict['coverage_rate']:.0%}"
                     f"（{_strict['uncovered']} 段掉出）。")
    else:
        _headline = (f"阈值 {threshold} 下覆盖 {len(covered)}/{len(paras)} 段，"
                     f"最低 cov={_min_cov}，距阈值 {_margin}，结论稳定。")

    return {
        "schema": "rulai-distill/coverage-audit@2",
        "generated_at": now_iso(),
        "card": str(card), "corpus": str(corpus),
        "threshold": threshold,
        "paragraphs_total": len(paras),
        "substantive": len(paras) - skipped,
        "covered": len(covered),
        "uncovered": len(uncovered),
        "coverage_rate": round(len(covered) / max(1, len(paras) - skipped), 3),
        "uncovered_paragraphs": uncovered,
        "coverage_distribution": dist,
        # ↓ 新增：结论的稳健性元数据。任何报告引用 coverage_rate 时必须同时引用这两个字段。
        "threshold_fragile": _fragile,
        "threshold_margin": _margin,
        "threshold_sensitivity": _sens,
        "strict_reference": _strict,
        "headline": _headline,
        "threshold_note": ("阈值直接决定结论：中文卡片 + 英文语料时 3-gram 覆盖率天然偏高，"
                           "0.30 与 0.60 都曾给出虚假的『100% 覆盖』。"
                           "引用 coverage_rate 前必须先看 threshold_fragile；"
                           "为真时该数字只在当前阈值成立，必须改引 coverage_distribution 的区间。"),
    }


def token_metrics(root: Path, enc: str = "cl100k_base") -> dict:
    root = Path(root)
    if not root.exists():
        raise ToolError(f"路径不存在：{root}")
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix in (".md", ".template", ".json")]
    entries, discovery = [], 0
    for p in files:
        try:
            t = read_text(p)
        except ToolError:
            continue
        n = count_tokens(t, enc)
        entries.append({"file": str(p.relative_to(root)), "tokens": n, "chars": len(t)})
        if p.name == "SKILL.md" and t.startswith("---"):
            end = t.find("\n---", 3)
            discovery += count_tokens(t[3:end], enc)
    totals = [e["tokens"] for e in entries]
    skill_files = [e for e in entries if e["file"].endswith("SKILL.md")]
    return {
        "schema": "rulai-distill/token-metrics@1",
        "generated_at": now_iso(),
        "root": str(root),
        "counter": token_source(),
        "file_count": len(entries),
        "discovery_payload": discovery,
        "corpus_total": sum(totals),
        "skill_md": {
            "count": len(skill_files),
            "min": min((e["tokens"] for e in skill_files), default=0),
            "median": int(statistics.median([e["tokens"] for e in skill_files])) if skill_files else 0,
            "max": max((e["tokens"] for e in skill_files), default=0),
            "total": sum(e["tokens"] for e in skill_files),
        },
        "top10": sorted(entries, key=lambda e: -e["tokens"])[:10],
    }


# --------------------------------------------------------------------------
# benchmark
# --------------------------------------------------------------------------
def bench(cmd_runner, rounds: int = 3) -> dict:
    """对一个可调用对象重复计时，报告 min/median/max。"""
    times = []
    for i in range(rounds):
        t0 = time.perf_counter()
        cmd_runner()
        times.append(time.perf_counter() - t0)
    return {"rounds": rounds, "min": round(min(times), 3),
            "median": round(statistics.median(times), 3), "max": round(max(times), 3),
            "generated_at": now_iso()}


def write_report(path: Path, data: dict) -> Path:
    write_json(path, data)
    return path
