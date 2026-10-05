#!/usr/bin/env python3
"""run_output_evals.py — 输出评测的确定性环节（Phase 3，路线 C）。

  prepare  为每条 output case 生成 old/new/without 三个匿名任务包（盲测：包名随机化标签，
           映射表单独存放，不给评审者）
  score    对记录的输出跑机械断言（文本、文件、JSON 字段/精确值/数值容差），
           机械断言先于 LLM judge；盲评分歧样本留给人工复核

outputs 目录约定: <outputs>/<case_id>/<variant-label>/output.md；产物保存在该变体目录。
兼容旧的 <case_id>/<variant-label>.md，但 file_exists 仍只读对应变体目录，避免产物串用。
退出码: 0 全部通过；1 完成但有断言失败；2 输入无效或输出不完整。

用法:
  python3 scripts/run_output_evals.py prepare <suite.json> --out <dir> [--variants old_skill,new_skill,without_skill]
  python3 scripts/run_output_evals.py score   <suite.json> --outputs <dir> --mapping <mapping.json> --out <report.md>
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cangjie_common import dump_json, load_json  # noqa: E402


def safe_name(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value) is not None


def artifact_path(base: Path, value: str) -> Path:
    parts = value.split("/")
    if not value or "\\" in value or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"产物路径必须是目录内的相对文件路径: {value!r}")
    path = base / value
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError(f"产物路径越界: {value!r}")
    return path


def finite_number(value) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_assertion(a: dict) -> None:
    if not isinstance(a, dict) or not isinstance(a.get("value"), str):
        raise ValueError("断言必须包含字符串 value")
    kind = a.get("kind")
    if kind not in {"contains", "not_contains", "regex", "file_exists", "json_path", "json_equals", "json_number"}:
        raise ValueError(f"未知断言类型: {kind}")
    if kind == "regex":
        try:
            re.compile(a["value"])
        except re.error as exc:
            raise ValueError(f"无效正则: {a['value']}") from exc
    if kind == "file_exists":
        artifact_path(Path.cwd(), a["value"])
    if kind.startswith("json_") and not re.fullmatch(r"\$(?:\.[^.\s]+)*", a["value"]):
        raise ValueError("JSON 路径使用 $ 或 $.field.subfield（数组下标使用 .0）")
    if kind in {"json_equals", "json_number"} and "expected" not in a:
        raise ValueError(f"{kind} 缺少 expected")
    if kind == "json_equals":
        json.dumps(a["expected"], allow_nan=False)
    if kind == "json_number":
        if not finite_number(a["expected"]):
            raise ValueError("json_number.expected 必须是有限数值，不能是布尔值")
        for key in ("abs_tol", "rel_tol"):
            if not finite_number(a.get(key, 0)) or a.get(key, 0) < 0:
                raise ValueError(f"{key} 必须为有限非负数")


def validate_suite(suite: dict) -> list[dict]:
    if not isinstance(suite, dict) or not isinstance(suite.get("target"), str):
        raise ValueError("suite 缺少 target")
    cases = suite.get("output_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("output_cases 不能为空")
    ids = set()
    for c in cases:
        if not isinstance(c, dict) or not safe_name(c.get("case_id")):
            raise ValueError("case_id 必须是安全的字母/数字/下划线/连字符标识")
        if c["case_id"] in ids:
            raise ValueError(f"重复 case_id: {c['case_id']}")
        ids.add(c["case_id"])
        if not isinstance(c.get("prompt"), str) or not c["prompt"].strip():
            raise ValueError(f"{c['case_id']}: prompt 不能为空")
        if not isinstance(c.get("assertions"), list) or not c["assertions"]:
            raise ValueError(f"{c['case_id']}: assertions 不能为空")
        for a in c["assertions"]:
            validate_assertion(a)
    return cases


def validate_mapping(cases: list[dict], mapping: dict) -> set[str]:
    ids = {c["case_id"] for c in cases}
    if not isinstance(mapping, dict) or set(mapping) != ids:
        raise ValueError("mapping 必须完整且恰好覆盖 output_cases，不能遗漏或多出 case")
    variants = None
    for cid, case_map in mapping.items():
        if not isinstance(case_map, dict) or not case_map or not all(safe_name(x) for x in case_map):
            raise ValueError(f"{cid}: mapping 为空或含无效标签")
        if not all(safe_name(x) for x in case_map.values()):
            raise ValueError(f"{cid}: 无效变体名")
        current = set(case_map.values())
        if len(current) != len(case_map):
            raise ValueError(f"{cid}: 同一变体不能重复映射")
        if variants is not None and current != variants:
            raise ValueError(f"{cid}: 各 case 的变体集合必须一致")
        variants = current
    return variants


def json_at(text: str, path: str):
    # 优先完整 JSON，其次单个 fenced JSON 块；不从自然语言中猜测多个对象哪一个是答案。
    blocks = re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    payload = blocks[0] if len(blocks) == 1 else text.strip()
    try:
        data = json.loads(payload)
    except ValueError:
        # 兼容旧回答“说明文字 + 一个 JSON 对象”。多个对象时拒绝猜测哪个是最终答案。
        if blocks or payload.startswith(("{", "[")):
            raise  # 结构化输出损坏时，不从其内部捞一个恰好正确的子对象
        decoder = json.JSONDecoder()
        objects = []
        pos = 0
        while pos < len(payload):
            match = re.search(r"[\[{]", payload[pos:])
            if not match:
                break
            start = pos + match.start()
            obj, length = decoder.raw_decode(payload[start:])
            objects.append(obj)
            pos = start + length
        if len(objects) != 1:
            raise ValueError("回答须有且仅有一个 JSON 结果")
        data = objects[0]
    for part in path.split(".")[1:]:
        if isinstance(data, list) and part.isdigit():
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data[part]
        else:
            raise KeyError(part)
    return data


def check_assertion(a: dict, text: str, base: Path) -> bool:
    validate_assertion(a)
    kind, value = a["kind"], a["value"]
    if kind == "contains":
        return value in text
    if kind == "not_contains":
        return value not in text
    if kind == "regex":
        return re.search(value, text) is not None
    if kind == "file_exists":
        return artifact_path(base, value).is_file()
    if kind in {"json_path", "json_equals", "json_number"}:
        try:
            actual = json_at(text, value)
        except (ValueError, KeyError, IndexError, TypeError):
            return False
        if kind == "json_path":
            return True  # 保留旧存在性语义，数值/单位正确性必须另外断言
        if kind == "json_number":
            return finite_number(actual) and math.isclose(
                actual, a["expected"], abs_tol=a.get("abs_tol", 0), rel_tol=a.get("rel_tol", 0))
        try:
            return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
                a["expected"], sort_keys=True, allow_nan=False)
        except ValueError:
            return False
    raise ValueError(f"未知断言类型: {kind}")


def cmd_prepare(suite_path: Path, out_dir: Path, variants: list[str]) -> int:
    suite = load_json(suite_path)
    cases = validate_suite(suite)
    if not variants or len(set(variants)) != len(variants) or not all(safe_name(v) for v in variants):
        raise ValueError("variants 必须是非空、唯一的安全标识")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError("prepare 需要空的新目录，避免旧输出污染新一轮评测")
    rng = random.Random(suite.get("split_seed", 42))
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, dict[str, str]] = {}
    for c in cases:
        labels = [f"v{chr(65 + i)}" for i in range(len(variants))]
        rng.shuffle(labels)
        mapping[c["case_id"]] = dict(zip(labels, variants))
        case_dir = out_dir / c["case_id"]
        case_dir.mkdir(exist_ok=True)
        for label in labels:
            variant_dir = case_dir / label
            variant_dir.mkdir(exist_ok=True)
            dump_json(variant_dir / "task.json", {
                "case_id": c["case_id"], "variant_label": label, "prompt": c["prompt"],
                "input_files": c.get("input_files", []),
                "instruction": "按 prompt 实际完成任务，最终答案写同目录 output.md，其他交付物也放在本目录。不要读取相邻变体、映射表或预期答案。",
            })
    dump_json(out_dir / "mapping.json", mapping)
    print(f"已生成 {len(mapping)} 条 output 任务（每条 {len(variants)} 个匿名变体）→ {out_dir}\n"
          f"映射表 {out_dir / 'mapping.json'} 不要给评审 sub-agent。")
    return 0


def cmd_score(suite_path: Path, outputs: Path, mapping_path: Path, out_path: Path) -> int:
    suite = load_json(suite_path)
    mapping = load_json(mapping_path)
    cases = validate_suite(suite)
    variants = validate_mapping(cases, mapping)
    lines = [f"# 输出评测机械断言判分 — {suite['target']}", ""]
    totals: dict[str, list[int]] = {v: [] for v in variants}
    completed = {v: 0 for v in variants}
    incomplete = False
    for c in cases:
        case_map = mapping[c["case_id"]]
        lines.append(f"## {c['case_id']}\n")
        lines.append("| 变体 | 断言通过 | 明细 |")
        lines.append("|---|---|---|")
        for label, variant in sorted(case_map.items()):
            base = outputs / c["case_id"] / label
            f = base / "output.md"
            if not f.is_file():
                f = outputs / c["case_id"] / f"{label}.md"
            if not f.is_file():
                lines.append(f"| {variant} | — | 输出缺失: {f.name} |")
                totals[variant].append(0)
                incomplete = True
                continue
            text = f.read_text(encoding="utf-8")
            completed[variant] += 1
            results = [(a, check_assertion(a, text, base)) for a in c["assertions"]]
            passed = sum(1 for _, ok in results if ok)
            detail = "; ".join(
                f"{'✓' if ok else '✗'}{a['kind']}:{a['value'][:24]}"
                + (f" expected={json.dumps(a['expected'], ensure_ascii=False)}" if "expected" in a else "")
                for a, ok in results)
            lines.append(f"| {variant} | {passed}/{len(results)} | {detail} |")
            totals.setdefault(variant, []).append(int(passed == len(results)))
        lines.append("")
    lines.append("## 汇总（全部断言通过的 case 比例）\n")
    for variant, arr in sorted(totals.items()):
        lines.append(f"- {variant}: {sum(arr)}/{len(arr)}；完成 {completed[variant]}/{len(cases)}（缺失计入分母）")
    lines.append(f"\n状态：{'INCOMPLETE（不可声明完整通过）' if incomplete else 'COMPLETE'}")
    lines.append("\n> 机械断言先于 LLM judge；A/B 盲评与分歧样本人工复核另行进行，此处不自动宣布非劣。")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 2 if incomplete else (0 if all(all(arr) for arr in totals.values()) else 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("suite")
    p.add_argument("--out", required=True)
    p.add_argument("--variants", default="old_skill,new_skill,without_skill")
    c = sub.add_parser("score")
    c.add_argument("suite")
    c.add_argument("--outputs", required=True)
    c.add_argument("--mapping", required=True)
    c.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        if args.mode == "prepare":
            return cmd_prepare(Path(args.suite), Path(args.out), args.variants.split(","))
        return cmd_score(Path(args.suite), Path(args.outputs), Path(args.mapping), Path(args.out))
    except (ValueError, OSError) as exc:
        print(f"评测未完成: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
