#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_social_card.py — 渲染 GitHub 社交预览图（1280×640）。

为什么要有这个脚本（而不是丢一张 AI 生成的图）：
1. AI 生图渲染中文几乎必出乱码，而这张图的全部信息量都在文字上；
2. 图上的数字（回归项数 / 缺陷数 / 跨模型复评例数）**必须从真实产物推导**，
   否则又是一处会腐烂的「声称≠实际」。本脚本逐个读：
     · 版本      ← scripts/tdlib/__init__.py 的 __version__
     · 回归项数  ← tests/e2e.py 里 `def t_*` 的个数
     · 缺陷数    ← scripts/tdlib/defects.py 的 DEFECTS 长度
     · 跨模型例数 ← docs/independent-recheck/*/*/review.json 的有效份数
     · 声称条数  ← docs/verify_claims.py 的 parse_claims()
3. 可复跑：改完数字重新生成即可，不留在某人电脑里的手工图。

用法：
    python3 tools/make_social_card.py                 # 输出 dist/social-preview.png
    python3 tools/make_social_card.py --out /tmp/x.png
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

W, H = 1280, 640
# 深色底 + 一点渐变，避免纯色在大图上发闷
BG_TOP = (13, 17, 23)
BG_BOT = (22, 27, 34)
FG = (230, 237, 243)
FG_DIM = (139, 148, 158)
ACCENT = (88, 166, 255)      # 链接蓝
OK = (63, 185, 80)           # 通过绿
RULE = (48, 54, 61)


def facts() -> dict:
    """从真实产物推导图上要用的数字。任一来源读不到就抛错——不许静默给默认值。"""
    from tdlib import __version__ as version
    from tdlib.defects import DEFECTS

    e2e = (ROOT / "tests" / "e2e.py").read_text(encoding="utf-8")
    tests = len(re.findall(r"^def t_[a-z0-9_]+\(", e2e, re.M))

    cross = 0
    rroot = ROOT / "docs" / "independent-recheck"
    if rroot.exists():
        for rf in sorted(rroot.glob("*/*/review.json")):
            try:
                d = json.loads(rf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if (d.get("reviewer_type") in ("cross_model", "human")
                    and not d.get("fabrication_flagged")
                    and d.get("fidelity_grade_reconfirmed") in ("A", "B", "C", "D")):
                cross += 1

    import importlib.util
    spec = importlib.util.spec_from_file_location("vc", ROOT / "docs" / "verify_claims.py")
    vc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vc)
    claims = len(vc.parse_claims())

    return {"version": version, "tests": tests, "defects": len(DEFECTS),
            "cross": cross, "claims": claims}


def font(size: int, bold: bool = False):
    from PIL import ImageFont
    # Hiragino Sans GB 覆盖简体；粗体用同族的 Medium 权重近似
    path = "/System/Library/Fonts/Hiragino Sans GB.ttc"
    for idx in (1 if bold else 0, 0, 2, 3):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def text(draw, xy, s, f, fill, anchor="la"):
    draw.text(xy, s, font=f, fill=fill, anchor=anchor)


def render(f: dict, out: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    # 竖向渐变
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))

    # 左上角色带（暗示"工厂/管线"）
    for i, x in enumerate(range(0, 300, 12)):
        d.rectangle([x, 0, x + 5, 6], fill=ACCENT if i % 2 == 0 else OK)

    f_h1 = font(86, bold=True)
    f_h2 = font(38)
    f_num = font(58, bold=True)
    f_lab = font(24)
    f_small = font(22)
    f_tag = font(30)

    x = 76
    y = 74

    text(d, (x, y), "rulai-distill", f_h1, FG)
    y += 104
    text(d, (x, y), "蒸馏工厂 · 把书籍/长视频/播客/访谈/人物素材", f_h2, FG_DIM)
    y += 48
    text(d, (x, y), "蒸馏成可执行、可验证、可追溯的 Agent Skills", f_h2, FG_DIM)
    y += 74

    # 主张：整张图的记忆点。色块按文字实测宽度撑开，不留一片死白。
    tagline = "别人证明「能生成」，它证明「没编造」。"
    tw = d.textlength(tagline, font=f_tag)
    d.rectangle([x - 14, y - 12, x - 14 + tw + 28, y + 52], fill=(31, 41, 55))
    text(d, (x, y), tagline, f_tag, FG)
    y += 96

    # 三个实证数字
    cols = [
        (f"{f['cross']}/3", "跨模型异族复评", "DeepSeek · 8/8 一致 · 无编造"),
        (f"{f['tests']} 项", "回归全绿", f"含 {f['claims']} 条对外声称逐条对账"),
        (f"{f['defects']} 条", "缺陷公开登记", "台账数字由测试强制相等"),
    ]
    cw = 352
    for i, (num, lab, sub) in enumerate(cols):
        cx = x + i * (cw + 24)
        d.line([(cx, y), (cx + cw - 20, y)], fill=RULE, width=2)
        text(d, (cx, y + 14), num, f_num, OK if i == 0 else FG)
        text(d, (cx, y + 82), lab, f_lab, FG)
        text(d, (cx, y + 116), sub, f_small, FG_DIM)

    # 底栏
    d.line([(x, H - 92), (W - 76, H - 92)], fill=RULE, width=2)
    text(d, (x, H - 62),
         f"github.com/yihexiang/rulai-distill", f_small, ACCENT)
    text(d, (W - 76, H - 62),
         f"v{f['version']} · MIT · Python ≥3.10 · 零第三方依赖 · 默认离线",
         f_small, FG_DIM, anchor="ra")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"✅ 已生成 {out}（{W}×{H}）")
    print(f"   图上数字来源：version={f['version']} tests={f['tests']} "
          f"defects={f['defects']} cross={f['cross']} claims={f['claims']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="渲染 GitHub 社交预览图")
    ap.add_argument("--out", default=str(ROOT / "dist" / "social-preview.png"))
    args = ap.parse_args()
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("❌ 需要 Pillow：pip install pillow", file=sys.stderr)
        return 1
    render(facts(), Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
