#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
td.py — rulai-distill 工具链（薄 CLI）

设计原则
  1. 薄 CLI：脚本只做**确定性文件操作**，语义提取与评分全部交给 Agent。
  2. 零网络：全包不发起任何外部请求（字幕/调研/评测均离线；触发评测由 Agent 作答、脚本判分）。
  3. 零动态执行：无 eval / exec / subprocess(shell=True)。
  4. 零依赖可跑：PyYAML / tiktoken 缺失时自动降级，不阻断。
  5. 失败可读：异常一律转成「❌ 人话 + 可执行下一步」，绝不抛裸 traceback。
  6. 写操作默认 dry-run：真正落盘要显式 --apply。

命令总览
  环境    doctor
  建包    init <dir>
  长内容  chunk <src> [--sidecar --max-chars --force] ｜ index <sidecar> [--grep] ｜ preview <sidecar>
  字幕    transcript <srt…> [--out --merge --offset --gap]
  调研    research init <dir> ｜ research merge <files…> --out <f>
  校验    validate <path>
  质检    gate <report> [--min A|B|C|D] [--scores 95,88]
         cross-review <95,88> [--threshold 10]   # 多评分 Agent 分差门禁（nuwa 第三铁律）
  决策    strategy <bundle> [--purpose --mode --trigger-ready]
  素材    overlap --new <新语料.md> --old <旧语料.md> [--n 8]   # 换素材重蒸馏前的零重叠证明
         anchor <card.md> --corpus <逐字稿.md…>            # 引语是否真在它声明的 §N 段内
  发布    compile <bundle> --out <dir> [--mode pack|single] ｜ snapshot <dir> ｜ rollback <dir> --to <id>
  评测    trigger build|record|score ｜ output-eval <card> ｜ count <path> ｜ bench <path>
  演进    diff <a> <b> ｜ impact <dir> <slug> ｜ repair <dir> ｜ patch <card> <patch.json> ｜ update <bundle> --out <dir>
  其他    prompt <src> [--mode entry|inline|cards] ｜ schema <name>
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tdlib import (anchor, chunking, contracts, evalkit, evolve, evals, fidelity as fid, fetch,
                   lintquotes, overlap, promptc, publish, research, strategy, transcript,
                   upstream, validate as vd)
from tdlib.util import (METHOD_DIR, SCHEMA_DIR, TEMPLATE_DIR, ToolError, VERSION,
                        die, head, info, ok, read_json, read_text, warn, write_json)

EXIT_OK, EXIT_FAIL = 0, 1


# --------------------------------------------------------------------------
# doctor / init
# --------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    print(f"td.py v{VERSION} · rulai-distill 环境自检\n")
    bad = 0
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        ok(f"Python {major}.{minor}.{sys.version_info[2]}（要求 ≥3.10）")
    else:
        warn(f"Python {major}.{minor} 过低，建议 ≥3.10")
        bad += 1
    for label, mod in (("PyYAML（严格 frontmatter 解析）", "yaml"),
                       ("tiktoken（精确 token 计量）", "tiktoken")):
        if importlib.util.find_spec(mod):
            ok(f"{label} 可用")
        else:
            warn(f"{label} 缺失 —— 已降级，功能不受阻")
            info(f"可选安装：python3 -m pip install {mod}")
    for label, d in (("methodology", METHOD_DIR), ("templates", TEMPLATE_DIR),
                     ("schemas", SCHEMA_DIR)):
        if d.is_dir() and any(d.iterdir()):
            ok(f"{label}/ 就绪（{len(list(d.glob('*')))} 个文件）")
        else:
            warn(f"{label}/ 缺失或为空 —— 安装不完整：{d}")
            bad += 1
    need = ["CAPABILITY.md.template", "PERSONA.md.template", "FIDELITY.md.template",
            "TEST-SUITE.md.template", "BOOK_OVERVIEW.md.template"]
    missing = [t for t in need if not (TEMPLATE_DIR / t).exists()]
    if missing:
        warn(f"缺少模板：{', '.join(missing)}")
        bad += 1
    else:
        ok("5 个核心模板齐全")
    head("能力矩阵（对齐三个来源技能）")
    for line in (
        "长内容分块 / 索引 / 缓存      ← cangjie build_chunks + build_index",
        "token 计量 / 输出形态决策    ← cangjie count_tokens + select_output_strategy",
        "原子发布 / 快照 / 回滚 / 手改检测 ← cangjie compile_pack + compile_single",
        "增量维护 diff/impact/repair/update/patch ← cangjie 五个演进脚本",
        "触发评测判分 / 输出体检 / 基准  ← cangjie run_trigger_evals + run_output_evals + benchmark",
        "字幕 SRT/VTT → 带时间戳逐字稿（离线）← nuwa srt_to_transcript",
        "六路调研骨架 + 合并去重 + 冲突标记 ← nuwa 六路 research + merge_research",
        "FIDELITY 双 Agent 质检 + 可执行门槛 ← nuwa fidelity-scorecard",
        "认知植入结构 + 显式步骤禁令   ← yeadon 认知植入 + quality_check",
        "单文件 prompt 编译            ← yeadon compile-prompt",
    ):
        info(line)
    print("\n" + ("🎉 可以开始蒸馏。" if bad == 0 else f"⚠️  有 {bad} 项需要处理，核心功能仍可离线使用。"))
    print("下一步：python3 scripts/td.py init my-bundle")
    return EXIT_OK if bad == 0 else EXIT_FAIL


def cmd_init(args) -> int:
    target = Path(args.dir).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        die(f"目录非空：{target}", "换个名字，或先清空")
    (target / "skills").mkdir(parents=True, exist_ok=True)
    (target / "fidelity").mkdir(parents=True, exist_ok=True)
    (target / "sources").mkdir(parents=True, exist_ok=True)

    write_json(target / "bundle.json", {
        "schema": "rulai-distill/bundle/v1",
        "version": "0.1.0",
        "source": {"material": "待填素材名", "material_type": "book", "author": "", "coverage": 100},
        "skills": [{"slug": "example-capability", "role": "router", "src": "skills/example-capability.md"}],
        "publish": {"allow_grade_below": "B"},
    })
    (target / "skills" / "example-capability.md").write_text("""---
name: example-capability
title: 示例能力卡
description: |
  示例：在 X 情境下用 Y 方法解决 Z。
  适用：<填 3-5 条>。不做：<填 2-3 条>。
source_material: 待填
source_locator: 第 X 章
capability_type: framework
promotion: router
---

# 示例能力卡

## R — Reading

> 「原文摘录」
> —— 书名 章节

## I — Interpretation

1. <前提 → 动作 → 结果>

## A1 — Past

**案例**：情境 / 应用 / 结果

## A2 — Future

**触发情境**：...
**语言信号**：「用户口语」
**邻近区分**：| 邻近能力 | 本卡 | 对方 |

## E — Execution

**Step 1 · 名字**
- 做什么：
- 完成标准：
- ⏸️ 检查点：

## B — Boundary

**不适用**：...
**失败模式**：| 症状 | 根因 | 纠正 |
""", encoding="utf-8")
    (target / "SOURCES.md").write_text(
        "---\ntitle: 素材清单\ndescription: 记录本次蒸馏用到的一手/二手素材与权重，非技能卡。\n---\n\n"
        "# 素材清单\n\n> 一手来源合计权重应 ≥0.7，否则 FIDELITY 维度 4 会扣分并在报告里显式降级。\n\n"
        "| 素材 | 类型 | 定位 | 一手 | 权重 |\n|---|---|---|---|---|\n| | | | | |\n",
        encoding="utf-8")
    made = research.scaffold(target / "references" / "research", args.person)
    ok(f"已生成 bundle 骨架：{target}")
    for line in ("bundle.json      ← 改 source / skills",
                 "skills/*.md      ← 能力卡，按 templates/CAPABILITY.md.template 写",
                 f"references/research/  ← 六路调研骨架 {len(made)} 个（书籍蒸馏可删）",
                 "SOURCES.md       ← 素材清单 + 一手来源占比",
                 "fidelity/        ← 可放 <slug>.json 形式的质检报告"):
        info(line)
    info("下一步：python3 scripts/td.py validate " + str(target))
    return EXIT_OK


# --------------------------------------------------------------------------
# 长内容
# --------------------------------------------------------------------------
def cmd_chunk(args) -> int:
    head(f"分块 · {args.src}")
    res = chunking.chunk_file(Path(args.src), Path(args.sidecar) if args.sidecar else None,
                              max_chars=args.max_chars, source_id=args.source_id,
                              force=args.force)
    avg = res["total_chars"] // max(1, res["chunk_count"])
    ok(f"{res['chunk_count']} 块 / {res['element_count']} elements / 平均 {avg} 字符")
    info(f"产物目录：{res['sidecar']}")
    info(f"最大块 {res['max_chunk_chars']} 字符（上限 {args.max_chars}）")
    info(f"下一步：td.py index {res['sidecar']} --grep <关键词>")
    return EXIT_OK


def cmd_index(args) -> int:
    sidecar = Path(args.sidecar)
    p = sidecar / "index.json"
    if not p.exists():
        die(f"未找到 index：{p}", f"先跑 `td.py chunk <src> --sidecar {sidecar}`")
    data = read_json(p)
    if not args.grep:
        ok(f"共 {data['chunk_count']} 块，总 {data['total_chars']} 字符")
        chunking.preview(sidecar, limit=args.limit)
        return EXIT_OK
    hits: list[str] = []

    def walk(node, path):
        for k, v in node.items():
            if k == "_chunks":
                if args.grep in " / ".join(path):
                    hits.extend(v)
            else:
                walk(v, path + [k])

    walk(data.get("headings", {}), [])
    # 2026-10-07（#49）：原来只按**标题**检索，正文里的词一个都搜不到——
    # 而 `chunk` 的输出恰恰提示「下一步：td.py index <sidecar> --grep <关键词>」，
    # **承诺了做不到**。这里补上正文匹配（大小写不敏感的子串）。
    chunks = {c["chunk_id"]: c for c in chunking.load_chunks(sidecar)}
    needle = args.grep.lower()
    hits.extend(cid for cid, c in chunks.items()
                if needle in c.get("text", "").lower())
    uniq = sorted(set(hits))
    ok(f"命中 {len(uniq)} 块（关键词：{args.grep}）")
    for cid in uniq[:args.limit]:
        c = chunks[cid]
        info(f"   {cid}  {c['chars']}c  {' / '.join(c['heading_path'])[:50]}")
    if len(uniq) > args.limit:
        info(f"   ...还有 {len(uniq) - args.limit} 块，用 --limit 调整")
    return EXIT_OK


def cmd_preview(args) -> int:
    chunking.preview(Path(args.sidecar), limit=args.limit)
    return EXIT_OK


def cmd_lexindex(args) -> int:
    head("词法索引 · SQLite FTS5 + 中文 bigram + 邻接块")
    if args.query:
        hits = chunking.query_lexindex(Path(args.db), args.query, limit=args.limit,
                                       neighbors=args.neighbors)
        if not hits:
            warn(f"未命中：{args.query}")
            info("中文检索按字符 bigram 索引；试更短的关键词，或 --neighbors 2 看上下文")
            return EXIT_OK
        for group in hits:
            hit = group[0]
            info(f"命中 {hit['chunk_id']}（seq {hit['seq']}）：{hit['snippet']}")
            for nb in group[1:]:
                hp = " / ".join(nb.get("heading_path") or []) or "(root)"
                info(f"   └ {nb['chunk_id']} seq {nb['seq']}  {hp[:44]}  {nb['snippet']}")
        return EXIT_OK
    res = chunking.build_lexindex(Path(args.chunks), Path(args.db) if args.db else None)
    ok(f"索引已建：{res['chunks']} 块 → {res['db']}")
    info("查询：td.py lexindex --db <db> --query \"主要矛盾\" --neighbors 1")
    return EXIT_OK


# --------------------------------------------------------------------------
# 字幕 / 调研
# --------------------------------------------------------------------------
def cmd_transcript(args) -> int:
    head("字幕 → 逐字稿（离线，不下载）")
    if len(args.inputs) > 1 or args.merge:
        out = Path(args.out) if args.out else Path(args.inputs[0]).with_suffix("")
        res = transcript.merge_transcripts([Path(p) for p in args.inputs], out,
                                           gap_ms=args.gap, max_chars=args.max_chars)
        ok(f"合并 {res['files']} 个文件 → {res['paragraphs']} 段")
        info(res["md"])
    else:
        res = transcript.build_transcript(
            Path(args.inputs[0]), Path(args.out) if args.out else None,
            gap_ms=args.gap, max_chars=args.max_chars, offset_ms=args.offset * 1000)
        ok(f"{res['cues']} cues → {res['paragraphs']} 段（去重丢弃 {res['dropped']}）")
        info(f"时长 {res['duration_ms'] // 1000}s")
        info(res["md"])
    info("下一步：td.py chunk <逐字稿.md> --source-id transcript")
    return EXIT_OK


def cmd_research(args) -> int:
    if args.research_cmd == "init":
        made = research.scaffold(Path(args.dir) / "references" / "research", args.person,
                                 args.overwrite)
        ok(f"六路调研骨架就绪：{len(made)} 个文件")
        for p in made:
            info("   " + p.name)
        return EXIT_OK
    res = research.merge_research([Path(p) for p in args.files], Path(args.out),
                                  threshold=args.threshold)
    ok(f"保留 {res['kept']} / {res['items_in']} 条（去重 {res['dropped']}），一手占比 {res['one_hand_ratio']:.0%}")
    if res["conflicts"]:
        warn(f"{len(res['conflicts'])} 处疑似冲突已标记，需人工判断")
    info(res["out"])
    if res["one_hand_ratio"] < 0.7:
        warn("一手来源占比 <70%：FIDELITY 维度 4 将扣分，且不得宣称「基于原始素材」")
    return EXIT_OK


# --------------------------------------------------------------------------
# 校验 / 质检 / 决策
# --------------------------------------------------------------------------
def cmd_validate(args) -> int:
    target = Path(args.path).expanduser()
    if not target.exists():
        die(f"路径不存在：{target}", "检查拼写，或先用 `td.py init` 生成骨架")
    problems, stats = vd.validate_path(target)
    print(f"🔍 校验：{target}\n")
    for lvl, src, msg in sorted(problems, key=lambda x: (x[0] != "error", x[1])):
        print(f"{'❌' if lvl == 'error' else '⚠️ '} [{src}] {msg}")
    print()
    if not problems:
        ok("无问题")
    print(f"统计：技能卡 {stats['cards']} / 文档 {stats['docs']} · error {stats['errors']} / warn {stats['warns']}")
    if stats["errors"]:
        die("存在阻断性问题，不允许发布。", f"修完再跑：python3 scripts/td.py validate {target}")
    return EXIT_OK


def cmd_gate(args) -> int:
    rep, notes = fid.apply_fallback_discount(fid.parse_report(Path(args.report).expanduser()))
    print(f"📋 FIDELITY gate · {Path(args.report).name}")
    print(f"   总分 {rep.get('total', 0)}/100   等级 {rep.get('grade', 'D')}   评测模式 {rep.get('eval_mode', 'unknown')}")
    if rep.get("dimensions"):
        info("分项：" + "  ".join(f"{k}={v}" for k, v in rep["dimensions"].items()))
    # 第三方测评 #2 / 报告 P1-2：解析严格化——漏维度 / 总分自相矛盾必须显式提示，
    # 不能让 gate 在"看起来完整"的报告上开绿灯。
    if rep.get("unparsed_dims"):
        warn(f"报告有 {len(rep['unparsed_dims'])} 个维度未解析（{', '.join(rep['unparsed_dims'])}）："
             "这些维度未被计入总分，请检查报告格式或手动补登，否则总分被低估")
    if rep.get("total_mismatch"):
        _decl, _sum = rep.get("declared_total"), rep.get("dimension_sum")
        warn(f"报告声明总分 {_decl} 与各维度之和 {_sum} 不一致（差 {abs(_decl - _sum)}）："
             "请以维度为准核查，勿直接信任声明总分")
    if rep.get("weakest_dimension"):
        info(f"最弱维度：{rep['weakest_dimension']}")
    for n in notes:
        warn(n)
    if rep.get("eval_mode") != "dual-agent":
        warn("非双 Agent 评测 —— 不得作为对外宣称的质量证据")
    # 复审 P0：gate **默认要求交叉复核记录**（≥2 个独立评分者），单评分 Agent 不构成质检
    # 结论。三种来源优先级：①CLI --scores ②报告内嵌（eval-kit check 产出的 graders +
    # cross_grader_gap）③都没有 → 默认拒绝，除非显式 --allow-single-scorer。
    cross = None
    _emb = _embedded_cross_review(rep)
    if getattr(args, "scores", ""):
        cross = _cross_review_from_arg(args.scores, args.cross_threshold, args.report)
        print(f"   交叉复核 {cross['scorers']} 个评分：{cross['scores']} → 分差 {cross['spread']:g}"
              f"（阈值 {cross['threshold']:g}）  判定 {cross['verdict']}")
    elif _emb:
        cross = _emb
        print(f"   交叉复核（报告内嵌）{cross['scorers']} 个评分 → 分差 {cross['spread']:g}"
              f"（阈值 {cross['threshold']:g}）  判定 {cross['verdict']}")
    elif getattr(args, "allow_single_scorer", False):
        warn("已按 --allow-single-scorer 放行：单评分 Agent 不构成独立质检，"
             "此结论不得作为对外质量证据")
    else:
        cross = _missing_cross_review()   # 具体理由在下面统一打印，避免重复
    if cross:
        if cross.get("threshold_fragile"):
            warn(f"分差 {cross.get('spread', 0):g} 贴着阈值 ±1 —— 结论脆弱，"
                 "换个评分员可能翻转，不许单独引用单点")
        for r in cross.get("reasons") or []:
            warn(r)
    passed, reasons = fid.gate(rep, args.min, allow_fallback=args.allow_fallback, cross=cross)
    if passed:
        ok(f"通过门槛 {args.min}（≥{fid.GRADES.get(args.min)}）")
        if args.allow_fallback and rep.get("eval_mode") != "dual-agent":
            warn("已按 --allow-fallback 放行：这是自测结果，不得对外宣称质量")
        return EXIT_OK
    die(f"未通过：{'；'.join(reasons)}",
        "退回阶段 2 重做能力卡，重点补：完成标准 / 失败模式 / 原始素材一手来源",
        "确需强发用 compile --force，但产物会被标记为未质检")


def _cross_review_from_arg(raw: str, threshold: float, subject: str | None = None) -> dict:
    """把 `--scores 95,88` 解析成 cross_review() 的输入（空段直接报错，不静默跳过）。"""
    parts = [x.strip() for x in str(raw).split(",")]
    if not any(parts):
        raise SystemExit(1)
    scores = []
    for p in parts:
        if not p:
            continue
        try:
            scores.append(float(p))
        except ValueError:
            die(f"评分不是数字：{p!r}", "用法：td.py cross-review 95,88（逗号分隔的百分制总分）")
    return fid.cross_review(scores, threshold=threshold, subject=subject)


def _embedded_cross_review(rep: dict) -> dict | None:
    """从报告里读**内嵌**的交叉复核信息。

    eval-kit check 产出的 FIDELITY JSON 带 `graders`（≥2）与 `cross_grader_gap`，
    于是 gate 无需再手填 `--scores` 就能识别"已交叉复核"。只给单个评分者或没有分差
    字段时返回 None（交给 CLI 默认策略处理，不假装已复核）。
    """
    graders = rep.get("graders") or []
    gap = rep.get("cross_grader_gap")
    if len(graders) < fid.CROSS_REVIEW_MIN_SCORERS or gap is None:
        return None
    spread = float(gap)
    verdict = "pass" if spread <= fid.CROSS_REVIEW_THRESHOLD else "needs_human_review"
    return {
        "schema": "rulai-distill/cross-review@1", "subject": rep.get("subject"),
        "scorers": len(graders), "spread": spread,
        "threshold": fid.CROSS_REVIEW_THRESHOLD, "min_scorers": fid.CROSS_REVIEW_MIN_SCORERS,
        "verdict": verdict, "needs_human_review": verdict != "pass",
        "threshold_fragile": abs(spread - fid.CROSS_REVIEW_THRESHOLD) <= 1,
        "reasons": ([f"报告内嵌分差 {spread:g} > 阈值 {fid.CROSS_REVIEW_THRESHOLD:g}："
                     "评分分歧过大，须人工复核"] if verdict != "pass" else []),
        "source": "报告内嵌 graders/cross_grader_gap（eval-kit check 产出）",
    }


def _missing_cross_review() -> dict:
    """gate 默认策略：没有交叉复核记录时构造一个"人数不足"判定 → 让 gate 拒绝放行。

    复审 P0：单评分 Agent 不构成质检结论。要放行须显式 --allow-single-scorer。
    语义与 fid.cross_review([]) 一致，但后者会抛错，所以这里手构造。
    """
    return {
        "schema": "rulai-distill/cross-review@1", "scorers": 0, "spread": 0.0,
        "threshold": fid.CROSS_REVIEW_THRESHOLD, "min_scorers": fid.CROSS_REVIEW_MIN_SCORERS,
        "verdict": "insufficient_scorers", "needs_human_review": True,
        "threshold_fragile": False,
        "reasons": ["缺交叉复核记录：gate 默认要求 ≥2 个独立评分者交叉复核"
                    "（用 --scores 提供，或让报告内嵌 graders）；"
                    "确要单评分放行请显式 --allow-single-scorer"],
    }


def cmd_eval_kit(args) -> int:
    if args.eval_cmd == "init":
        rep = evalkit.build_kit(Path(args.card).expanduser(), Path(args.out).expanduser())
        head("eval-kit · 生成独立评测套件")
        ok(f"{rep['files']} → {rep['out']}（{rep['questions']} 道种子题）")
        warn("题库是**种子**：source=human 的题（尤其 edge_honesty）必须人工补——"
             "那是唯一能抓出「拿素材权威包装编造内容」的一维")
        info(f"下一步：读 {rep['out']}/README.md，让独立答题 Agent 填 answers.json")
        return EXIT_OK
    # check
    res = evalkit.check(Path(args.answers).expanduser(),
                        [Path(p).expanduser() for p in args.scores],
                        subject=args.subject)
    head("eval-kit · 汇总独立评分并过交叉复核门禁")
    print(f"   答题者 {res['answerer']!r}   评分者 {res['graders']}"
          f"（{res.get('unique_graders', len(res['graders']))} 个唯一）")
    cr = res["cross"]
    print(f"   分差门禁 判定 {cr['verdict']}（分差 {cr.get('spread', 0):g}／阈值 "
          f"{cr.get('threshold', fid.CROSS_REVIEW_THRESHOLD):g}）")
    print(f"   合并维度：{'  '.join(f'{k}={v}' for k, v in res['report']['dimensions'].items())}")
    print(f"   总分 {res['report']['total']}/100   等级 {res['report']['grade']}")
    for e in res["errors"]:
        warn(e)
    for b in res["report"].get("blocking_issues") or []:
        warn(b)
    out = Path(args.out).expanduser() if args.out else Path(args.answers).with_name("FIDELITY.json")
    vres = contracts.validate_local("fidelity", res["report"])
    if not vres["ok"]:
        die("产出的 FIDELITY JSON 不符合本包 fidelity 契约（这是工具自己的错）",
            *vres["errors"][:6])
    if res["verdict"] != "pass":
        # 复审 G1：失败**不得**产出「普通产物」——否则它照样能被喂给 gate。
        # 写成 .rejected.json 供排查，并明确它不可用于放行。
        rej = out.with_name(out.stem + ".rejected" + out.suffix)
        write_json(rej, res["report"])
        die("eval-kit 判定不通过：不得据此宣称质量（已写出 " + rej.name + " 供排查）",
            "看上面的 errors / blocking_issues：答题或评分未填全、评分者 <2 个**不同**标识、"
            "评分者与答题者同名、或分差 >10（评分分歧过大须人工复核）",
            "修好回传文件后重跑 eval-kit check")
    write_json(out, res["report"])
    ok(f"已写出 FIDELITY 报告：{out}")
    info(f"下一步：td.py gate {out}")
    return EXIT_OK


def cmd_anchor(args) -> int:
    head("引语段号锚定 · 引语是否真在它自己声明的 §N 段里")
    info("与 verify-quotes 的区别：那个验「引语在语料里存在吗」，"
         "这个验「引语在它被引用的那一段里吗」")
    info(f"门槛：{args.n}-gram 命中率 ≥60%（与 verify-quotes 同口径，不制造两套标准）")
    corpora = anchor.load_corpora([Path(p).expanduser() for p in args.corpus])
    rep = anchor.verify_file(Path(args.card).expanduser(), corpora, n=args.n)
    print(f"   引语 {rep['quotes_seen']} 条：锚定命中 {rep['anchored_checked']}，"
          f"未标注段号 {rep['unanchored']}")
    print(f"   判定明细：{rep['tally']}")
    print(f"   对账：{rep['reconciliation']}")
    # #61：抽取层对账——候选引语 = 认出 + 噪声 + 因太短跳过的中文候选。
    # 旧实现把"太短的中文候选"混进 noise，看不出漏了什么；现在显式打印。
    _er = rep.get("extraction_reconciliation") or {}
    if _er:
        print(f"   抽取：候选 {_er.get('candidates')} = 认出 {_er.get('quotes_seen')}"
              f" + 噪声 {_er.get('noise_filtered')} + 中文太短跳过 {_er.get('skipped_cjk_short')}"
              f"（自检 {_er.get('balanced')}）")
    # 复审 5：短引语已升级为可核验——命中计入上方"锚定命中"，失配在此报警（不判失败）
    _sq = rep.get("short_quotes") or {}
    if _sq.get("verified"):
        info(f"   其中短引语（<8 汉字、逐字见于语料、同行带 §N）已纳入核验并命中 "
             f"{_sq['verified']} 条 —— 它们以前只被当'太短'跳过")
    if _sq.get("misplaced"):
        warn(f"短引语失配 {len(_sq['misplaced'])} 条：**不判失败**（短句在多引用行上归属含糊），"
             "但请人工核对段号")
        for f in _sq["misplaced"][:5]:
            info(f"      第 {f['line']} 行 声明 §{f['claimed_at']}，实际在 §{f['found_at']}"
                 f"（{f['verdict']}）「{f['quote'][:60]}」")
    if rep.get("skipped_cjk_short"):
        in_corp = rep.get("short_but_in_corpus") or []
        warn(f"{rep['skipped_cjk_short']} 条中文候选因「汉字数 <8」被判为术语/短语、未纳入裁决"
             f"（**不判失败**）；其中 {len(in_corp)} 条**逐字见于语料**"
             "（同行没有 §N 标注，所以无可锚定的段号）：")
        for s in in_corp[:8]:
            ic = s.get("in_corpus") or {}
            info(f"      第 {s['line']} 行「{s['quote']}」（语料 {ic.get('src')} §{ic.get('para')}）"
                 f"—— 建议补 §N 标注，补了就会自动纳入核验")
    if args.json_out:
        write_json(Path(args.json_out).expanduser(), rep)
        ok(f"已写出 {args.json_out}")
    # 复审 5：短引语失配的报警（见上）
    for f in rep["failures"]:
        cands = "、".join(f"§{c['para']}({c['rate']})" for c in f["candidates"]) or "无候选"
        decl = f.get("claimed_label") or f"§{f['claimed_at']}"
        found = f.get("found_label") or (f"§{f['found_at']}"
                                         if f.get("found_at") is not None else "—")
        warn(f"第 {f['line']} 行 声明 {decl}，实际在 {found}（{f['verdict']}）｜最可能段号：{cands}")
        warn(f"         「{f['quote'][:90]}」")
    if rep["verdict"] == "FAIL":
        die("判定 FAIL：存在挂错段号的引语",
            "按提示的实际段号改正，或若引语确实跨段则改写为可定位的形式；"
            "不要因为「引语本身存在」就放过——那正是本命令要防的")
    if rep["verdict"] == "UNVERIFIED":
        die("⚠️ 未核验（N/A）——不是通过：卡片里的引语均无可识别定位标记"
            "（§N / 【第N段】 / 篇-章号 / [时间戳]）",
            "本命令无从核验它们。请给引语补上定位标记，"
            "或改用 verify-quotes 只确认引语是否存在于语料")
    if rep["unanchored"]:
        warn(f"{rep['unanchored']} 条引语没有 §N 标注，属不可定位——本命令无法核验它们"
             "（**不判失败**，与 verify-quotes / lint-quotes「无出处即跳过」同口径），"
             "但需人工确认它们该挂哪一段")
        for u in rep.get("unanchored_quotes") or []:
            where = (f"（在语料 §{u['in_corpus_at']} 命中）"
                     if u.get("in_corpus_at") is not None else "（语料中也未命中）")
            info(f"      第 {u['line']} 行「{u['quote'][:70]}」{where}")
    # #56：卡片有标注却一条引语都没抽出来 = 核验器没干活，不是"没问题"。
    # 空集不得判 PASS（与 v1.3 的「空集假绿」同一纪律）。
    if rep.get("vacuous"):
        die(f"⚠️ 空集假绿：卡片有 {rep['citations_seen']} 处 §N/[时间戳] 标注，"
            f"却一条引语都没抽出来 —— 本命令**没有核验任何东西**",
            "这不是通过，是核验器没干活。请确认引语写在引号里"
            "（支持 \"…\"、「…」、“…”），且长度 ≥12 字符；"
            "或先用 verify-quotes 确认引语能被识别")
    tail = (f"；另有 {rep['unanchored']} 条无 §N 标注、不可定位（未核验）"
            if rep["unanchored"] else "")
    ok(f"判定 PASS：{rep['anchored_checked']} 条带段号标注的引语全部锚定在声明的段号内{tail}")
    return EXIT_OK


def cmd_corpus_anchor(args) -> int:
    head("书类语料规整 · 产出 anchor 可读的【第N段】形式")
    from tdlib.anchor import normalize_book_corpus
    src = Path(args.infile).expanduser()
    text = src.read_text(encoding="utf-8", errors="replace")
    max_chars = int(getattr(args, "max_chars", 0) or 0)
    out_text, stats = normalize_book_corpus(text, max_chars=max_chars)
    if args.out:
        dst = Path(args.out).expanduser()
        dst.write_text(out_text + "\n", encoding="utf-8")
        ok(f"已写出 {dst}（{stats['segments']} 段"
           + ("，已按出现顺序重新编号" if stats["resequenced"] else "）"))
    else:
        print(out_text)
    info(f"段数 {stats['segments']}；原文件含【第N段】标记：{stats['had_markers']}")
    info(f"切段依据：{stats['split_by']}"
         + (f"；超长段按 {max_chars} 字再切" if max_chars else ""))
    # #70：段数少到离谱时**必须说清风险**。段号是给引语定位用的，
    # 一段近万字时「第12段」约等于「第12 段 = 一整卷」，定位等于没有——
    # 而工具此前照常打印「✅ 规整完成」。
    if stats["segments"] <= 3 and len(text) > 4000:
        warn(f"只切出 {stats['segments']} 段而原文有 {len(text):,} 字——"
             f"段号已失去定位意义。建议加 --max-chars 3000 让它按句边界再切。")
    return EXIT_OK


def cmd_lint_quotes(args) -> int:
    head("引语体检 · 简繁不一致 / 省略号 / 归属可疑")
    info("提示器：glyph（简繁/用字）确证判失败；省略号与归属可疑是启发式，只提示")
    corpora: dict[str, str] = {}
    for p in getattr(args, "corpus", []) or []:
        pp = Path(p).expanduser()
        corpora[pp.stem] = pp.read_text(encoding="utf-8", errors="replace")
    rep = lintquotes.lint(Path(args.card).expanduser(), corpora)
    extra = "" if rep["corpus_provided"] else "（未给 --corpus：只做省略号检查）"
    tech = rep.get("technical_tokens_skipped") or 0
    print(f"   检查引语 {rep['quotes_checked']} 条{extra}"
          + (f"；跳过 {tech} 条技术 token（文件名/通配/URL，不是引语）" if tech else ""))
    if args.json_out:
        write_json(Path(args.json_out).expanduser(), rep)
        ok(f"已写出 {args.json_out}")
    for f in rep["findings"]:
        mark = "❌" if f["kind"] == "glyph" else "⚠️"
        print(f"   {mark} 第 {f['line']} 行 [{f['kind']}] {f['why']}")
        if f.get("pairs"):
            print("        差异字形：" + "，".join(f"{a}→{b}" for a, b in f["pairs"]))
        print(f"        「{f['quote'][:70]}」")
    if rep.get("vacuous"):
        die("⚠️ 空集假绿：卡片含引语候选，却一条都没抽出来 —— 体检器没干活，不是没问题",
            "确认引语写在引号里（「…」/\"…\"），且长度 ≥8 字符")
    if rep["verdict"] == "fail":
        die("体检发现**确证**用字不一致（简繁/异体）—— 引语不是逐字原文，核验必然失败",
            "把卡片引语统一成**语料所用字形**（见上列差异字形对），再跑 verify-quotes 确认")
    if rep["findings"]:
        warn(f"另有 {len(rep['findings'])} 条提示级发现（省略号 / 归属可疑），建议人工确认")
        if args.strict:
            die("--strict：存在提示级发现，按失败处理")
    ok("未发现用字不一致（简繁/异体）")
    return EXIT_OK


def cmd_overlap(args) -> int:
    head("语料重叠检测 · 换素材重蒸馏前的零重叠证明")
    info("口径：新语料的 n-gram 有多少出现在旧语料里 + 整句是否重复；"
         "两者都为 0 才是真零重叠")
    new_p, old_p = Path(args.new).expanduser(), Path(args.old).expanduser()
    for p in (new_p, old_p):
        if not p.exists():
            die(f"文件不存在：{p}", "先确认路径；两批语料都要是纯文本（.md/.txt）")
    rep = overlap.compute(new_p, old_p, n=args.n)
    print(f"   新语料 {rep['new_words']} 词 / 旧语料 {rep['old_words']} 词"
          f"（{rep['ngram_n']}-gram）")
    print(f"   共享 {rep['shared_shingles']} 个 {rep['ngram_n']}-gram"
          f"  包含率 {rep['containment']:.4%}")
    print(f"   整句重复 {rep['exact_duplicate_sentences']} / {rep['new_sentences']} 句"
          f"  子串命中 {rep['substring_contained_sentences']}")
    if args.json_out:
        write_json(Path(args.json_out).expanduser(), rep)
        ok(f"已写出 {args.json_out}")
    if rep["examples"]:
        info("共享片段示例：" + " ｜ ".join(e[:60] for e in rep["examples"][:3]))
    if rep["overlap_verdict"] == "FAIL":
        die("判定 FAIL：两批语料实质重叠，不满足『换素材』前提",
            "换来源，或把重叠部分登记为已知交集后再继续")
    ok(f"判定 PASS：包含率 {rep['containment']:.4%}，整句重复 "
       f"{rep['exact_duplicate_sentences']} 句")
    return EXIT_OK


def cmd_cross_review(args) -> int:
    head("交叉复核 · 多个独立评分 Agent 的分差门禁")
    info("口径（照抄 nuwa 第三条铁律）：分差 > 阈值才须人工复核；评分人数不足不构成交叉复核")
    res = _cross_review_from_arg(args.scores, args.threshold, args.subject)
    print(f"   评分 {res['scorers']} 个：{res['scores']}")
    print(f"   最低 {res['min']:g}  最高 {res['max']:g}  分差 {res['spread']:g}  阈值 {res['threshold']:g}"
          f"  最少人数 {res['min_scorers']}")
    if res["threshold_fragile"]:
        warn(f"分差 {res['spread']:g} 贴着阈值 ±1 —— 阈值脆弱，单点读数不可单独引用")
    for r in res["reasons"]:
        warn(r)
    if args.out:
        write_json(Path(args.out).expanduser(), res)
        ok(f"已写出 {args.out}")
    if res["needs_human_review"]:
        die(f"判定 {res['verdict']}：不得作为「已交叉复核」放行",
            "请第三个独立评分 Agent 复评，或人工裁定并记录裁定理由",
            "确认只是评分噪声时可用 --threshold 放宽，但放宽须写进披露")
        return EXIT_FAIL
    ok(f"判定 {res['verdict']}：{res['scorers']} 个评分 Agent 分差 {res['spread']:g} ≤ {res['threshold']:g}")
    return EXIT_OK


def cmd_strategy(args) -> int:
    head("输出形态决策 · single-first-v1")
    rep = strategy.decide(Path(args.bundle), requested=args.mode, purpose=args.purpose,
                          trigger_ready=args.trigger_ready, promo_budget=args.budget)
    ok(f"推荐形态：{rep['selected']}   （{rep['counts']['promoted']} 晋级 / "
       f"{rep['counts']['router']} 路由 / 共 {rep['counts']['total']}）")
    for r in rep["reasons"]:
        info("· " + r)
    info("备选：" + rep["alternative"])
    p = strategy.write_decision(Path(args.bundle), rep, Path(args.out) if args.out else None)
    info(f"决策记录：{p}")
    return EXIT_OK


# --------------------------------------------------------------------------
# 发布 / 快照 / 回滚
# --------------------------------------------------------------------------
def cmd_compile(args) -> int:
    head("compile")
    res = publish.compile_bundle(Path(args.bundle), Path(args.out), allow_grade=args.allow_grade,
                                 force=args.force, overwrite=args.overwrite, mode=args.mode,
                                 with_reports=getattr(args, "with_reports", False))
    for r in res["skills"]:
        print(f"   ✓ {r['slug']:<28} FIDELITY {r['fidelity_score']}/{r['fidelity_grade']}")
    # 复审 #4：**只在真的复制了报告时才说"已随产物发布"**。
    # 此前无条件打印，于是"没找到报告"的 bundle 也会看到成功提示——假绿。
    if getattr(args, "with_reports", False):
        done = [r["slug"] for r in res["skills"] if r.get("report_published")]
        missing = [r["slug"] for r in res["skills"] if not r.get("report_published")]
        if done:
            info(f"--with-reports：{len(done)} 份 FIDELITY 报告已写入产物"
                 f"（skills/<slug>/FIDELITY.*）：{'、'.join(done)}")
        if missing:
            warn(f"--with-reports：{len(missing)} 张卡**未找到** FIDELITY 报告，未随包发布："
                 f"{'、'.join(missing)}（检查卡片同级 FIDELITY.md/.json 或 bundle 的 "
                 "fidelity/<slug>.* / eval/<slug>.*）")
        if not done:
            warn("--with-reports 已指定，但没有任何报告被写入产物——产物里**没有**质量证据")
    if res["pre_snapshot"]:
        info(f"发布前快照：{res['pre_snapshot']}")
    ok(f"已发布 {res['count']} 个技能（mode={res['mode']}）→ {res['out']}")
    info(f"回滚：python3 scripts/td.py rollback {res['out']} --to latest")
    return EXIT_OK


def cmd_snapshot(args) -> int:
    target = Path(args.dir).expanduser().resolve()
    sid = publish.snapshot(target, args.label or "")
    ok(f"快照已创建：{sid}  ({publish.snap_root(target) / sid})")
    return EXIT_OK


def cmd_rollback(args) -> int:
    res = publish.rollback(Path(args.dir).expanduser().resolve(), args.to)
    info(f"回滚前另存：{res['pre_snapshot']}（可再回滚）")
    ok(f"已回滚到 {res['restored']}（{res['files']} 个文件）")
    return EXIT_OK


# --------------------------------------------------------------------------
# 评测
# --------------------------------------------------------------------------
def cmd_trigger(args) -> int:
    if args.trigger_cmd == "build":
        suite = evals.build_suite(Path(args.bundle), Path(args.out) if args.out else None)
        out = Path(args.out) if args.out else Path(args.bundle) / "eval-suite.json"
        ok(f"测试套件骨架：{len(evals._cases_of(suite))} 条用例 → {out}")
        for r in suite["rules"]:
            info("· " + r)
        info("已按上游 eval-suite 契约生成（case_id/prompt/expected/sibling_target）")
        info(f"下一步：td.py trigger split {out}   # 切 train/validation")
        return EXIT_OK
    if args.trigger_cmd == "split":
        suite = read_json(Path(args.suite))
        sp = evals.split_cases(suite, seed=args.seed, train_ratio=args.ratio)
        p = Path(args.out) if args.out else Path(args.suite).with_name("trigger-split.json")
        write_json(p, sp)
        ok(f"切分完成（seed={sp['split_seed']} ratio={sp['train_ratio']}）→ {p}")
        info(f"train {len(sp['train'])} 条 / validation {len(sp['validation'])} 条")
        info("validation 在选版前保持隐藏；选完版只跑一次，否则结果没有意义")
        return EXIT_OK
    if args.trigger_cmd == "prepare":
        suite = read_json(Path(args.suite))
        ids = None
        if args.set in ("train", "validation"):
            ids = evals.split_cases(suite)[args.set]
        p = evals.prepare_blind(suite, ids, Path(args.out))
        ok(f"盲测任务包（不含 expect/why）：{p}")
        info("同目录 answers-template.jsonl：把被测 Agent 的作答按格式填好后交给 score")
        return EXIT_OK
    if args.trigger_cmd == "record":
        ids = None
        sp = Path(args.suite).with_name("trigger-split.json")
        if args.set in ("train", "validation") and sp.exists():
            ids = read_json(sp)[args.set]
        p = evals.record_sheet(read_json(Path(args.suite)), Path(args.out), case_ids=ids)
        ok(f"答卷已生成：{p}" + (f"（仅 {args.set} 集）" if ids else ""))
        info("把 skills_in_scope 全部给被测 Agent 作答，把选择填进 actual，存为 answers.json")
        info("然后：td.py trigger score <suite> answers.json")
        return EXIT_OK
    suite = read_json(Path(args.suite))
    answers = read_json(Path(args.answers))
    if isinstance(answers, dict) and "answers" in answers:
        answers = answers["answers"]
    res = evals.score_suite(suite, answers)
    head("触发评测")
    print(f"通过 {res['passed']}/{res['total']}（{res['pass_rate']:.0%}）→ {res['verdict']}")
    m = res["metrics"]
    print(f"   precision {m['precision']}   recall {m['recall']}   F1 {m['f1']}")
    print(f"   诱饵通过率 {m['decoy_pass_rate']:.0%}（{m['decoy_total']} 条）"
          f"   兄弟混淆率 {m['sibling_confusion_rate']:.0%}（{m['sibling_confusion']} 条）")
    print(f"   TP {m['tp']} / FP {m['fp']} / FN {m['fn']}")
    for k, v in res["by_kind"].items():
        print(f"   {k:<10} {v['pass']}/{v['total']}")
    for r in res["results"]:
        if r["status"] == "fail":
            print(f"   ❌ {r['id']} 期望 {r['expect']} 实际 {r['actual']} — {r.get('why', '')}")
        elif r["status"] == "unanswered":
            print(f"   ⚠️  {r['id']} 未作答")
    p = Path(args.out) if args.out else Path(args.suite).with_name("trigger-eval.json")
    write_json(p, res)
    info(f"报告：{p}")
    if res["verdict"] != "pass":
        die("触发测试未通过（容错 0）",
            "诱饵被响应 → 改 description 的『不做/不适用』段",
            "兄弟混淆（选错邻居）→ 两张卡的 B 段『易混淆辨析』都要重写，只改一张无效",
            f"未作答 {len(res['unanswered'])} 条 → 先补齐再判分")
    return EXIT_OK


def cmd_output_eval(args) -> int:
    res = evals.output_eval(Path(args.card))
    head(f"输出评测 · {Path(args.card).name}")
    info(f"规模：{res['chars']} 字符 / {res['tokens']} tokens")
    missing = [k for k, v in res["sections"].items() if not v]
    info("六段：" + ("齐全" if not missing else f"缺 {', '.join(missing)}"))
    info(f"引语 {res['quotes_found']} 条")
    for e in res["errors"]:
        print(f"   ❌ {e}")
    for w in res["warns"]:
        print(f"   ⚠️  {w}")
    if args.out:
        write_json(Path(args.out), res)
    return EXIT_OK if res["verdict"] != "fail" else EXIT_FAIL


def cmd_verify_quotes(args) -> int:
    head(f"引语核验 · {Path(args.card).name}")
    res = evals.verify_quotes(Path(args.card), Path(args.corpus))
    k = res["refs_by_kind"]
    bk_checked = res.get("book_block", {}).get("checked", 0)
    info(f"引用 {res['refs_total'] + bk_checked} 个（条目引用 {k['entry_refs']} "
         f"+ 时间戳 {k['timestamp_refs']} + 书类引用块 {bk_checked}）")
    # 引用总数必须能加总还原，否则报告会自相矛盾（曾出现"引用 44 个但只核到 3 条"
    # 而不说明其余去处的缺陷）。三类归宿逐项打印。
    print(f"   逐字引语核验 {res['quotes_checked']} 条 → 命中 {res['verified']} 条")
    if k.get("ts_locator_only"):
        print(f"   表格/披露表定位锚点 {k['ts_locator_only']} 个（不承载引语，不计入分母）")
    if k.get("ts_unquoted"):
        print(f"   概述式引用 {k['ts_unquoted']} 个（有引用无逐字引语，提示级）")
    rec = res.get("reconciliation", {})
    if rec and not all(rec.values()):
        warn("引用计数无法加总还原 —— 统计口径有漏，请修 verify_quotes")
    # 2026-10-07（#57）：**把「挂错位置」与「真的不存在」分开报**。
    # 旧实现一律说「未在语料中找到」，而引语明明在语料里、只是位置标错——
    # 用户看到那句话会去删一条真引语。这两件事对用户的意义完全相反：
    # 一个要「改引用位置」，一个要「删掉并追查怎么编出来的」。
    for m_ in res.get("misplaced", []):
        print(f"   ⚠️  【第{m_['ref']}条】引语存在但**位置不符**："
              f"实际在 {', '.join('@' + w for w in m_['actually_at'])}"
              f"（你标注的是 {m_['ref']}）")
        print(f"        「{m_['quote'][:60]}」→ 改引用位置即可，**引语本身是真的**")
    for u in res["unverified"]:
        print(f"   ❌ 【第{u['ref']}条】全篇语料中均未找到（疑似编造或转述改写）："
              f"{u['quote'][:60]}")
    for o in res["orphaned_refs"]:
        print(f"   ❌ 语料中不存在编号：{o}")
    # 2026-10-07（#60）：被语言过滤丢掉的候选**必须显式打出来**。
    # 旧实现把它们静默混进「表格定位锚点（不承载引语，不计入分母）」，
    # 于是引语数、分母、覆盖率三项一起低估，最后还打印一句干净的 ✅。
    for s in res.get("lang_skipped", []):
        print(f"   ⚠️  【第{s['ref']}条】**未核验**：行内中文候选因「语料判为英文」被过滤")
        print(f"        「{s['quote'][:60]}」")
        print(f"        → 本工具**没有核验它**（区分不了「作者行文」与「真引语」），"
              f"需人工确认它不是来源引语")
    if args.out:
        write_json(Path(args.out), res)
    # 2026-10-09（第三方测评 #2 / 报告 P1）：空集守卫。
    # 卡片含引语候选（「」/"" 引号）却一条都没进统计 = 工具无法锚定，不得判通过。
    if res.get("vacuous"):
        if args.allow_empty:
            warn("空集假绿：卡片含引语但无定位标记，工具无法机器核验 —— 已按 --allow-empty 放行")
            return EXIT_OK
        die("⚠️ 空集假绿：卡片里含引语（「」/引号），但没有任何可识别的定位标记"
            "（【第N条】/ [时间戳]），工具无法把引语锚定到语料、一条都没核验。",
            "这正是「引用 0 个 → ✅ 全部核到」那类最危险的假绿。",
            "修复二选一：① 给引语加定位标记（书类语料用 --allow-empty 仅作临时放行）；"
            "② 改用 anchor 命令做段落级锚定核验。",
            "绝不允许在「无法核验」的状态下宣布引语已核对。")
    if res["verdict"] == "pass":
        n_skip = len(res.get("lang_skipped", [])) + res.get("book_block", {}).get("lang_skipped", 0)
        if n_skip:
            ok(f"已核引语全部在语料中核到 —— 但另有 {n_skip} 条候选**未核验**"
               f"（见上），**不等于它们没问题**")
        else:
            ok("全部引语在语料中核到")
        return EXIT_OK
    die("存在核不到或编号不存在的引语 —— 这类来源不实必须修掉，不允许发布",
        "⚠️ 先看上面的分类：标「位置不符」的是引用位置写错（引语是真的，改位置即可）；"
        "标「全篇语料中均未找到」的才疑似编造，必须删掉并追查来源。",
        "常见原因：转述时改写了原话、编号写错、或引用了他篇/他源内容",
        f"修正后重跑：python3 scripts/td.py verify-quotes {args.card} {args.corpus}")


def cmd_audit_coverage(args) -> int:
    """穷举语料，列出卡片未覆盖的段落——把 FIDELITY 评分员手工做的穷举自动化。"""
    res = evals.audit_coverage(Path(args.card), Path(args.corpus),
                               threshold=args.threshold, min_words=args.min_words)
    head(f"覆盖审计 · {Path(args.card).name}")
    info(f"语料段落 {res['paragraphs_total']}（实质 {res['substantive']}）")
    # #58：实质 0 段 = 审计没干活。旧版在这种情况下照样打印「未覆盖 0 · 覆盖率 0%」，
    # 扫一眼的人会把「未覆盖 0」读成"全都覆盖了"——与 #38 的虚假满覆盖同形。
    if res.get("vacuous"):
        die(f"⚠️ 空集假绿：{res['paragraphs_total']} 个段落**全部被跳过**，"
            f"没有任何段落参与审计 —— 本命令没有给出任何覆盖结论",
            "每个段落的实质词数都低于 --min-words。中文按**字**计数，"
            "长段落仍被跳过说明 --min-words 设得过大；"
            "也可能是语料格式不对（需要 td.py transcript 产出的 [时间戳] 逐字稿）")
    info(f"已覆盖 {res['covered']} · 未覆盖 **{res['uncovered']}** · 覆盖率 {res['coverage_rate']:.0%}")
    d = res["coverage_distribution"]
    info(f"覆盖率分布 min={d['min']:.2f} p25={d['p25']:.2f} 中位={d['median']:.2f} "
         f"p75={d['p75']:.2f} max={d['max']:.2f}（阈值 {res['threshold']}）")
    # 不能只把 100% 丢给用户就完事——同一个跳坑三次了（0.30 / 0.60 都给过虚假 100%）。
    if res.get("threshold_fragile"):
        warn("阈值敏感：当前覆盖率**脆弱**，不得单独引用")
        info(f"最低段落 cov={d['min']:.2f}，距阈值仅 {res['threshold_margin']}")
        sr = res["strict_reference"]
        info(f"更严格档 {sr['threshold']} → 覆盖 {sr['covered']} 段"
             f"（{sr['coverage_rate']:.0%}），掉出 {sr['uncovered']} 段")
        _s = res["threshold_sensitivity"]
        info("阈值敏感性：" + " · ".join(
            f"{k}→{v['coverage_rate']:.0%}" for k, v in _s.items()))
        info("结论请写成区间，不要写成单点")
    else:
        info(f"结论稳定（最低 cov={d['min']:.2f}，距阈值 {res['threshold_margin']}）")
    if res["uncovered_paragraphs"]:
        info("")
        info("未覆盖段落（按覆盖率升序，最低的在最需要补的位置）：")
        for u in res["uncovered_paragraphs"][:args.limit]:
            info(f"  [{u['ts']}] cov={u['coverage']:.2f}  {u['text'][:110]}")
        if len(res["uncovered_paragraphs"]) > args.limit:
            info(f"  …… 还有 {len(res['uncovered_paragraphs']) - args.limit} 段（--limit 调整）")
    if args.out:
        write_json(Path(args.out), res)
        info(f"\n完整结果：{args.out}")
    if args.fail_under_covered is not None and res["uncovered"] > args.fail_under_covered:
        die(f"未覆盖段落 {res['uncovered']} 段，超过阈值 {args.fail_under_covered}",
            "这些内容要么收进卡片，要么逐条写进『素材未涉及 / 本卡自加』清单",
            "原则：清单按**穷举**维护，不按需维护")
    return EXIT_OK


def cmd_count(args) -> int:
    res = evals.token_metrics(Path(args.path))
    head(f"token 计量 · {res['root']}")
    info(f"计数方式：{res['counter']}")
    print(f"   常驻发现成本 discovery_payload : {res['discovery_payload']:>7}")
    print(f"   语料总量 corpus_total          : {res['corpus_total']:>7}")
    sk = res["skill_md"]
    print(f"   SKILL.md  min/median/max/total : {sk['min']} / {sk['median']} / {sk['max']} / {sk['total']}")
    print("\n   最耗 token 的 10 个文件：")
    for e in res["top10"]:
        print(f"     {e['tokens']:>7}  {e['file']}")
    if args.out:
        write_json(Path(args.out), res)
    return EXIT_OK


def cmd_bench(args) -> int:
    res = evals.bench(lambda: evals.token_metrics(Path(args.path)), rounds=args.rounds)
    head(f"benchmark · {args.path} × {args.rounds}")
    print(f"   min {res['min']}s / median {res['median']}s / max {res['max']}s")
    return EXIT_OK


# --------------------------------------------------------------------------
# 演进
# --------------------------------------------------------------------------
def cmd_diff(args) -> int:
    res = evolve.diff_sources(Path(args.a), Path(args.b))
    head(f"diff · {args.a} → {args.b}")
    s = res["summary"]
    print(f"   新增 {s['added']} · 删除 {s['removed']} · 变更 {s['changed']} · 未变 {s['unchanged']}")
    for c in res["changed"]:
        info(f"   ~ {c['slug']}：{'、'.join(c['sections_changed'][:4])}（{c['chars'][0]}→{c['chars'][1]} 字符）")
    for a in res["added"]:
        info(f"   + {a}")
    for r in res["removed"]:
        info(f"   - {r}")
    if args.out:
        write_json(Path(args.out), res)
    return EXIT_OK


def cmd_impact(args) -> int:
    res = evolve.impact_analysis(Path(args.dir), args.slug)
    head(f"影响面 · {args.slug}")
    if not res["affected_count"]:
        info("没有其它技能引用它 —— 可安全改动")
    for h in res["affected"]:
        info(f"   {h['skill']}  引用：{', '.join(h['refs'][:5])}")
    if args.out:
        write_json(Path(args.out), res)
    return EXIT_OK


def cmd_repair(args) -> int:
    res = evolve.repair(Path(args.dir), apply=args.apply)
    head(f"repair · {args.dir}{'（已落盘）' if args.apply else '（dry-run，加 --apply 落盘）'}")
    if not res["count"]:
        ok("没有可机械修复的问题")
    for f in res["fixable"]:
        info(f"   {f['file']}：{'、'.join(f['notes'])}")
    if res["count"] and not args.apply:
        info("repair 只做无争议的机械修复，不会替你补内容（补内容=编造）")
    return EXIT_OK


def cmd_patch(args) -> int:
    res = evolve.apply_patch(Path(args.card), read_json(Path(args.patch)), apply=args.apply)
    head(f"patch · {Path(args.card).name}{'（已落盘）' if args.apply else '（dry-run）'}")
    for c in res["changes"]:
        info("· " + c)
    for line in res["diff"]:
        info("  " + line)
    if not args.apply:
        info("加 --apply 落盘")
    return EXIT_OK


def cmd_update(args) -> int:
    res = evolve.update_flow(Path(args.bundle), Path(args.out), apply=args.apply)
    head(f"update · {Path(args.bundle)} → {args.out}")
    info(f"校验：{res['validated']}")
    for e in res["errors"][:10]:
        print(f"   ❌ {e[2] if len(e) > 2 else e}")
    if res["local_edit"]:
        warn(f"目标存在本地改动 {len(res['local_edit'])} 处")
    if res.get("compile"):
        ok(f"已重编译 {res['compile']['count']} 个技能，快照 {res.get('pre_snapshot')}")
    return EXIT_OK


def cmd_prompt(args) -> int:
    res = promptc.compile_prompt(Path(args.src), Path(args.out) if args.out else None, mode=args.mode)
    head(f"compile-prompt · mode={res['mode']}")
    info(f"内联文件 {len(res['inlined'])} 个：{'、'.join(res['inlined'][:6]) or '（无）'}")
    ok(f"{res['chars']} 字符 / {res['tokens']} tokens（{res['counter']}）")
    info(f"输出：{res['out']}")
    return EXIT_OK


def cmd_schema(args) -> int:
    p = SCHEMA_DIR / f"{args.name}.schema.json"
    if not p.exists():
        die(f"schema 不存在：{p}",
            "可选：" + "、".join(sorted(x.name.replace(".schema.json", "")
                                        for x in SCHEMA_DIR.glob("*.schema.json"))))
    ok(str(p))
    print(read_text(p))
    return EXIT_OK


# --------------------------------------------------------------------------
# 上游直通 / 字幕获取
# --------------------------------------------------------------------------
def cmd_contract(args) -> int:
    if args.contract_cmd == "list":
        head("上游契约（kangarooking/cangjie-skill，MIT · 本包以此为权威）")
        st = contracts.status()
        info(f"契约目录：{st['dir']}")
        info(f"校验方式：{'jsonschema（完整）' if st['jsonschema'] else '内置子集校验（未装 jsonschema，覆盖 required/enum/const/pattern/type）'}")
        print()
        for name, okk in st["contracts"].items():
            print(f"  {'✅' if okk else '❌'} {name:<20} {contracts.MAP[name]}")
        return EXIT_OK if all(st["contracts"].values()) else EXIT_FAIL
    path = Path(args.file)
    if not path.exists():
        die(f"文件不存在：{path}")
    data = read_json(path)
    res = contracts.validate(args.name, data)
    head(f"契约校验 · {args.name}")
    info(f"文件：{path}")
    info(f"方式：{res['mode']}")
    if res["ok"]:
        ok("符合上游契约")
        return EXIT_OK
    for e in res["errors"][:12]:
        print(f"   ❌ {e}")
    die(f"不符合上游契约 {args.name}（共 {len(res['errors'])} 处）",
        "修实现，不要改契约——契约的价值就在于强制")


def cmd_failure(args) -> int:
    head("失败用例集（上游 failure-case 契约）")
    from tdlib import defects
    cases = defects.build_cases()
    if args.failure_cmd == "list":
        from tdlib.evals import SEVERITY_ORDER
        for c in cases:
            fc, dg = c["failure_case"], c["diagnosis"]
            sev = fc["severity"]
            info(f"[{SEVERITY_ORDER[sev]}] {c['skill']:<28} {dg.get('category') or '-':<16} {fc['prompt'][:46]}")
        n_crit = sum(1 for c in cases if c["failure_case"]["severity"] == "critical")
        print()
        info(f"共 {len(cases)} 条，其中 critical {n_crit} 条")
        return EXIT_OK
    rep = evals.export_failure_cases(cases, Path(args.out) if args.out else
                                      Path("failure-cases.json"))
    ok(f"导出 {rep['valid']} 条（{rep['invalid']} 条不合契约）→ {args.out or 'failure-cases.json'}")
    info(f"按严重级：{rep['by_severity']}")
    return EXIT_OK if rep["invalid"] == 0 else EXIT_FAIL


def cmd_upstream(args) -> int:
    if args.upstream_cmd == "list":
        head("vendored 上游能力（kangarooking/cangjie-skill, MIT）")
        d = upstream.doctor()
        for line in d["lines"]:
            info(line)
        print()
        info("调用方式：td.py upstream run <tool> [args...]")
        info("建议：能用上游就用上游（本包自研是兜底，也是上游没有的部分）")
        return EXIT_OK
    code = upstream.run_upstream(args.tool, args.rest, dry=args.dry_run)
    if code == 0 and not args.dry_run:
        ok(f"上游 {args.tool} 执行完成")
    return code


def cmd_fetch_subtitle(args) -> int:
    head("字幕获取（本包唯一联网命令，默认 dry-run）")
    langs = tuple(args.lang.split(",")) if args.lang else fetch.LANGS
    res = fetch.fetch_subtitle(args.url, Path(args.out), langs=langs,
                                cookies=args.cookies, execute=args.execute,
                                use_proxy=not args.no_proxy)
    if res["status"] == "dry-run":
        info("")
        warn("未执行：加 --execute 才会真正下载")
    return EXIT_OK


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="td.py", description="rulai-distill 工具链（纯本地 · 零网络 · 零依赖可跑）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="典型流程：init → chunk/transcript → research init（人物）→ validate → gate "
               "→ strategy → compile → trigger build/record/score")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="环境自检 + 能力矩阵").set_defaults(func=cmd_doctor)

    q = sub.add_parser("init", help="生成 bundle 骨架")
    q.add_argument("dir")
    q.add_argument("--person", default="待填", help="六路调研骨架里的人物名")
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("chunk", help="结构感知分块（+索引 +缓存）")
    q.add_argument("src")
    q.add_argument("--sidecar")
    q.add_argument("--max-chars", type=int, default=4000)
    q.add_argument("--source-id", default="src-main")
    q.add_argument("--force", action="store_true", help="忽略缓存重算")
    q.set_defaults(func=cmd_chunk)

    q = sub.add_parser("index", help="查看/检索分块索引")
    q.add_argument("sidecar")
    q.add_argument("--grep", help="按标题路径关键词检索块")
    q.add_argument("--limit", type=int, default=10)
    q.set_defaults(func=cmd_index)

    q = sub.add_parser("lexindex", help="SQLite FTS5 词法索引 / 查询（含邻接块）")
    q.add_argument("chunks", nargs="?", default="", help="chunks.jsonl 路径（建索引时用）")
    q.add_argument("--db", help="索引路径，默认 <sidecar>/lexical.sqlite")
    q.add_argument("--query", help="查询词；给了就是查询模式")
    q.add_argument("--limit", type=int, default=5)
    q.add_argument("--neighbors", type=int, default=1, help="命中块前后各取几块（防断章取义）")
    q.set_defaults(func=cmd_lexindex)

    q = sub.add_parser("preview", help="预览分块")
    q.add_argument("sidecar")
    q.add_argument("--limit", type=int, default=10)
    q.set_defaults(func=cmd_preview)

    q = sub.add_parser("transcript", help="SRT/VTT → 带时间戳逐字稿（离线）")
    q.add_argument("inputs", nargs="+")
    q.add_argument("--out")
    q.add_argument("--merge", action="store_true")
    q.add_argument("--gap", type=int, default=2500, help="合并间隔阈值(ms)")
    q.add_argument("--max-chars", type=int, default=420)
    q.add_argument("--offset", type=int, default=0, help="整体时间偏移秒（多集拼接）")
    q.set_defaults(func=cmd_transcript)

    q = sub.add_parser("research", help="人物六路调研")
    rq = q.add_subparsers(dest="research_cmd", required=True)
    a = rq.add_parser("init", help="生成六路调研骨架")
    a.add_argument("dir")
    a.add_argument("--person", default="待填")
    a.add_argument("--overwrite", action="store_true")
    a.set_defaults(func=cmd_research)
    b = rq.add_parser("merge", help="合并去重 + 冲突标记")
    b.add_argument("files", nargs="+")
    b.add_argument("--out", required=True)
    b.add_argument("--threshold", type=float, default=0.62)
    b.set_defaults(func=cmd_research)

    q = sub.add_parser("validate", help="静态校验")
    q.add_argument("path")
    q.set_defaults(func=cmd_validate)

    q = sub.add_parser("gate", help="FIDELITY 门槛判定（默认要求交叉复核记录）")
    q.add_argument("report")
    q.add_argument("--min", default="B", choices=["A", "B", "C", "D"])
    q.add_argument("--allow-fallback", action="store_true",
                   help="允许 fallback 自测通过（不得对外宣称质量）")
    q.add_argument("--scores", default="",
                   help="多个独立评分 Agent 的总分（逗号分隔，如 95,88）；给了就强制走交叉复核门禁")
    q.add_argument("--allow-single-scorer", action="store_true",
                   help="显式豁免交叉复核（单评分 Agent 放行；不得作为对外质量证据）")
    q.add_argument("--cross-threshold", type=float, default=fid.CROSS_REVIEW_THRESHOLD,
                   help="分差阈值（默认 10，照抄 nuwa 第三条铁律口径）")
    q.set_defaults(func=cmd_gate)

    q = sub.add_parser("eval-kit", help="独立评测套件：题库/评分模板/JSON 回传/分差门禁")
    eq = q.add_subparsers(dest="eval_cmd", required=True)
    a = eq.add_parser("init", help="生成题库 / 答题模板 / 评分模板 / 工作流说明")
    a.add_argument("card", help="被评测的卡片（SKILL.md）")
    a.add_argument("--out", required=True, help="套件输出目录")
    a.set_defaults(func=cmd_eval_kit)
    c = eq.add_parser("check", help="汇总答题+评分 → 交叉复核 → 产出 FIDELITY JSON")
    c.add_argument("--answers", required=True, help="独立答题 Agent 回传的 answers.json")
    c.add_argument("--scores", nargs="+", required=True,
                   help="≥2 个独立评分 Agent 回传的 scores-*.json")
    c.add_argument("--subject", help="被评测对象标识，写进报告便于审计")
    c.add_argument("--out", help="FIDELITY JSON 输出路径（默认与 answers 同目录 FIDELITY.json）")
    c.set_defaults(func=cmd_eval_kit)

    q = sub.add_parser("cross-review", help="多评分 Agent 交叉复核（分差 > 阈值须人工复核）")
    q.add_argument("scores", help="各评分 Agent 的总分，逗号分隔，如 95,88")
    q.add_argument("--threshold", type=float, default=fid.CROSS_REVIEW_THRESHOLD)
    q.add_argument("--subject", help="被复核对象标识，写进结果便于事后审计")
    q.add_argument("--out", help="写出 rulai-distill/cross-review@1 JSON")
    q.set_defaults(func=cmd_cross_review)

    q = sub.add_parser("anchor", help="引语段号锚定：验引语是否真在它声明的 §N 段内")
    q.add_argument("card", help="卡片或候选文件（写明 §N 与引语的那份）")
    q.add_argument("--corpus", nargs="+", required=True, help="逐字稿 / 书类【第N段】语料（段号来源，可多份）")
    q.add_argument("--n", type=int, default=5)
    q.add_argument("--json-out", help="把报告写成 JSON")
    q.set_defaults(func=cmd_anchor)

    q = sub.add_parser("corpus-anchor",
                       help="书类语料规整：把书类原文产出成 anchor 可读的【第N段】形式")
    q.add_argument("infile", help="书类原文（可带或不含【第N段】标记）")
    q.add_argument("-o", "--out", help="输出文件（不指定则打印到 stdout）")
    q.add_argument("--max-chars", type=int, default=0,
                   help="单段超过此字数则按句边界再切（0 = 不切）。"
                        "不加时，一行一段的公版典籍会被切成整卷一「段」")
    q.set_defaults(func=cmd_corpus_anchor)

    q = sub.add_parser("lint-quotes",
                       help="引语体检：简繁不一致 / 省略号 / 归属可疑（核验前的提示器）")
    q.add_argument("card", help="卡片（SKILL.md）")
    q.add_argument("--corpus", nargs="*", default=[],
                   help="语料原文（可多份）；简繁与归属检查需要，省略号检查不需要")
    q.add_argument("--json-out", help="把体检报告写成 JSON")
    q.add_argument("--strict", action="store_true", help="任何发现（含提示级）都判失败")
    q.set_defaults(func=cmd_lint_quotes)

    q = sub.add_parser("overlap", help="语料重叠检测：证明两批素材零重叠（换素材重蒸馏前用）")
    q.add_argument("--new", required=True, help="新语料（.md/.txt）")
    q.add_argument("--old", required=True, help="旧语料（.md/.txt）")
    q.add_argument("--n", type=int, default=8, help="n-gram 长度（默认 8）")
    q.add_argument("--json-out", help="把报告写成 JSON")
    q.set_defaults(func=cmd_overlap)

    q = sub.add_parser("strategy", help="输出形态决策 single/pack")
    q.add_argument("bundle")
    q.add_argument("--purpose", choices=["learning", "reference", "workflow", "distribution"])
    q.add_argument("--mode", choices=["single", "pack"])
    q.add_argument("--trigger-ready", action="store_true")
    q.add_argument("--budget", type=int, default=8)
    q.add_argument("--out")
    q.set_defaults(func=cmd_strategy)

    q = sub.add_parser("compile", help="原子发布")
    q.add_argument("bundle")
    q.add_argument("--out", required=True)
    q.add_argument("--mode", choices=["pack", "single"], default="pack")
    q.add_argument("--allow-grade", choices=["A", "B", "C", "D"])
    q.add_argument("--force", action="store_true")
    q.add_argument("--overwrite", action="store_true")
    q.add_argument("--with-reports", action="store_true",
                   help="把 FIDELITY 报告一并放进产物（质量证据随包发布）")
    q.set_defaults(func=cmd_compile)

    q = sub.add_parser("snapshot", help="创建快照")
    q.add_argument("dir")
    q.add_argument("--label", default="")
    q.set_defaults(func=cmd_snapshot)

    q = sub.add_parser("rollback", help="回滚")
    q.add_argument("dir")
    q.add_argument("--to", required=True)
    q.set_defaults(func=cmd_rollback)

    q = sub.add_parser("trigger", help="触发压力测试（Agent 作答，脚本判分）")
    tq = q.add_subparsers(dest="trigger_cmd", required=True)
    a = tq.add_parser("build", help="从 bundle 生成套件骨架")
    a.add_argument("bundle")
    a.add_argument("--out")
    a.set_defaults(func=cmd_trigger)
    s_ = tq.add_parser("split", help="固定种子切 train/validation")
    s_.add_argument("suite")
    s_.add_argument("--seed", type=int)
    s_.add_argument("--ratio", type=float, help="train 占比，默认 0.6")
    s_.add_argument("--out")
    s_.set_defaults(func=cmd_trigger)
    pr = tq.add_parser("prepare", help="生成盲测任务包（不含 expect/why）")
    pr.add_argument("suite")
    pr.add_argument("--out", required=True)
    pr.add_argument("--set", choices=["train", "validation", "all"], default="all")
    pr.set_defaults(func=cmd_trigger)
    b = tq.add_parser("record", help="生成待答问卷")
    b.add_argument("suite")
    b.add_argument("--out", required=True)
    b.add_argument("--set", choices=["train", "validation", "all"], default="all")
    b.set_defaults(func=cmd_trigger)
    c = tq.add_parser("score", help="机械判分（容错 0，输出 P/R/F1）")
    c.add_argument("suite")
    c.add_argument("answers")
    c.add_argument("--out")
    c.set_defaults(func=cmd_trigger)

    q = sub.add_parser("output-eval", help="产物机械体检")
    q.add_argument("card")
    q.add_argument("--out")
    q.set_defaults(func=cmd_output_eval)

    q = sub.add_parser("verify-quotes", help="机械核验卡片引语是否真在语料中")
    q.add_argument("card")
    q.add_argument("corpus", help="语料文件（含【第N条 | 日期 | id】定位标记，或书类逐字原文）")
    q.add_argument("--out")
    q.add_argument("--allow-empty", action="store_true",
                   help="卡片含引语却无定位标记、工具无法机器核验时，仍按空集放行（不推荐）")
    q.set_defaults(func=cmd_verify_quotes)

    q = sub.add_parser("audit-coverage", help="穷举语料，列出卡片未覆盖的段落")
    q.add_argument("card")
    q.add_argument("corpus")
    q.add_argument("--threshold", type=float, default=0.60,
                   help="覆盖率阈值，低于视为未覆盖（中文卡片+英文语料建议 ≥0.6）")
    q.add_argument("--min-words", type=int, default=8)
    q.add_argument("--limit", type=int, default=15)
    q.add_argument("--out")
    q.add_argument("--fail-under-covered", type=int,
                   help="未覆盖段数超过此值直接失败（接进 CI 用）")
    q.set_defaults(func=cmd_audit_coverage)

    q = sub.add_parser("count", help="token 计量")
    q.add_argument("path")
    q.add_argument("--out")
    q.set_defaults(func=cmd_count)

    q = sub.add_parser("bench", help="重复计时")
    q.add_argument("path")
    q.add_argument("--rounds", type=int, default=3)
    q.set_defaults(func=cmd_bench)

    q = sub.add_parser("diff", help="两版产物差异")
    q.add_argument("a")
    q.add_argument("b")
    q.add_argument("--out")
    q.set_defaults(func=cmd_diff)

    q = sub.add_parser("impact", help="改动影响面")
    q.add_argument("dir")
    q.add_argument("slug")
    q.add_argument("--out")
    q.set_defaults(func=cmd_impact)

    q = sub.add_parser("repair", help="机械修复（默认 dry-run）")
    q.add_argument("dir")
    q.add_argument("--apply", action="store_true")
    q.set_defaults(func=cmd_repair)

    q = sub.add_parser("patch", help="结构化补丁（默认 dry-run）")
    q.add_argument("card")
    q.add_argument("patch")
    q.add_argument("--apply", action="store_true")
    q.set_defaults(func=cmd_patch)

    q = sub.add_parser("update", help="重新校验 + 重编译（默认 dry-run）")
    q.add_argument("bundle")
    q.add_argument("--out", required=True)
    q.add_argument("--apply", action="store_true")
    q.set_defaults(func=cmd_update)

    q = sub.add_parser("prompt", help="编译成单文件 prompt")
    q.add_argument("src")
    q.add_argument("--out")
    q.add_argument("--mode", choices=["entry", "inline", "cards"], default="inline")
    q.set_defaults(func=cmd_prompt)

    q = sub.add_parser("schema", help="打印内置 JSON Schema")
    q.add_argument("name")
    q.set_defaults(func=cmd_schema)

    q = sub.add_parser("contract", help="查看/校验上游契约（权威契约层）")
    cq = q.add_subparsers(dest="contract_cmd", required=True)
    cq.add_parser("list", help="列出契约与校验方式").set_defaults(func=cmd_contract)
    c = cq.add_parser("check", help="按契约校验一个 JSON 产物")
    c.add_argument("name", help="契约名，如 source-document / registry-entry")
    c.add_argument("file")
    c.set_defaults(func=cmd_contract)

    q = sub.add_parser("failure", help="本包自身的失败用例集（failure-case 契约）")
    fq = q.add_subparsers(dest="failure_cmd", required=True)
    fq.add_parser("list", help="列出全部失败用例").set_defaults(func=cmd_failure)
    fx = fq.add_parser("export", help="导出为 failure-set JSON")
    fx.add_argument("--out")
    fx.set_defaults(func=cmd_failure)

    q = sub.add_parser("upstream", help="直通内置上游（cangjie）实现")
    uq = q.add_subparsers(dest="upstream_cmd", required=True)
    uq.add_parser("list", help="列出可用的上游能力与依赖状态").set_defaults(func=cmd_upstream)
    a = uq.add_parser("run", help="以子进程执行某个上游脚本")
    a.add_argument("tool", help="chunk / lexindex / count / strategy / validate / compile …")
    a.add_argument("rest", nargs=argparse.REMAINDER)
    a.add_argument("--dry-run", action="store_true", help="只打印将执行的命令")
    a.set_defaults(func=cmd_upstream)

    q = sub.add_parser("fetch-subtitle", help="获取字幕（唯一联网命令，默认 dry-run）")
    q.add_argument("url")
    q.add_argument("--out", required=True, help="字幕输出目录")
    q.add_argument("--lang", default="zh-Hans,zh-Hant,zh,en")
    q.add_argument("--cookies", help="cookies.txt（需登录的视频）")
    q.add_argument("--execute", action="store_true", help="真正执行（否则只打印命令）")
    q.add_argument("--no-proxy", action="store_true",
                   help="忽略环境代理变量直连（代理隧道 502 时用）")
    q.set_defaults(func=cmd_fetch_subtitle)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ToolError as e:
        die(e.message, *e.hints)
    except KeyboardInterrupt:
        print("\n⏹  已中断")
        return 130
    except SystemExit:
        raise
    except FileNotFoundError as e:
        die(f"文件或目录不存在：{e.filename or e}", "检查路径拼写")
    except PermissionError as e:
        die(f"权限不足：{e.filename or e}", "确认目标目录可写")
    except Exception as e:  # noqa: BLE001
        die(f"未预期的错误：{type(e).__name__}: {e}",
            "这是脚本缺陷，请附完整命令反馈；不会自动修改任何文件")
    return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
