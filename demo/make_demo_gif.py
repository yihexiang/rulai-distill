#!/usr/bin/env python3
"""make_demo_gif.py — 把 demo 真跑输出录成终端风 GIF（推广资产）。

为什么要有这个脚本：README 与社交投放都需要一段 30 秒的「看得见的证据」。
手录屏不可复跑、也会随窗口大小漂移；本脚本从 `demo/demo-output.txt`
（`demo/demo.sh --ascii --no-pause` 的真跑产物）确定性重渲染，任何人重跑得到同一段 GIF。

设计取舍（都写在这里，免得下次困惑）：
- **网格化渲染**：Menlo 等宽 ASCII（1 格），Hiragino Sans GB 中文（2 格，实测字宽 20px < 24px
  不溢出），按 12px 格、26px 行高排版；超宽行按终端习惯**换行**（不截断——截断就是另一种
  「声称≠实际」）。
- **5 个 emoji 转写**：✅/❌ 用矢量勾/叉绘制（绿/红），🔍→◇、🎉→★、📋→≡、⚠→▲。
  其余字符逐字保留。转写只为在 GIF 里可渲染，**不改变任何命令与输出文本**。
- **变速不停内容**：长列表快过、结论行停留（步标题 0.55s / 判定行 0.95s / 普通行 0.22s），
  首尾各加停顿。**不删任何一行**——删了就不是实录。
- **平滑滚动 + 新行淡入**：窗口跟随内容底部缓动（每帧逼近 20%），最新三行渐显。
- 颜色走 GitHub Dark 终端配色，与仓库 README 的暗色主题一致。

用法：
    python3 demo/make_demo_gif.py                      # demo-output.txt → demo/demo.gif
    python3 demo/make_demo_gif.py --input x.txt --output y.gif --fps 12
依赖：Pillow + ffmpeg（PATH 中可得）。帧中间产物落在临时目录，跑完即清。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

# ── 排版常量 ────────────────────────────────────────────────────────────────
CELL = 9            # ASCII 格宽（px）；CJK 占 2 格
LINE_H = 20         # 行高（px）
PAD = 11            # 视口内边距
COLS = 92           # 每行格数（超宽则换行）
ROWS = 21           # 视口可见行数
FONT_ASCII = "/System/Library/Fonts/Menlo.ttc"
FONT_CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_SIZE = 15

# ── 配色（GitHub Dark 终端）────────────────────────────────────────────────
BG = (13, 17, 23)
FG = (201, 209, 217)
DIM = (139, 148, 158)
BLUE = (88, 166, 255)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
PURPLE = (210, 168, 255)

# ── emoji 转写：\ue001/\ue002 是内部标记，渲染时改画矢量勾叉 ────────────────
EMOJI_MAP = {
    "✅": "\ue001",   # 绿勾
    "❌": "\ue002",   # 红叉
    "🔍": "◇", "🎉": "★", "📋": "≡", "⚠": "▲",
}


def normalize(text: str) -> list[str]:
    """去变体选择符 + emoji 转写；逐行保留，不改内容。"""
    text = text.replace("\ufe0f", "")
    return ["".join(EMOJI_MAP.get(c, c) for c in ln) for ln in text.splitlines()]


def char_cells(c: str) -> int:
    if unicodedata.combining(c):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def wrap(line: str, cols: int = COLS) -> list[str]:
    """CJK 感知换行：宽字符不被劈开。"""
    out, cur, w = [], "", 0
    for c in line:
        cw = char_cells(c)
        if w + cw > cols and cur:
            out.append(cur)
            cur, w = "", 0
        cur += c
        w += cw
    out.append(cur)
    return out


def line_style(orig: str) -> tuple:
    s = orig.lstrip()
    if s.startswith(("━━━", "───")):
        return BLUE
    if orig.startswith("✅"):
        return GREEN
    if orig.startswith("❌"):
        return RED
    if "🎉" in orig:
        return PURPLE
    if orig.startswith(("注：", "注意：", "提示")) or orig.lstrip().startswith("·"):
        return DIM
    return FG


def dwell_frames(orig: str, fps: int) -> int:
    """该行停留几帧（不是秒——帧数才能精确控制总帧数，而帧数就是 GIF 体积）。

    下限 1 帧：129 行内容至少 129 帧，这是体积的地板；再要小只能减像素或减内容。
    8fps 下：步标题 2 帧 / 判定行 3 帧 / 其余 1 帧，总时长 ~20s。
    """
    s = orig.lstrip()
    if s.startswith("━━━"):
        return 2
    if orig.startswith(("✅", "❌")) or "判定" in orig or "🎉" in orig or "统计：" in orig:
        return 3
    return 1


# 二值化文本渲染：PIL 默认抗锯齿会在暗底上产生几十种中间色，GIF 量化后噪声很大
# （实测同样内容 5.8MB）。做法：把整行画进一张**底色为 BG 的临时图**，再用
# ImageChops.difference 求与 BG 的差异当掩码贴回主图——差异大于阈值的像素统一
# 染成该行颜色，于是每个字形只剩「前景色 + 底色」两种状态。
# 既更接近真终端的硬边字形，也让调色板只剩几种纯色、LZW 压缩率大幅上升。
# （试过 font.getmask2 逐字缓存，但它返回 ImagingCore 而非 Image，没有 .point。）
_BG_IMG_CACHE: dict[tuple, Image.Image] = {}

# 二值化阈值（0-255 查找表）：与底色差异 ≥40 的像素才算字形。
# 40 是经验值——再低会保留抗锯齿晕环（调色板颜色数上升、GIF 变大），
# 再高会吃掉细笔画的尾部（小字号下「。」「丶」首先消失）。
_THRESH_LUT = [255 if i >= 40 else 0 for i in range(256)]


def draw_row_binary(img: Image.Image, x0: int, y: int, piece: str, color: tuple,
                    f_ascii, f_cjk) -> None:
    if not piece:
        return
    width = sum(char_cells(c) for c in piece) * CELL
    if width <= 0:
        return
    tmp = Image.new("RGB", (width, LINE_H), BG)
    td = ImageDraw.Draw(tmp)
    x = 0
    for ch in piece:
        cw = char_cells(ch)
        if ch == "\ue001":
            _check(td, x, 1, color)
        elif ch == "\ue002":
            _cross(td, x, 1, color)
        elif ord(ch) < 128:
            td.text((x, 2), ch, font=f_ascii, fill=color)
        else:
            td.text((x, 2), ch, font=f_cjk, fill=color)
        x += cw * CELL
    key = (width, LINE_H)
    bg = _BG_IMG_CACHE.get(key)
    if bg is None:
        bg = Image.new("RGB", (width, LINE_H), BG)
        _BG_IMG_CACHE[key] = bg
    diff = ImageChops.difference(tmp, bg).convert("L")
    mask = diff.point(_THRESH_LUT)
    img.paste(tmp, (x0, y), mask)


def _check(d: ImageDraw.ImageDraw, x: int, y: int, color) -> None:
    d.line([(x + 2, y + 13), (x + 5, y + 16), (x + 10, y + 6)], fill=color, width=2)


def _cross(d: ImageDraw.ImageDraw, x: int, y: int, color) -> None:
    d.line([(x + 3, y + 6), (x + 9, y + 15)], fill=color, width=2)
    d.line([(x + 9, y + 6), (x + 3, y + 15)], fill=color, width=2)


def render(src: Path, out: Path, fps: int = 12) -> None:
    raw = src.read_text(encoding="utf-8")
    orig_lines = raw.splitlines()
    lines = normalize(raw)

    # 预排版：原始行 → (渲染行, 颜色)；换行展开
    laid: list[tuple[str, tuple]] = []
    per_line_rows: list[int] = []
    for o, l in zip(orig_lines, lines):
        color = line_style(o)
        pieces = wrap(l)
        per_line_rows.append(len(pieces))
        for p in pieces:
            laid.append((p, color))
    total_rows = len(laid)
    # 前 k 个原始行对应的渲染行数（含换行展开）
    cum = [0]
    for n in per_line_rows:
        cum.append(cum[-1] + n)

    # 时间轴：开头停顿（空屏 + 光标）+ 每原始行一个时段 + 结尾停顿（**停在最后内容上**）
    # 首版结尾停顿也传 -1，于是最后 1.8s 整屏空白——结论横幅根本没被看到，白录了
    spans = [(int(0.5 * fps), -1)]                    # (帧数, 原始行索引；-1=只显示光标)
    for i, ln in enumerate(orig_lines):
        spans.append((dwell_frames(ln, fps), i))
    spans.append((int(1.6 * fps), len(orig_lines) - 1))

    W = PAD * 2 + COLS * CELL
    H = PAD * 2 + ROWS * LINE_H
    f_ascii = ImageFont.truetype(FONT_ASCII, FONT_SIZE)
    f_cjk = ImageFont.truetype(FONT_CJK, FONT_SIZE)

    total_frames = sum(n for n, _ in spans)
    tmp = Path(tempfile.mkdtemp(prefix="demogif_"))
    try:
        fi = 0
        page_start = 0          # 当前页首行索引
        for frames, line_idx in spans:
            shown = cum[line_idx] if line_idx >= 0 else 0
            # 翻页：页满则清屏重开一页。
            # 为什么不用滚动：整屏上移 20px 会让每一帧都是全屏变化，GIF 的行式 LZW
            # 无法利用垂直位移，体积压在 3.3MB 下不来；分页后帧差分只剩「新出现的那
            # 一条 20px 带」，同样 132 行内容能降到 1MB 量级。内容一行不删。
            if shown > 0 and shown - page_start > ROWS:
                page_start = shown
            for _ in range(frames):
                img = Image.new("RGB", (W, H), BG)
                d = ImageDraw.Draw(img)
                if shown == 0:      # 开头停顿：画一个闪烁光标块
                    if (fi // 6) % 2 == 0:
                        d.rectangle([PAD, PAD + 3, PAD + 7, PAD + 18], fill=FG)
                for row in range(page_start, min(shown, page_start + ROWS)):
                    piece, color = laid[row]
                    y = PAD + (row - page_start) * LINE_H
                    draw_row_binary(img, PAD, y, piece, color, f_ascii, f_cjk)
                img.save(tmp / f"f{fi:04d}.png")
                fi += 1

        out.parent.mkdir(parents=True, exist_ok=True)
        pal = tmp / "pal.png"
        # -framerate 必须给：图片序列默认按 25fps 解读，缺了它下游 fps 滤镜会按比例
        # **丢帧**（239 帧被丢成 86 帧，26.5s 塌成 9.5s——录了但播快了近 3 倍）
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-framerate", str(fps), "-i", str(tmp / "f%04d.png"),
                        "-vf", f"palettegen=max_colors=16",
                        str(pal)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-framerate", str(fps), "-i", str(tmp / "f%04d.png"),
                        "-i", str(pal),
                        "-lavfi", f"[0:v][1:v]paletteuse=dither=none",
                        str(out)], check=True)
        print(f"✅ GIF 已生成：{out}")
        print(f"   {total_rows} 渲染行 / {total_frames} 帧 / {fps}fps / {W}x{H} / "
              f"{out.stat().st_size/1024/1024:.2f} MB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(ROOT / "demo" / "demo-output.txt"))
    ap.add_argument("--output", default=str(ROOT / "demo" / "demo.gif"))
    ap.add_argument("--fps", type=int, default=12)
    a = ap.parse_args()
    src = Path(a.input)
    if not src.exists():
        print(f"❌ 找不到输入 {src}；先跑 bash demo/demo.sh --ascii --no-pause > demo/demo-output.txt")
        return 1
    render(src, Path(a.output), a.fps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
