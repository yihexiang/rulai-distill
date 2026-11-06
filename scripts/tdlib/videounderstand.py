# -*- coding: utf-8 -*-
"""tdlib.videounderstand — 视频理解「授权前披露单」生成器（P1-b）。

## 这是什么

**不是**视频理解执行器，**永不联网、永不上传**。它把「假如你决定调用 LongCat / 豆包
做视觉理解」的隐私代价、数据流向与成本估算，在**你授权之前**摊开成一份可留证的
文字 / JSON。真正的调用必须由 Agent 侧在你显式同意后手工完成。

## 为什么不做 --execute

LongCat / 豆包的 `video_url` 只收公网 URL，本地文件必须先发布到第三方托管。
社区方案用的 Uguu 临时托管**约 3 小时自动过期、期间公网可访问、无法提前删除**——
这是一次**不可撤回**的数据外传。把它做成 CLI 里的一个 flag，等于让「一次高风险
决定」退化成「顺手加个参数」。所以本模块连网络库都不 import（回归
`t_video_understand_zero_network` 用 AST 钉住），「零网络」是可机械验证的性质，
不是一句承诺。

## 诚实边界（每一份披露单都会打印）

- 单帧 / 单段 token 消耗、缓存命中率、长视频截断行为 **全部未实测**；下面的费用是
  按显式假设常量算的**规划估算**，不是报价。
- 单价默认取 LongCat 官方 API 文档 2026-11 查得的 ¥2/M 输入 · ¥8/M 输出 ·
  ¥0.04/M 缓存命中；社区文章按 755 万 token ≈ ¥23 反推约 ¥3/M。**两者不一致、
  均未复核账单** → 用 `--price-in / --price-out / --price-cache` 覆盖。
- 本模块不验证引擎可用性、不探测网络、不读取代理环境变量、不读取视频内容。
- 只 `stat` 文件大小；**不放时间戳**，保证相同输入两次输出完全一致（R5）。
"""
from __future__ import annotations

import math
from pathlib import Path

from . import layers

ENGINES = ('longcat', 'doubao', 'none')
UPLOAD_TARGETS = ('uguu', 'self-hosted', 'none')
VISION_MODES = ('agent-slices', 'keyframes', 'full')

# 官方 API 文档口径（2026-11 查得，未复核账单）
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_VIDEO_SECONDS = 3600
SLICE_SECONDS = 600

# 以下全部是**估算假设，未实测**；改口径只需改这里，披露单会自动带上新说明。
TOK_IN_PER_SLICE = 1800
TOK_OUT_PER_SLICE = 400
TOK_IN_PER_KEYFRAME = 800
TOK_OUT_PER_KEYFRAME = 150
KEYFRAME_INTERVAL_SECONDS = 30
TOK_IN_PER_MIN_FULL = 2500
TOK_OUT_PER_SLICE_FULL = 300

PRICE_SOURCE = (
    'LongCat 官方 API 文档（2026-11 查得）：¥2/M 输入 · ¥8/M 输出 · ¥0.04/M 缓存命中；'
    '社区文章按 755 万 token ≈ ¥23 反推约 ¥3/M。两者不一致、均未复核账单，'
    '以官方账单为准；可用 --price-* 覆盖')

ENDPOINTS = {
    'longcat': 'api.longcat.chat（OpenAI 兼容端点，仅披露，不调用）',
    'doubao': 'Volcano Ark / 豆包视觉理解（仅披露，不调用）',
    'none': '未选择视觉引擎（纯本地路线）',
}

UPLOAD_DISCLOSURE = {
    'uguu': ('LongCat / 豆包的 video_url 只收公网 URL，本地文件必须先上传到第三方。'
             'Uguu 临时公网托管约 3 小时自动过期、期间任何拿到链接的人可访问、'
             '无法提前删除 —— 这是一次不可撤回的数据外传。'),
    'self-hosted': ('自托管同样要求公网可达；托管方、留存时间与删除责任由你承担，'
                    '本工具不代管也不验证。'),
    'none': ('未提供公网 URL → 视觉引擎无法调用。这是最安全的默认：'
             '走本地 Whisper / 平台字幕（media-pipeline.md 3.1），文件不出机器。'),
}


def _human_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f'{n / 1024 ** 3:.2f} GiB'
    if n >= 1024 ** 2:
        return f'{n / 1024 ** 2:.1f} MiB'
    return f'{n / 1024:.1f} KiB'


def estimate(duration_seconds: float | None, mode: str, enabled: bool,
             price_in: float, price_out: float) -> dict:
    """给出**规划估算**（不是报价）。缺时长或引擎关闭时不编数字。

    三条硬规矩：① 没给 `--duration-seconds` 就不给 token / 费用（不编数字）；
    ② engine=none 或 upload_to=none → 0 token / ¥0；③ 每条假设都写进 assumptions。
    """
    base = {
        'kind': 'planning-estimate-not-a-quote',
        'mode': mode,
        'input_tokens': None,
        'output_tokens': None,
        'cost_cny': None,
        'assumptions': [],
    }
    if not enabled:
        base['note'] = ('未启用视觉引擎（--engine none 或 --upload-to none）：'
                        '0 token / ¥0，仅本地路线')
        base['input_tokens'] = 0
        base['output_tokens'] = 0
        base['cost_cny'] = 0.0
        return base
    if duration_seconds is None:
        base['note'] = ('未提供 --duration-seconds → 不给 token / 费用估算。'
                        '不是遗漏，是拒绝在缺输入时编数字；隐私披露仍然完整给出')
        return base
    d = max(0.0, float(duration_seconds))
    if mode == 'agent-slices':
        n = math.ceil(d / SLICE_SECONDS) if d else 0
        tin, tout = n * TOK_IN_PER_SLICE, n * TOK_OUT_PER_SLICE
        base['assumptions'].append(f'每 {SLICE_SECONDS}s 一段，共 {n} 段')
        base['assumptions'].append(f'假设每段输入 {TOK_IN_PER_SLICE} / 输出 {TOK_OUT_PER_SLICE} token')
    elif mode == 'keyframes':
        n = math.ceil(d / KEYFRAME_INTERVAL_SECONDS) if d else 0
        tin, tout = n * TOK_IN_PER_KEYFRAME, n * TOK_OUT_PER_KEYFRAME
        base['assumptions'].append(f'每 {KEYFRAME_INTERVAL_SECONDS}s 一帧，共 {n} 帧')
        base['assumptions'].append(f'假设每帧输入 {TOK_IN_PER_KEYFRAME} / 输出 {TOK_OUT_PER_KEYFRAME} token')
    else:      # full
        mins = math.ceil(d / 60) if d else 0
        n = math.ceil(d / SLICE_SECONDS) if d else 0
        tin, tout = mins * TOK_IN_PER_MIN_FULL, n * TOK_OUT_PER_SLICE_FULL
        base['assumptions'].append(f'完整视频按分钟计，共 {mins} 分钟')
        base['assumptions'].append(f'假设每分钟输入 {TOK_IN_PER_MIN_FULL} token / 每 {SLICE_SECONDS}s 输出 {TOK_OUT_PER_SLICE_FULL} token')
    cost = tin / 1_000_000 * price_in + tout / 1_000_000 * price_out
    base.update({
        'input_tokens': tin,
        'output_tokens': tout,
        'cost_cny': round(cost, 4),
        'assumptions': base['assumptions'] + [
            f'单价 ¥{price_in}/M 输入 · ¥{price_out}/M 输出（可用 --price-* 覆盖）',
            '缓存命中率未知，未计入缓存价；长视频是否截断未实测',
        ],
        'note': '规划估算，非报价：单帧/单段 token 消耗与截断行为全部未实测，以官方账单为准',
    })
    return base


def plan(video: Path, *, duration_seconds: float | None = None,
         engine: str = 'longcat', upload_to: str = 'uguu',
         vision_mode: str = 'agent-slices',
         price_in: float = 2.0, price_out: float = 8.0,
         price_cache: float = 0.04) -> dict:
    """生成披露单。**只读 stat，不读内容、不联网**；输出不含时间戳（R5 一致性）。"""
    if engine not in ENGINES or upload_to not in UPLOAD_TARGETS or vision_mode not in VISION_MODES:
        raise ValueError('engine / upload_to / vision_mode 取值非法')
    size = video.stat().st_size
    enabled = engine != 'none' and upload_to != 'none'
    warnings: list[str] = []
    if size > MAX_VIDEO_BYTES:
        warnings.append(f'文件 {_human_size(size)} 超出官方单视频 100MB 上限（文档口径）')
    if duration_seconds is not None and duration_seconds > MAX_VIDEO_SECONDS:
        warnings.append(f'时长 {duration_seconds}s 超出官方 <3600s 上限（文档口径）')
    if duration_seconds is None and enabled:
        warnings.append('未给 --duration-seconds：无法核对时长上限，也不给费用估算')
    return {
        'schema': 'rulai-distill/video-understand-plan@1',
        'video': str(video),
        'video_size_bytes': size,
        'video_size_human': _human_size(size),
        'duration_seconds': duration_seconds,
        'engine': engine,
        'endpoint_disclosure': ENDPOINTS[engine],
        'upload_to': upload_to,
        'vision_mode': vision_mode,
        'price': {'in_per_million_cny': price_in,
                  'out_per_million_cny': price_out,
                  'cache_hit_per_million_cny': price_cache},
        'price_source': PRICE_SOURCE,
        'estimate': estimate(duration_seconds, vision_mode, enabled, price_in, price_out),
        'limit_warnings': warnings,
        'privacy_disclosure': UPLOAD_DISCLOSURE[upload_to],
        'disclosures': [
            '隐私：私有 / 涉密 / 未授权素材禁止上传到公网托管；'
            '--upload-to none --engine none 是唯一不出机器的路线',
            '成本：上表是规划估算，单价两种口径不一致且未复核账单；'
            '单帧 token 消耗与长视频截断行为未实测',
            '分层：视觉理解稿属 L2 AI 观察，禁作引语出处 / --corpus；'
            'lint-quotes 会硬失败（见 media-pipeline.md 3.5）',
        ],
        'layer_contract': {
            'L1': {'value': layers.LAYER_VERBATIM,
                   'use': '平台字幕 / 本地 ASR 逐字稿；唯一可作 --corpus 与 source_locator'},
            'L2': {'value': layers.LAYER_AI_OBSERVATION,
                   'marker': layers.AI_OBS_HEADER,
                   'use': '视觉理解稿；只作检索/索引线索，禁作引语出处'},
            'L3': {'value': layers.LAYER_USER_SUPPLIED,
                   'marker': layers.USER_HEADER,
                   'use': '人工笔记 / 通法 / 本卡规则，按来源状态逐条标注'},
        },
        # 下面三个字段是给回归与审计看的：零网络是可验证的结构性质，不是承诺
        'network_calls': 0,
        'upload_performed': False,
        'execute_supported': False,
        'honest_boundaries': [
            '本模块不验证引擎可用性、不探测网络、不读取代理环境变量、不读取视频内容',
            'v1.12.0 起三个核验器共用 layers.guard()，但只认带约定标记 / 约定文件名'
            '的 AI 观察稿；标记缺失且文件名随意时无从分辨',
            'L3 用户提供 / 推断层需按 claim-level 逐条标注，工具不替人判断内容真伪',
        ],
    }


def render(p: dict) -> str:
    """渲染人类可读披露单。措辞一律用「拟 / 假如」，不写成已发生。"""
    est = p['estimate']
    lines = [
        '【授权前披露单】本命令不会上传任何文件、不发起任何网络请求',
        '──────────────────────────────────────────────',
        f"本地素材   : {p['video']}",
        f"文件大小   : {p['video_size_human']}（实测 stat，未读取内容）",
        f"时长       : {p['duration_seconds'] if p['duration_seconds'] is not None else '未提供 --duration-seconds'}",
        f"拟用引擎   : {p['engine']} · {p['endpoint_disclosure']}",
        f"视觉模式   : {p['vision_mode']}",
        f"拟上传目标 : {p['upload_to']}",
        '',
        '⚠️  隐私（必须先读）',
        f"   {p['privacy_disclosure']}",
        '   仅适用于你愿意公开的视频；私有 / 涉密 / 未授权素材禁止走这条路。',
        '',
        '📋 成本（规划估算，不是报价）',
        f"   单价口径 : {p['price_source']}",
    ]
    for a in est['assumptions']:
        lines.append(f"   假设     : {a}")
    if est['input_tokens'] is None:
        lines.append('   token/费用: 未给时长，不给估算（拒绝在缺输入时编数字）')
    else:
        lines.append(f"   token    : 输入 {est['input_tokens']:,} / 输出 {est['output_tokens']:,}")
        lines.append(f"   费用估算 : ≈ ¥{est['cost_cny']:.4f}（{est['note']}）")
    lines += [
        '',
        '🧱 产物分层契约（写进 media-pipeline.md 3.5）',
        f"   L1 {p['layer_contract']['L1']['value']:<16s} {p['layer_contract']['L1']['use']}",
        f"   L2 {p['layer_contract']['L2']['value']:<16s} {p['layer_contract']['L2']['use']}",
        f"       标记：{p['layer_contract']['L2']['marker']}",
        f"   L3 {p['layer_contract']['L3']['value']:<16s} {p['layer_contract']['L3']['use']}",
        '',
        '✅ 本命令实际做了什么',
        f"   network_calls = {p['network_calls']} / upload_performed = "
        f"{str(p['upload_performed']).lower()} / execute_supported = "
        f"{str(p['execute_supported']).lower()}",
        '   仅读取文件大小；未读取视频内容、未读取代理环境变量、未探测网络。',
    ]
    if p['limit_warnings']:
        lines += ['', '⚠️  上限警示']
        lines += [f'   · {w}' for w in p['limit_warnings']]
    lines += ['', '三条必读披露']
    lines += [f'   {i}. {d}' for i, d in enumerate(p['disclosures'], 1)]
    lines += ['', '诚实边界（不要把本披露单当成「已核验」）']
    lines += [f'   · {b}' for b in p['honest_boundaries']]
    lines += ['', '→ 是否调用外部引擎，由你在读完以上披露后显式决定；本命令到此为止。']
    return '\n'.join(lines)
