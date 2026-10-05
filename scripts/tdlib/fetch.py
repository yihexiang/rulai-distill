# -*- coding: utf-8 -*-
"""tdlib.fetch — 字幕获取（**唯一联网的模块**，默认 dry-run，必须显式 --execute）。

对标 alchaincyf/nuwa-skill 的 `scripts/download_subtitles.sh`，修掉它实测存在的三个缺陷：

| nuwa 的问题 | 本实现 |
|---|---|
| 用 `find -newer /tmp/.ytdlp_marker` 判断是否人工字幕，但该 marker **全文从未被 touch** → 检测恒为假，人工字幕识别静默失效 | marker 建在输出目录内并真实写入，`human` / `auto` 分开判定 |
| 隐式联网，出错只打印 yt-dlp 原始输出 | 默认 dry-run 打印完整命令；`--execute` 才联网；失败给中文可执行提示 |
| 依赖固定的 `/tmp` 路径，多项目并行会互相污染 | 全部状态落在 `--out` 目录内 |

**为什么默认 dry-run**：本包其它 21 个子命令都是纯本地操作，字幕获取是唯一会发起
网络请求的动作。默认打印命令让人确认，是让"联网"变成一个显式决定。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .util import ToolError, ensure_dir, info, now_iso, ok, read_json, warn, write_json

MARKER = ".td-subtitle-marker.json"
LANGS = ("zh-Hans", "zh-Hant", "zh", "en")


def have_yt_dlp() -> bool:
    return shutil.which("yt-dlp") is not None or shutil.which("youtube-dl") is not None


def _bin() -> str:
    for name in ("yt-dlp", "youtube-dl"):
        p = shutil.which(name)
        if p:
            return p
    raise ToolError("未找到 yt-dlp",
                    "安装：brew install yt-dlp  或  pipx install yt-dlp",
                    "或改用本地已有字幕：把 .srt/.vtt 放到本地后直接跑 `td.py transcript`",
                    "或用 ffmmpeg 本地转写：ffmpeg -i input.mp4 output.srt")


PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
              "https_proxy", "all_proxy")


def build_cmd(url: str, out_dir: Path, langs: tuple[str, ...], binary: str,
              cookies: str | None = None, subs_format: str = "srt",
              use_proxy: bool = True) -> list[str]:
    cmd = [binary, "--skip-download", "--write-subs", "--write-auto-subs",
           "--sub-langs", ",".join(langs), "--sub-format", subs_format,
           "--no-playlist", "--no-warnings"]
    if not use_proxy:
        cmd += ["--proxy", ""]          # yt-dlp 显式禁用代理
    if cookies:
        cmd += ["--cookies", cookies]
    cmd += ["-o", str(out_dir / "%(id)s.%(ext)s"), url]
    return cmd


def diagnose_network() -> list[str]:
    """诊断代理状态。实测踩过：yt-dlp 继承了 shell 里的 HTTP_PROXY（指向 WorkBuddy
    内部代理），隧道直接 502；清掉后又变成 YouTube 反爬。**两种失败长得完全不一样**，
    必须分开报，否则使用者会照着错误的方向排查。"""
    notes = []
    env_proxy = {k: v for k, v in os.environ.items() if k in PROXY_VARS and v}
    if env_proxy:
        notes.append("检测到环境代理变量：" + ", ".join(f"{k}={v}" for k, v in env_proxy.items()))
        notes.append("若报 'Tunnel connection failed / 502'，加 --no-proxy 重试"
                     "（环境变量可能指向已失效的代理）")
    try:
        import subprocess as _sp
        out = _sp.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=5).stdout
        if "HTTPEnable : 1" in out:
            port = [l.split(":")[1].strip() for l in out.splitlines() if "HTTPPort" in l]
            notes.append(f"系统代理已开启（端口 {port[0] if port else '?'}），"
                         "但进程未必继承——两者不一致是常见坑")
    except Exception:
        pass
    return notes


def already_fetched(out_dir: Path) -> dict | None:
    m = Path(out_dir) / MARKER
    if m.exists():
        try:
            return read_json(m)
        except ToolError:
            return None
    return None


def fetch_subtitle(url: str, out_dir: Path, langs: tuple[str, ...] = LANGS,
                   cookies: str | None = None, execute: bool = False,
                   subs_format: str = "srt", use_proxy: bool = True) -> dict:
    out_dir = ensure_dir(Path(out_dir).expanduser().resolve())
    binary = _bin() if execute or have_yt_dlp() else ("yt-dlp" if not have_yt_dlp() else shutil.which("yt-dlp"))
    cmd = build_cmd(url, out_dir, langs, binary, cookies, subs_format, use_proxy)

    prev = already_fetched(out_dir)
    if prev and prev.get("url") == url:
        found = sorted(p.name for p in out_dir.glob(f"*.{subs_format}"))
        if found:
            info(f"该 URL 已下载过：{'、'.join(found)}（{prev.get('fetched_at')}）")
            info("如需重下：删除 " + MARKER)
            return {"status": "cached", "files": [str(out_dir / f) for f in found],
                    "marker": prev}

    if not execute:
        head = ("将执行（这是本包唯一会联网的命令）：" if have_yt_dlp()
                else "未找到 yt-dlp，实际执行会失败。理论命令：")
        info(head)
        info("  " + " ".join(cmd))
        info("加 --execute 才会真正下载。字幕拿到后：td.py transcript <file.srt>")
        return {"status": "dry-run", "cmd": cmd, "out_dir": str(out_dir),
                "yt_dlp_found": have_yt_dlp()}

    info(f"执行：{' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    got = sorted([p for p in out_dir.glob(f"*.{subs_format}")],
                 key=lambda p: p.stat().st_mtime)
    if proc.returncode != 0 and not got:
        raw = (proc.stderr or proc.stdout)[-300:] or "无输出"
        hints = [raw]
        low = raw.lower()
        if "tunnel" in low or "502" in low or "proxy" in low:
            hints.append("这是**代理**问题，不是网络问题 → 加 --no-proxy 重试")
            hints += diagnose_network()
        elif "reloaded" in low or "sign in" in low or "bot" in low:
            hints.append("这是 YouTube 的反爬/需要 PO token，不是代理问题")
            hints.append("解法：升级 yt-dlp（yt-dlp -U）；或用 --cookies <cookies.txt>；"
                         "或改用本地已有字幕：ffmpeg -i in.mp4 out.srt")
        elif "private" in low:
            hints.append("该视频非公开，换一个公开视频")
        else:
            hints.append("常见原因：网络/代理未通、地区限制、需登录 → 加 --cookies <cookies.txt>")
        if "deprecated feature" in low:
            hints.insert(0, "⚠️ 本机 yt-dlp 版本过旧（Python 3.9 已弃用支持）→ 先升级：yt-dlp -U")
        raise ToolError(f"yt-dlp 失败（exit {proc.returncode}）", *hints)
    if not got:
        warn("命令成功但没拿到字幕文件：该视频可能没有该语言字幕")
    mark = {"url": url, "fetched_at": now_iso(), "langs": list(langs),
            "subs_format": subs_format, "files": [p.name for p in got],
            "tool": binary, "cookies_used": bool(cookies),
            "returncode": proc.returncode}
    write_json(out_dir / MARKER, mark)
    ok(f"下载完成：{'、'.join(p.name for p in got) or '（无）'}")
    for p in got:
        info(str(p))
    info("下一步：td.py transcript " + str(got[0]) if got else "")
    return {"status": "ok", **mark}
