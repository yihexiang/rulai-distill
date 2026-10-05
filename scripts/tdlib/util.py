# -*- coding: utf-8 -*-
"""tdlib.util — 公共基础设施：异常、输出、frontmatter 解析、路径安全、哈希、token 计量。

设计约束（全包适用）：
  * 零网络：本模块不 import 任何网络库。
  * 零动态执行：不使用 eval / exec / subprocess。
  * 零第三方依赖即可运行：PyYAML / tiktoken 均为可选，缺失时自动降级。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from pathlib import Path

MANIFEST_NAME = "BUILD_MANIFEST.json"
GRADE_ORDER = ["A", "B", "C", "D"]
VERSION = "1.1.0"
PKG_ROOT = Path(__file__).resolve().parent.parent.parent   # rulai-distill/
METHOD_DIR = PKG_ROOT / "methodology"
TEMPLATE_DIR = PKG_ROOT / "templates"
SCHEMA_DIR = PKG_ROOT / "schemas"

# --------------------------------------------------------------------------
# 异常与输出
# --------------------------------------------------------------------------


class ToolError(Exception):
    """所有预期内失败都走这里，保证用户看到的是人话而不是裸 traceback。"""

    def __init__(self, message: str, *hints: str):
        super().__init__(message)
        self.message = message
        self.hints = list(hints)


def die(msg: str, *hints: str, code: int = 1):
    print(f"❌ {msg}")
    for h in hints:
        print(f"   → {h}")
    raise SystemExit(code)


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def info(msg: str) -> None:
    print(f"   {msg}")


def step(msg: str) -> None:
    print(f"▸ {msg}")


def head(title: str) -> None:
    print(f"\n{title}\n" + "─" * max(8, len(title)))


# --------------------------------------------------------------------------
# 路径安全
# --------------------------------------------------------------------------

def safe_target(base: Path, rel: str) -> Path:
    """把 rel 限制在 base 内：拒绝绝对路径、URL 协议、.. 逃逸、符号链接。"""
    if not rel:
        raise ToolError("空路径")
    if os.path.isabs(rel) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", rel):
        raise ToolError(f"非法路径（绝对或带协议）：{rel}")
    base_r = base.resolve()
    cand = (base / rel).resolve()
    if cand != base_r and base_r not in cand.parents:
        raise ToolError(f"路径逃逸出根目录：{rel}")
    return cand


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------
# 哈希与时间
# --------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def now_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


# --------------------------------------------------------------------------
# frontmatter（优先 PyYAML，缺失时降级到内置最小解析器）
# --------------------------------------------------------------------------

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)


def _mini_yaml(block: str) -> dict:
    """解析 SKILL.md frontmatter 常用子集：标量、块标量(|/-)、一层嵌套、行内数组、列表。"""
    out: dict = {}
    cur_key = None
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        m = re.match(r"^([A-Za-z_][\w.\-]*):\s*(.*)$", raw.strip())
        if m and indent == 0:
            key, val = m.group(1), m.group(2).strip()
            cur_key = key
            if val in ("|", ">", "|-", ">-"):
                buf: list[str] = []
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.strip() and (len(nxt) - len(nxt.lstrip())) == 0:
                        break
                    buf.append(nxt.strip())
                    i += 1
                out[key] = "\n".join(buf).strip()
                continue
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                out[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
            elif val == "":
                j = i + 1
                nxt_indent, is_list = -1, False
                if j < len(lines) and lines[j].strip():
                    ni = len(lines[j]) - len(lines[j].lstrip())
                    if ni > 0:
                        nxt_indent = ni
                        is_list = lines[j].lstrip().startswith("- ")
                if nxt_indent > 0 and not is_list:
                    sub: dict = {}
                    while j < len(lines):
                        ln = lines[j]
                        if not ln.strip():
                            j += 1
                            continue
                        li = len(ln) - len(ln.lstrip())
                        if li < nxt_indent:
                            break
                        sm = re.match(r"^([A-Za-z_][\w.\-]*):\s*(.*)$", ln.strip())
                        if sm:
                            sub[sm.group(1)] = sm.group(2).strip()
                        j += 1
                    out[key] = sub
                    i = j
                    continue
                if is_list:
                    items: list = []
                    while j < len(lines):
                        ln = lines[j]
                        if not ln.strip():
                            j += 1
                            continue
                        li = len(ln) - len(ln.lstrip())
                        if li < nxt_indent or not ln.lstrip().startswith("- "):
                            break
                        items.append(ln.strip()[2:].strip().strip("'\""))
                        j += 1
                    out[key] = items
                    i = j
                    continue
                out[key] = None
            else:
                out[key] = val.strip("'\"")
        i += 1
    return out


def load_frontmatter(path: Path) -> tuple[dict, str]:
    """返回 (frontmatter dict, 正文)。文件不存在 / 非 UTF-8 抛 ToolError。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ToolError(f"文件不存在：{path}")
    except UnicodeDecodeError:
        raise ToolError(f"文件不是合法 UTF-8：{path}", "请用 UTF-8 重新保存")
    except IsADirectoryError:
        raise ToolError(f"期望文件但得到目录：{path}")
    except OSError as e:
        raise ToolError(f"读取失败：{path}（{e.strerror}）")

    fm = _FM_RE.match(text)
    if not fm:
        return {}, text
    block, body = fm.group(1), text[fm.end():]
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(block) or {}
        if not isinstance(data, dict):
            raise ToolError(f"frontmatter 不是键值结构：{path}")
        return data, body
    except ImportError:
        return _mini_yaml(block), body
    except ToolError:
        raise
    except Exception:
        return _mini_yaml(block), body


def dump_frontmatter(fm: dict, body: str) -> str:
    """把 dict + 正文序列化成带 frontmatter 的 markdown（不依赖 PyYAML）。"""
    lines = ["---"]

    def scalar(v) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v)
        if "\n" in s:
            return "|"
        return s

    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                lines.extend(f"  - {scalar(x)}" for x in v)
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for k2, v2 in v.items():
                lines.append(f"  {k2}: {scalar(v2)}")
        else:
            s = scalar(v)
            if s == "|":
                lines.append(f"{k}: |")
                lines.extend("  " + ln for ln in str(v).splitlines())
            else:
                lines.append(f"{k}: {s}")
    lines += ["---", ""]
    return "\n".join(lines) + body.lstrip("\n")


# --------------------------------------------------------------------------
# Markdown 链接
# --------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_SCHEME_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.\-]*:|#|mailto:)")


def iter_links(body: str):
    for m in _LINK_RE.finditer(body):
        raw = m.group(1).strip()
        if not raw:
            continue
        tgt = raw.split()[0]
        if _SCHEME_RE.match(tgt):
            continue
        yield tgt.split("#")[0]


# --------------------------------------------------------------------------
# token 计量（tiktoken 可选，缺失时降级为字符估算并明确标注）
# --------------------------------------------------------------------------

_ENC = {}
_ESTIMATE_RATIO = {"cjk": 1.0, "other": 0.35}  # 中文约 1 token/字，英文约 0.35 token/char


def has_tiktoken() -> bool:
    try:
        import tiktoken  # noqa: F401
        return True
    except ImportError:
        return False


def count_tokens(text: str, enc_name: str = "cl100k_base") -> int:
    """精确 token 数；无 tiktoken 时按字符类别估算（返回值标注为估算）。"""
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore
    except ImportError:
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        other = len(text) - cjk
        return int(cjk * _ESTIMATE_RATIO["cjk"] + other * _ESTIMATE_RATIO["other"])
    if enc_name not in _ENC:
        _ENC[enc_name] = tiktoken.get_encoding(enc_name)
    return len(_ENC[enc_name].encode(text))


def ngrams(text: str, n: int = 3) -> set:
    """字符 n-gram 集合（相似度计算用）。

    实测教训：算相似度**不能**用字符集合 Jaccard——英文句子常用字母天然重叠，
    两句无关的话会得 0.9+，导致正常内容被误判为重复删掉。
    统一放这里，供 transcript 去重 / research 去重 / lexindex 共用。
    """
    t = re.sub(r"[\s\W_]+", "", (text or "").lower())
    if not t:
        return set()
    if len(t) <= n:
        return {t}
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def token_source() -> str:
    return "tiktoken 精确计量" if has_tiktoken() else "字符估算（未安装 tiktoken，数值偏低）"


# --------------------------------------------------------------------------
# JSON 读写
# --------------------------------------------------------------------------

def read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError(f"文件不存在：{path}")
    except json.JSONDecodeError as e:
        raise ToolError(f"JSON 解析失败：{path}", f"{e.msg}（行 {e.lineno} 列 {e.colno}）")


def write_json(path: Path, data) -> None:
    ensure_dir(Path(path).parent)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ToolError(f"文件不存在：{path}")
    except UnicodeDecodeError:
        raise ToolError(f"不是合法 UTF-8：{path}")
    except OSError as e:
        raise ToolError(f"读取失败：{path}（{e.strerror}）")
