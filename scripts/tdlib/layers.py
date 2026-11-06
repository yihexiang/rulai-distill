# -*- coding: utf-8 -*-
"""tdlib.layers — 素材三层：把「可核原文」与「AI 观察」机械隔离（P1-a）。

## 为什么需要这个模块

长视频蒸馏里有两类文字长得几乎一样，性质却相反：

| 层 | 例子 | 能不能逐字回源 |
|---|---|---|
| L1 可核原文 | 平台字幕、本地 ASR 逐字稿、用户手抄原文 | ✅ 带时间戳，`source_locator` 可核 |
| L2 AI 观察 | 视觉理解稿、画面描述、屏幕文字归纳、OCR 摘要 | ❌ 是模型对画面的**理解性复述**，不是「视频里说过的话」 |

`verify-quotes` / `anchor` / `lint-quotes` 全部建立在 L1 上：逐字去语料里找，
找到才算 ANCHOR_HIT。若把 L2 混进 `--corpus`，anchor 会把 AI 生成的句子当成
「已核实的原文」，产出**假 ANCHOR_HIT**——核验链条从源头就断了，而且显示为绿。
这正是 #77 那类事故的形态（没有出处的词被伪装成核实过的），只是更隐蔽：
这次连「原文」本身都是模型编的。

所以隔离不能靠文档叮嘱，必须**机器可判、体检器硬失败**。

## 三层与标记约定

| 层 | 值 | 标记 | 可否作 `--corpus` / 引语出处 |
|---|---|---|---|
| L1 可核原文 | `verbatim` | 无（默认） | ✅ 唯一允许 |
| L2 AI 观察 | `ai-observation` | 必须带 `RULAI_LAYER: ai-observation` | ❌ `lint-quotes` 硬失败 |
| L3 用户提供/推断 | `user-supplied` | 建议带 `RULAI_LAYER: user-supplied` | ⚠️ 不自动算原文，按 claim-level 逐条标注 |

L2 产物**必须**在文件开头带一行（md/txt/JSONL 通用）：

    <!-- RULAI_LAYER: ai-observation | 禁止作为可核原文 / 引语出处 -->

JSONL 也可每行带 `"layer": "ai-observation"`。另外按**文件名**兜底：
`*.visual-notes.jsonl` / `*.ai-transcript.md` / `*.vision.md` / `multimodal-transcript*`
即使漏写标记也判 L2——防「忘了标记就混进去」。

## 诚实边界（不要写成「已全面拦截」）

本模块只能拦住**带约定标记、或用约定文件名**的 L2。一段既没标记、文件名也随意的
AI 生成文本，工具无从分辨——那是产出方/使用者的责任。

v1.12.0 起，`verify-quotes` / `anchor` / `lint-quotes` **三个核验器在库层共用
`guard()`**：绕过 `td.py` 直接调库函数也拦得住。剩余边界是「标记缺失且文件名随意」，
以及 L3 用户推断层需按 claim-level 逐条标注（工具不替人判断内容真伪）。
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import ToolError

LAYER_VERBATIM = 'verbatim'
LAYER_AI_OBSERVATION = 'ai-observation'
LAYER_USER_SUPPLIED = 'user-supplied'

AI_OBS_HEADER = '<!-- RULAI_LAYER: ai-observation | 禁止作为可核原文 / 引语出处 -->'
USER_HEADER = '<!-- RULAI_LAYER: user-supplied | 逐条标注 [原文]/[通法]/[本卡规则] -->'

# 只认「开头 4000 字符内、独立成行」的标记：正文里讨论这条规则不算标记，
# 否则把 media-pipeline.md 当语料的人会被误伤（假阳性比漏报更坏，见 lintquotes 纪律）。
_MARKER_RE = re.compile(
    r'^\s*(?:<!--|#|//|/\*)?\s*RULAI_LAYER\s*:\s*(ai-observation|user-supplied)\b',
    re.M)
_JSON_LAYER_RE = re.compile(r'"layer"\s*:\s*"ai-observation"')
_AI_FILENAME_HINTS = (
    'visual-notes', 'ai-transcript', 'vision-notes', '.vision.md',
    'multimodal-transcript', '.visual.md',
)
# 卡片里把 AI 观察层写成出处的形态。只认**产物文件名**，不认裸层名——
# 否则卡片里一句「AI 观察层禁作语料」的正当说明会被误判成违规。
_LOCATOR_RE = re.compile(
    r'(?:source_locator|出处|语料|来源|corpus)[^\n]{0,140}'
    r'(?:visual-notes|ai-transcript|vision-notes|multimodal-transcript|\.vision\.md)',
    re.I)


def detect_layer(text: str | None = None, name: str | None = None) -> str:
    """判定一份素材属于哪一层。返回 verbatim / ai-observation / user-supplied。"""
    if text:
        head = text[:4000]
        m = _MARKER_RE.search(head)
        if m:
            return (LAYER_AI_OBSERVATION if m.group(1) == 'ai-observation'
                    else LAYER_USER_SUPPLIED)
        if _JSON_LAYER_RE.search(head):
            return LAYER_AI_OBSERVATION
    if name:
        low = str(name).lower()
        if any(h in low for h in _AI_FILENAME_HINTS):
            return LAYER_AI_OBSERVATION
    return LAYER_VERBATIM


def is_ai_observation(text: str | None = None, name: str | None = None) -> bool:
    return detect_layer(text, name) == LAYER_AI_OBSERVATION


def find_violations(card_text: str,
                    corpus_texts: dict[str, str] | None = None) -> list[dict]:
    """找出「AI 观察层被当作可核原文 / 引语出处」的所有位置。

    返回 `[{where, line, why}]`；空列表表示未发现违规。
    检查三处：① 传入的 `--corpus` 语料（正文标记）；② 语料文件名兜底；
    ③ 卡片自身正文（被标成 L2、或 source_locator 指向 L2 产物）。
    """
    out: list[dict] = []
    why_corpus = (
        '该语料属于 AI 观察层（RULAI_LAYER: ai-observation）——它是模型对画面的'
        '理解性复述，不是可逐字回源的原文；喂给 anchor 会制造假 ANCHOR_HIT')
    for name, text in (corpus_texts or {}).items():
        if is_ai_observation(text, name):
            out.append({'where': f'--corpus {name}', 'line': 0, 'why': why_corpus})

    lines = card_text.splitlines()
    m = _MARKER_RE.search(card_text[:4000])
    if m and m.group(1) == 'ai-observation':
        ln = card_text[:m.start()].count('\n') + 1
        out.append({'where': f'卡片第 {ln} 行', 'line': ln,
                    'why': '卡片自身被标成 AI 观察层——它不该进入引语核验链'})
    for i, line in enumerate(lines, 1):
        if _LOCATOR_RE.search(line):
            out.append({'where': f'卡片第 {i} 行', 'line': i,
                        'why': 'source_locator / 出处指向 AI 观察层产物，'
                               '该产物不能作为逐字原文的出处'})
            break       # 同类只报一条，避免刷屏淹没真信号
    return out


def guard(card: Path | None, corpus_paths: list[Path]) -> None:
    """核验链入口守卫：任何一层命中 AI 观察层就**直接抛 ToolError**（硬阻断）。

    放在**库层**而不只是 CLI：绕过 `td.py` 直接调 `anchor.verify_file` /
    `evals.verify_quotes` / `anchor.load_corpora` 的调用方同样受保护。
    这是 P1-a 的 P2 收口——此前只有 `lint-quotes` 会拦，另两个核验器仍会把
    AI 观察稿当语料并产出假 ANCHOR_HIT。

    - `card` 传 None → 只查语料（`anchor.load_corpora` 拿不到卡片时用）；
    - `corpus_paths` 传空 → 只查卡片（`anchor.verify_file` 收到的是已切段语料，
      原始标记不在其中，故语料侧由 load_corpora 在切段前查）。
    - 语料只读**开头 4000 字符**：标记按约定必须在文件开头，3MB 逐字稿不必
      为了守卫再全文读一遍（`detect_layer` 自身也只认开头 4000 字符）。
    """
    card_text = ''
    if card is not None:
        card_text = Path(card).read_text(encoding='utf-8', errors='replace')
    corpus_texts: dict[str, str] = {}
    for p in corpus_paths:
        p = Path(p)
        corpus_texts[p.stem] = p.read_text(encoding='utf-8', errors='replace')[:4000]
    violations = find_violations(card_text, corpus_texts)
    if not violations:
        return
    where = '；'.join(v['where'] for v in violations)
    raise ToolError(
        f'素材分层违规（{where}）：AI 观察层被当作可核原文 / 引语出处 —— '
        '继续核验会产出假 ANCHOR_HIT，核验链从源头就断了',
        '把 AI 观察稿从 --corpus 里移除；可核原文只用平台字幕 / 本地 ASR 逐字稿',
        'AI 观察稿只能作检索 / 索引线索，产物须带 RULAI_LAYER: ai-observation 标记',
        'verify-quotes / anchor / lint-quotes 三个核验器共用本守卫；'
        '规则与剩余边界见 references/media-pipeline.md 3.5',
    )
