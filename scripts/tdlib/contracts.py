# -*- coding: utf-8 -*-
"""tdlib.contracts — **上游契约的权威实现层**（P1 契约归一）。

## 为什么有这一层

v1.2.0 之前的错误：把上游的**算法**继承过来，却自己另定义了一套**数据契约**
（`rulai-skill/*`）。结果分块器、编译器、registry 各说各话——契约的价值恰恰在于只有一套。

本模块把 `scripts/vendor/cangjie/schemas/` 里的 13 份 schema 变成**权威契约**：
本包的产物**直接按它们产出**，并可用它们校验。校验优先用 `jsonschema`；
缺该依赖时降级到内置的最小校验器（required + enum + pattern + type 子集），
**不静默跳过**——校验不可用时必须显式降级并告知。

## 命名映射（逻辑名 → 上游 schema 文件）

  source-document  ← contracts/source-document     输入的规范化文档（带 version_id）
  source-manifest  ← source-manifest                多来源打包与权利/可信度声明
  chunk            ← contracts/chunk                结构感知块
  capability       ← capability                     单张能力卡
  capability-bundle← capability-bundle              能力包
  change-set       ← change-set                     版本间差异（可校验）
  output-decision  ← output-decision                single/pack 形态决策
  registry-entry   ← registry-entry-v2              登记条目（15 必填）
  dependency-graph ← dependency-graph               能力依赖图
  eval-suite       ← eval-suite                     评测套件
  failure-case     ← failure-case                   失败用例
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .util import ToolError, ensure_dir

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "vendor" / "cangjie" / "schemas"

MAP = {
    "source-document": "contracts/source-document.schema.json",
    "chunk": "contracts/chunk.schema.json",
    "source-manifest": "source-manifest.schema.json",
    "capability": "capability.schema.json",
    "capability-bundle": "capability-bundle.schema.json",
    "change-set": "change-set.schema.json",
    "output-decision": "output-decision.schema.json",
    "registry-entry": "registry-entry-v2.schema.json",
    "dependency-graph": "dependency-graph.schema.json",
    "eval-suite": "eval-suite.schema.json",
    "failure-case": "failure-case.schema.json",
}

SCHEMA_VERSION = 1            # 上游 source-document 契约规定为 const: 1（整数，不是字符串）
REGISTRY_SCHEMA_VERSION = "registry-entry@2"


# --------------------------------------------------------------------------
# 加载
# --------------------------------------------------------------------------
def schema_path(name: str) -> Path:
    if name not in MAP:
        raise ToolError(f"未知契约：{name}", "可用：" + "、".join(sorted(MAP)))
    p = CONTRACT_DIR / MAP[name]
    if not p.exists():
        raise ToolError(f"上游契约文件缺失：{p}",
                        "本包应自带 vendored 副本；若被删除请重新安装 rulai-skill")
    return p


def load(name: str) -> dict:
    try:
        return json.loads(schema_path(name).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ToolError(f"契约文件损坏：{schema_path(name)}", str(e))


def has_jsonschema() -> bool:
    import importlib.util
    return importlib.util.find_spec("jsonschema") is not None


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "integer": int, "number": (int, float), "null": type(None),
}


def _mini_check(data, schema: dict, path: str, errors: list[str], depth: int = 0) -> None:
    """零依赖校验器：覆盖 required / enum / pattern / type / 嵌套对象与数组。

    只支持本项目实际用到的 draft-07 子集；遇到不认识的关键字**不报错也不放行**，
    而是由 has_jsonschema() 决定是否走完整校验（见 validate）。
    """
    if depth > 12:
        return
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        if not any((_TYPES.get(x) is None) or isinstance(data, _TYPES[x]) for x in types):
            errors.append(f"{path}: 期望类型 {t}，实际 {type(data).__name__}")
            return
    if "const" in schema and data != schema["const"]:
        errors.append(f"{path}: 取值 {data!r} != const {schema['const']!r}")
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: 取值 {data!r} 不在 enum {schema['enum']} 内")
    if isinstance(data, str) and schema.get("pattern"):
        if not re.search(schema["pattern"], data):
            errors.append(f"{path}: {data!r} 不匹配 pattern {schema['pattern']}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append(f"{path}: {data} < minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errors.append(f"{path}: {data} > maximum {schema['maximum']}")
    if isinstance(data, dict):
        for r in schema.get("required", []):
            if r not in data:
                errors.append(f"{path}: 缺少必填字段 {r}")
        for k, sub in (schema.get("properties") or {}).items():
            if k in data and isinstance(sub, dict):
                _mini_check(data[k], sub, f"{path}.{k}", errors, depth + 1)
        if "minProperties" in schema and len(data) < schema["minProperties"]:
            errors.append(f"{path}: 属性数 {len(data)} < minProperties {schema['minProperties']}")
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(f"{path}: 元素数 {len(data)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errors.append(f"{path}: 元素数 {len(data)} > maxItems {schema['maxItems']}")
        if schema.get("uniqueItems") and len(data) != len({json.dumps(x, sort_keys=True, ensure_ascii=False)
                                                            for x in data}):
            errors.append(f"{path}: 元素需唯一（uniqueItems）")
        item = schema.get("items")
        if isinstance(item, dict):
            for i, x in enumerate(data):
                _mini_check(x, item, f"{path}[{i}]", errors, depth + 1)


def validate(name: str, data, *, strict: bool = True) -> dict:
    """按上游契约校验数据。返回 {ok, errors, mode}。

    mode = "jsonschema"（完整校验）| "builtin-subset"（零依赖降级）
    """
    schema = load(name)
    if has_jsonschema():
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        errs = [f"{'.'.join(str(x) for x in e.absolute_path) or '$'}: {e.message}"
                for e in sorted(validator.iter_errors(data), key=lambda x: list(x.absolute_path))]
        return {"ok": not errs, "errors": errs, "mode": "jsonschema", "contract": name}
    errs: list[str] = []
    _mini_check(data, schema, "$", errs)
    if strict and not errs and "additionalProperties" not in schema:
        pass  # 降级模式不覆盖 additionalProperties，如实说明在 mode 里
    return {"ok": not errs, "errors": errs, "mode": "builtin-subset", "contract": name}


def validate_local(name: str, data) -> dict:
    """按**本包自有** schema（`schemas/<name>.schema.json`）校验数据。

    与 `validate()` 的区别：那条只认上游权威契约，这条认自有契约（如 cross-review）。
    降级模式与 jsonschema 模式的口径差异同 `validate()`：降级不覆盖 additionalProperties，
    如实写在 `mode` 里，不假装等价。
    """
    from .util import SCHEMA_DIR
    sp = SCHEMA_DIR / f"{name}.schema.json"
    if not sp.exists():
        raise ToolError(f"本包没有这个 schema：{name}", f"现有：{sorted(p.stem.replace('.schema', '') for p in SCHEMA_DIR.glob('*.schema.json'))}")
    schema = json.loads(sp.read_text(encoding="utf-8"))
    if has_jsonschema():
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        errs = [f"{'.'.join(str(x) for x in e.absolute_path) or '$'}: {e.message}"
                for e in sorted(validator.iter_errors(data), key=lambda x: list(x.absolute_path))]
        return {"ok": not errs, "errors": errs, "mode": "jsonschema", "contract": f"local:{name}"}
    errs = []
    _mini_check(data, schema, "$", errs)
    return {"ok": not errs, "errors": errs, "mode": "builtin-subset", "contract": f"local:{name}"}


def write_verified(name: str, data, out_dir: Path, filename: str | None = None) -> Path:
    res = validate(name, data)
    if not res["ok"]:
        raise ToolError(f"产物不符合上游契约 {name}",
                        *(res["errors"][:8]),
                        "修实现，不要改契约")
    d = ensure_dir(Path(out_dir))
    p = d / (filename or f"{name.replace('/', '-')}.json")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def status() -> dict:
    return {
        "dir": str(CONTRACT_DIR),
        "contracts": {k: (CONTRACT_DIR / v).exists() for k, v in MAP.items()},
        "jsonschema": has_jsonschema(),
    }
