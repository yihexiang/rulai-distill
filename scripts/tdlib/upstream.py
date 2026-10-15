# -*- coding: utf-8 -*-
"""tdlib.upstream — 内置上游实现（vendored）的直通与体检。

## 为什么保留上游代码而不是全部重写

rulai-distill v1.1.0 曾把 cangjie 的能力**重新实现**一遍。实测核证后发现，
上游在四处确实更深，重写版本是**变浅**的：

| 上游做法 | v1.1.0 的做法 | 后果 |
|---|---|---|
| `deterministic_cache_key(stage, impl_version, schema_version, input_hashes, params)` | 只用 (source_sha256, max_chars) | **改了分块算法仍命中旧缓存** |
| `build_index` 用 SQLite FTS5 + 中文 bigram，查询返回**邻接块**（防断章取义） | JSON 标题树 + `--grep` 路径匹配 | 只能按标题路径检索，无词法检索、无邻接扩展 |
| `new_run_id()` + `runs/<run_id>/` 每次运行独立留痕 | 只有发布前快照 | 无法回看任意一次分块/编译的结果 |
| `WriterLock`（O_EXCL）防并发写同一 target | 无 | 两个进程同时发布 → 半个 target，事后难查 |

**结论**：契约化与跨版本溯源确实是 cangjie 质量的主要来源，不是锦上添花。
因此 v1.2.0 起，上游脚本以 **vendored 形式原样保留**（MIT，署名见 PROVENANCE.md），
rulai-distill 自己的实现定位为「零依赖统一入口 + 上游没有的部分」。

本模块负责：
  1. 体检 vendored 目录（是否齐全、依赖是否满足）
  2. 把 `td.py` 的调用映射到对应上游脚本并**以子进程直通执行**（不经 shell）
  3. 给出「用哪个」的明确建议：能用上游就用上游

**边界**：上游脚本不在本包内修改（B 方案：原样 vendored + 在本包侧适配）。
若要改上游逻辑，请在其仓库提 PR；本包只在 `tdlib/` 提供适配与增强。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .util import ToolError, ensure_dir, info, ok, warn

VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor"
CANGJIE_DIR = VENDOR_DIR / "cangjie"
NUWA_DIR = VENDOR_DIR / "nuwa"

# td.py 子命令 → 上游脚本。None 表示上游无对应实现（由本包自研）
MAPPING = {
    "chunk": ("build_chunks.py", "分块 + 规范化 + 版本化缓存"),
    "lexindex": ("build_index.py", "SQLite FTS5 词法索引 + 邻接块扩展"),
    "count": ("count_tokens.py", "token 计量（需 tiktoken）"),
    "strategy": ("select_output_strategy.py", "single/pack 形态决策"),
    "validate": ("validate_skill_pack.py", "技能包校验（需 PyYAML）"),
    "compile": ("compile_pack.py", "pack 编译（需 PyYAML）"),
    "compile-single": ("compile_single.py", "single 编译（需 PyYAML）"),
    "trigger": ("run_trigger_evals.py", "触发评测"),
    "output-eval": ("run_output_evals.py", "输出评测"),
    "bench": ("benchmark.py", "基准"),
    "diff": ("diff_sources.py", "两版差异"),
    "impact": ("impact_analysis.py", "影响面"),
    "repair": ("repair_flow.py", "机械修复"),
    "patch": ("apply_skill_patch.py", "结构化补丁"),
    "update": ("update_flow.py", "重新校验 + 重编译（需 PyYAML）"),
    "cli": ("cangjie.py", "上游统一 CLI（doctor/status 等）"),
}

# MAPPING 键 → 它在 td.py 里的**真实入口**。
#
# 为什么需要这张表：2026-10-15 逐条核对发现 MAPPING 有 2 个键**不是 td.py 子命令**，
# 而 parity 表的列头写着「td.py 子命令」——读者照表敲 `td.py cli` 会直接报错。
# 原来的守卫只比对了「parity 表 ↔ MAPPING」，没比对「MAPPING ↔ td.py 实际子命令」，
# 所以这个不一致一直没红。别名在此显式登记，并由
# `t_parity_table_matches_upstream_mapping` 强制：每个键要么本身是子命令，要么在此有条目，
# 且每个别名指向的入口必须真实存在。
ALIASES = {
    "cli": "upstream",                 # td.py upstream run cli …
    "compile-single": "compile --mode single",   # td.py compile <bundle> --mode single
}

OPTIONAL_DEPS = {
    "count_tokens.py": ("tiktoken", "pip install tiktoken"),
    "validate_skill_pack.py": ("yaml", "pip install pyyaml"),
    "compile_pack.py": ("yaml", "pip install pyyaml"),
    "compile_single.py": ("yaml", "pip install pyyaml"),
    "update_flow.py": ("yaml", "pip install pyyaml"),
}


def _script_for(tool: str) -> Path:
    if tool not in MAPPING:
        raise ToolError(f"未知上游工具：{tool}",
                        "可用：" + "、".join(sorted(MAPPING)))
    p = CANGJIE_DIR / MAPPING[tool][0]
    if not p.exists():
        raise ToolError(f"上游脚本缺失：{p}",
                        "本包应自带 vendored 副本；若被删除请重新安装 rulai-distill")
    return p


def deps_ok(tool: str) -> tuple[bool, str]:
    if tool not in OPTIONAL_DEPS:
        return True, ""
    mod, hint = OPTIONAL_DEPS[tool]
    import importlib.util
    if importlib.util.find_spec(mod):
        return True, ""
    return False, f"{MAPPING[tool][0]} 需要 {mod}（{hint}）；缺失时用本包自研的等价命令"


def doctor() -> dict:
    head_lines = []
    present = [t for t in MAPPING if (CANGJIE_DIR / MAPPING[t][0]).exists()]
    missing = [t for t in MAPPING if t not in present]
    head_lines.append(f"vendored 上游：{CANGJIE_DIR}")
    head_lines.append(f"  可用工具 {len(present)}/{len(MAPPING)}")
    if missing:
        head_lines.append(f"  缺失：{'、'.join(sorted(missing))}")
    blocked = {}
    for t in present:
        fine, msg = deps_ok(t)
        if not fine:
            blocked[t] = msg
    if blocked:
        head_lines.append(f"  依赖不满足 {len(blocked)} 个：")
        for t, m in blocked.items():
            head_lines.append(f"    - {t}: {m}")
    return {"present": sorted(present), "missing": sorted(missing),
            "blocked": blocked, "lines": head_lines,
            "cangjie_dir": str(CANGJIE_DIR)}


def run_upstream(tool: str, args: list[str], dry: bool = False) -> int:
    """以子进程直通执行上游脚本（不经 shell，不拼 shell 命令）。"""
    script = _script_for(tool)
    fine, msg = deps_ok(tool)
    cmd = [sys.executable, str(script), *args]
    if dry:
        info("dry-run：将执行")
        info("  " + " ".join(cmd))
        if not fine:
            warn(f"注意：{msg}")
        return 0
    if not fine:
        raise ToolError(f"依赖不满足：{msg}",
                        "可改用本包自研的等价命令，或先安装依赖")
    info(f"→ 上游 {MAPPING[tool][0]}（{MAPPING[tool][1]}）")
    proc = subprocess.run(cmd, capture_output=False, text=True)
    return proc.returncode


def prefer_upstream(tool: str) -> bool:
    """该能力当前是否**实际上**会走到上游实现。

    2026-10-15 修正：原实现自己重复了一遍「脚本存在 + 依赖满足」的判断，
    而全仓 **0 个调用点**（死代码），`td.py upstream list` 里的
    「能用上游就用上游」是一句硬编码文本——建议是静态的，不反映每个工具的真实状态。

    现在改为从 `doctor()` 推导（单一真源，不与 `blocked` 逻辑分叉），
    并由 `td.py upstream list` 逐工具打印，使这句建议成为**计算结果**而非口号。
    """
    d = doctor()
    if tool not in d["present"]:
        return False
    return tool not in d["blocked"]
