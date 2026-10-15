#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cross_model_recheck.py — 跨模型（异族）独立复评脚本（P1#2 落地）

用 DeepSeek（异族模型家族，相对本项目主用族）对 rulai-distill 的人物卡做一次
独立复评，产出 docs/independent-recheck/<card>/<model>/review.json，
再由 scripts/tdlib/independent_recheck.py 聚合并标记「组织独立」。

为什么是「跨模型」：本项目出厂质检是结构独立（答题/评分双 Agent，但同属一个模型
家族、由本项目调度）。同族互评可能偏宽松。DeepSeek 是不同模型家族，按同一套方法
重答+重评即可消除该残余风险。注意：同平台换档位（default→reasoning/lite）不计入
异族证实，必须接真外部族——DeepSeek 即属于此。

流程（三步，全部由 DeepSeek 完成，但分角色以保留「答题 ≠ 评分」纪律）：
  1. 出题：基于底稿（SKILL.md 含 src-XX §N 引语）自出 8 题
           （立场/结论一致性 3、风格辨识 1、边缘诚实 1、来源透明 1、结构完整 1、综合 1）
           题目不得泄露答案、不得直接复述卡片已有示例。
  2. 答题：以卡片第一人称作答 8 题，关键结论挂 src-XX §N；素材未覆盖的题先声明未覆盖。
  3. 盲评：不知答题者身份，按五维百分制盲评，输出 review.json 字段。

用法：
  export DEEPSEEK_API_KEY=sk-...          # 或脚本自动从 ~/.hermes/.env 读取
  export DEEPSEEK_BASE_URL=https://api.deepseek.com   # 可选，默认即此
  python3 scripts/cross_model_recheck.py --card zhengbanqiao-chidu
  python3 scripts/cross_model_recheck.py --all
  python3 scripts/cross_model_recheck.py --card wangyangming-xinxue --model deepseek-v4-flash
  python3 scripts/cross_model_recheck.py --all --no-aggregate   # 只生成 review.json 不聚合

依赖：仅 Python 标准库（urllib + json），无需 pip install。

网络：调用 api.deepseek.com。若报 ECONNREFUSED / 代理相关错误，是代理问题——
      在继承了你修好的 ~/.zshrc 代理的普通终端里跑即可，或显式 export NO_PROXY=api.deepseek.com。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[1]  # 项目根
PERSONA_SKILLS = ROOT / "examples" / "persona-bundle" / "skills"

# 人物卡 slug -> 第一人称名称（供出题/答题提示词使用）
PERSONA_NAMES = {
    "zhengbanqiao-chidu": "郑板桥",
    "wangyangming-xinxue": "王阳明",
    "zengguofan-xiushen": "曾国藩",
}

DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_BASE_URL = "https://api.deepseek.com"
HERMES_ENV = Path.home() / ".hermes" / ".env"

RUBRIC_TEXT = (
    "五维百分制：立场/结论一致性 30 ｜ 风格辨识度 20 ｜ 边缘诚实度 20 ｜ "
    "来源透明度 15 ｜ 结构完整度 15；等级 A≥85 / B 70-84 / C 55-69 / D<55。"
    "边缘诚实度若发现编造（把底稿没讲过的内容当事实、或第一人称编造未标示例）记为 fabrication。"
)

RETRY = 3


# --------------------------------------------------------------------------- #
# API key / base url
# --------------------------------------------------------------------------- #

def load_credentials() -> tuple[str, str]:
    """优先读环境变量，回退解析 ~/.hermes/.env。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base = os.environ.get("DEEPSEEK_BASE_URL", "").strip() or DEFAULT_BASE_URL
    if key:
        return key, base
    if HERMES_ENV.exists():
        text = HERMES_ENV.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("DEEPSEEK_BASE_URL="):
                base = line.split("=", 1)[1].strip().strip('"').strip("'") or base
    if not key:
        raise SystemExit(
            "✗ 未找到 DeepSeek API key。请 export DEEPSEEK_API_KEY=sk-... "
            "或在 ~/.hermes/.env 中配置 DEEPSEEK_API_KEY。"
        )
    return key, base


# --------------------------------------------------------------------------- #
# DeepSeek 调用（OpenAI 兼容）
# --------------------------------------------------------------------------- #

def call_deepseek(api_key: str, base_url: str, model: str,
                  system: str, user: str, temperature: float = 0.3,
                  max_tokens: int = 4096) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    last_err = None
    for attempt in range(1, RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            reason = body["choices"][0].get("finish_reason", "?")
            if not content or not content.strip():
                raise ValueError(f"返回内容为空（finish_reason={reason}）")
            if reason == "length":
                print(f"    · 警告：输出被 max_tokens 截断（finish_reason=length）",
                      file=sys.stderr)
            return content
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                json.JSONDecodeError, TimeoutError, ValueError) as e:
            last_err = e
            print(f"    · API 调用失败（第 {attempt}/{RETRY} 次）：{e}", file=sys.stderr)
    raise SystemExit(f"✗ DeepSeek 调用最终失败：{last_err}")


# --------------------------------------------------------------------------- #
# JSON 提取
# --------------------------------------------------------------------------- #

def _balanced_slice(text: str, open_ch: str, close_ch: str) -> str | None:
    """返回第一个括号平衡的 open..close 片段（尊重字符串与转义）；未闭合返回 None。

    比 `text[find(open):rfind(close)]` 稳：后者遇到前后夹带的散文/多个 JSON 会切错。
    """
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None  # 未闭合（多半被 max_tokens 截断）


def extract_json(text: str, prefer: str | None = None):
    """从模型返回里抠出第一个合法 JSON（对象或数组），容忍代码围栏与前后散文。

    prefer="list"/"dict" 指定优先尝试的形态（本脚本出题/答题返回数组、盲评返回对象）；
    缺省按 [] 与 {} 谁先出现谁优先。
    """
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    # 1) 直接解析（最干净的情况）
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) 指定优先形态时只认该形态（否则截断数组会被误当成内层对象返回）
    if prefer == "list":
        order = [("[", "]")]
    elif prefer == "dict":
        order = [("{", "}")]
    else:
        ai, oi = text.find("["), text.find("{")
        order = ([("[", "]"), ("{", "}")]
                 if (ai != -1 and (oi == -1 or ai < oi))
                 else [("{", "}"), ("[", "]")])
    for o, c in order:
        frag = _balanced_slice(text, o, c)
        if frag:
            try:
                return json.loads(frag)
            except json.JSONDecodeError:
                pass
    # 2b) prefer=list 兜底：模型把数组包进对象（如 {"answers":[...]}）
    if prefer == "list":
        frag = _balanced_slice(text, "{", "}")
        obj = None
        if frag:
            try:
                obj = json.loads(frag)
            except json.JSONDecodeError:
                obj = None
        inner = [v for v in obj.values() if isinstance(v, list)] if isinstance(obj, dict) else []
        if len(inner) == 1:
            return inner[0]
    # 3) 失败：原文落盘便于诊断
    dbg = Path("/tmp/cmr_bad_response.txt")
    try:
        dbg.write_text(text, encoding="utf-8")
    except OSError:
        pass
    raise SystemExit(f"✗ 无法从模型返回解析 JSON（原文已存 {dbg}）：\n{text[:500]}")


def _ask_json(system: str, user: str, temperature: float, max_tokens: int,
              kind: str, expect_n: int | None = None, label: str = "调用"):
    """调用 → 解析 → 校验完整性；模型偶发截断/夹带散文时自动重试。

    kind="list" 期望非空数组（可要求 ≥expect_n 项）；kind="dict" 期望非空对象。
    这样把「一次返回不合格」从致命错误降级为可重试的抖动。
    """
    last = None
    for attempt in range(1, RETRY + 1):
        raw = call_deepseek(_KEY, _BASE, _MODEL, system, user, temperature, max_tokens)
        try:
            out = extract_json(raw, prefer=kind)
        except SystemExit as e:
            last = str(e).splitlines()[0]
            print(f"    · {label} 解析失败（第 {attempt}/{RETRY} 次），重试…", file=sys.stderr)
            continue
        if kind == "list":
            if not isinstance(out, list) or not out:
                last = "返回非数组或为空"
            elif expect_n is not None and len(out) < expect_n:
                last = f"仅 {len(out)}/{expect_n} 项（疑似截断）"
            else:
                return out
        else:
            if not isinstance(out, dict) or not out:
                last = "返回非对象或为空"
            else:
                return out
        print(f"    · {label} 数据不完整（第 {attempt}/{RETRY} 次）：{last}，重试…",
              file=sys.stderr)
    raise SystemExit(f"✗ {label} 最终失败：{last}")


# --------------------------------------------------------------------------- #
# 三步提示词
# --------------------------------------------------------------------------- #

def step_generate_questions(name: str, skill_md: str) -> list[dict]:
    system = (
        f"你是独立评测出题者（模型家族与 rulai-distill 不同）。你将基于一份人物卡底稿，"
        f"为该人物「{name}」设计评测题。不得参考任何外部已有题库，只依据下方底稿。"
    )
    user = (
        f"底稿（含 src-XX §N 引语标注）如下：\n\n----\n{skill_md}\n----\n\n"
        f"请基于底稿自出 8 道评测题，覆盖：立场/结论一致性 3 题、风格辨识度 1 题"
        f"（盲读判断，不给答案）、边缘诚实度 1 题（底稿没讲过的问题，用于检测编造）、"
        f"来源透明度 1 题、结构完整度 1 题、综合 1 题。题目不得泄露答案、不得直接复述"
        f"底稿已有示例。每题只用一句话表述，不要解释、不要额外字段。\n\n"
        f"严格只输出 JSON 数组，不要输出数组之外的任何文字，每项："
        f'{{"id": <1-8>, "dimension": "<维度名>", "question": "<题目>"}}。'
    )
    return _ask_json(system, user, 0.5, 8192, "list", expect_n=8, label="出题")


def step_answer(name: str, skill_md: str, questions: list[dict]) -> list[dict]:
    system = (
        f"你是「{name}」本人（第一人称）。请仅凭下方底稿中的立场与引语作答，"
        f"不得引入底稿之外的主张；引用底稿原话时保留原文并标注（src-XX §N）。"
    )
    q_text = "\n".join(f"{q['id']}. [{q['dimension']}] {q['question']}" for q in questions)
    user = (
        f"底稿如下：\n\n----\n{skill_md}\n----\n\n"
        f"请以下列题目要求，以「{name}」第一人称逐题作答（共 8 题）：\n\n{q_text}\n\n"
        f"要求：关键结论必须挂（src-XX §N）；若某题底稿未覆盖，先声明「素材未覆盖」，"
        f"再区分「基于已知信念的推断（标'推断'）」与「素材无载、只能存疑」。"
        f"每题作答控制在 150 字以内。\n\n"
        f"严格只输出 JSON 数组，不要输出数组之外的任何文字，每项："
        f'{{"id": <题号>, "answer": "<作答内容>"}}。'
    )
    return _ask_json(system, user, 0.7, 12000, "list",
                     expect_n=len(questions), label="答题")


def step_grade(name: str, skill_md: str, questions: list[dict], answers: list[dict]) -> dict:
    system = (
        f"你是盲态评分者（不知道答题者身份，不被提示正在测哪个维度）。"
        f"依据底稿判断答案是否编造、是否与底稿立场一致。{RUBRIC_TEXT}"
    )
    q_map = {q["id"]: q for q in questions}
    paired = []
    for a in answers:
        q = q_map.get(a["id"], {})
        paired.append(f"【题 {a['id']} · {q.get('dimension','?')}】\n问：{q.get('question','?')}\n答：{a.get('answer','')}")
    paired_text = "\n\n".join(paired)
    user = (
        f"底稿（用于判定编造/一致性）如下：\n\n----\n{skill_md}\n----\n\n"
        f"以下是 8 题的「题目 + 答案」（你不知答题者是谁）：\n\n{paired_text}\n\n"
        f"请逐题给出 verdict：consistent（与底稿一致）/ inconsistent（偏离底稿立场）/ "
        f"fabrication（编造底稿没有的内容或第一人称未标示例）。\n"
        f"并给出整体 fidelity_grade_reconfirmed（A/B/C/D/none）与 fabrication_flagged（bool）。\n\n"
        f"以 JSON 返回：\n"
        f'{{"answers_rechecked": [{{"id":<题号>,"verdict":"<consistent|inconsistent|fabrication>","notes":"<可选>"}}],'
        f'"fidelity_grade_reconfirmed": "<A|B|C|D|none>", "fabrication_flagged": <true|false>}}'
    )
    return _ask_json(system, user, 0.2, 4096, "dict", label="盲评")


# --------------------------------------------------------------------------- #
# 单卡编排
# --------------------------------------------------------------------------- #

_KEY = ""
_BASE = ""
_MODEL = ""


def run_card(slug: str, model: str, aggregate: bool) -> Path:
    global _MODEL
    _MODEL = model
    if slug not in PERSONA_NAMES:
        raise SystemExit(f"✗ 未知人物卡 slug：{slug}（已知：{', '.join(PERSONA_NAMES)}）")
    name = PERSONA_NAMES[slug]
    skill_path = PERSONA_SKILLS / slug / "SKILL.md"
    if not skill_path.exists():
        raise SystemExit(f"✗ 找不到卡片：{skill_path}")
    skill_md = skill_path.read_text(encoding="utf-8")

    print(f"\n=== 卡片 {slug}（{name}）· 模型 {model} ===")
    print("  1/3 出题…")
    questions = step_generate_questions(name, skill_md)
    print(f"     出 {len(questions)} 题")
    print("  2/3 答题…")
    answers = step_answer(name, skill_md, questions)
    print(f"     答 {len(answers)} 题")
    print("  3/3 盲评…")
    graded = step_grade(name, skill_md, questions, answers)

    review = {
        "card": slug,
        "reviewer_type": "cross_model",
        "model_or_reviewer": model,
        "date": date.today().isoformat(),
        "answers_rechecked": graded.get("answers_rechecked", []),
        "fidelity_grade_reconfirmed": graded.get("fidelity_grade_reconfirmed", "none"),
        "fabrication_flagged": bool(graded.get("fabrication_flagged", False)),
        "independence_note": (
            f"使用 DeepSeek({model}) 独立重答+重评，与 rulai-distill 同族无关；"
            f"8 题由该异族模型基于底稿自出，非复用卡内题库（缓解 #82 判别力缺陷）。"
        ),
    }

    out_dir = ROOT / "docs" / "independent-recheck" / slug / model
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "review.json"
    out_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"     → 写入 {out_path}")
    print(f"     等级重申：{review['fidelity_grade_reconfirmed']}｜编造标记：{review['fabrication_flagged']}")
    return out_path


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="跨模型（DeepSeek）独立复评脚本")
    ap.add_argument("--card", help="单张人物卡 slug，如 zhengbanqiao-chidu")
    ap.add_argument("--all", action="store_true", help="对三张人物卡全部跑")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"DeepSeek 模型（默认 {DEFAULT_MODEL}）")
    ap.add_argument("--no-aggregate", action="store_true", help="只生成 review.json，不跑聚合器")
    args = ap.parse_args(argv)

    if not args.card and not args.all:
        ap.error("必须指定 --card <slug> 或 --all")

    global _KEY, _BASE
    _KEY, _BASE = load_credentials()
    print(f"· 已载入 DeepSeek 凭证（base={_BASE}）")

    slugs = list(PERSONA_NAMES) if args.all else [args.card]
    written = []
    for slug in slugs:
        try:
            written.append(run_card(slug, args.model, not args.no_aggregate))
        except SystemExit as e:
            print(f"  ⚠ 跳过 {slug}：{e}", file=sys.stderr)

    if written and not args.no_aggregate:
        print("\n--- 聚合 ORG-INDEPENDENCE-LEDGER ---")
        agg = ROOT / "scripts" / "tdlib" / "independent_recheck.py"
        # 不用 os.system：与 `scripts/td.py` 设计原则 3「零动态执行」保持一致。
        # 列表参数不经 shell；agg 是仓内固定路径、用户不可注入。
        subprocess.run([sys.executable, str(agg)], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
