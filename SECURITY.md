# 安全政策

## 支持范围

| 版本 | 状态 |
|---|---|
| 最新 minor（当前 v1.11.x） | ✅ 接受安全修复 |
| 更早的 minor | ❌ 不再修补，请升级 |

## 本项目的攻击面（如实说明，不夸大也不隐瞒）

**默认完全离线**：除 `td.py fetch-subtitle`（下载字幕，**默认 dry-run，须显式 `--execute`**）外，
本包所有命令都不发起任何外部请求，不读取 `~/.hermes/.env` 之外的用户配置文件。

已知的、**需要用户主动提供才会触发**的外部接触点：

| 接触点 | 触发条件 | 防护 |
|---|---|---|
| `fetch-subtitle --execute` | 用户显式传 URL 并加 `--execute` | 默认 dry-run；参数不经 shell |
| `cross_model_recheck.py`（可选脚本，非工具链一部分） | 用户主动运行，且提供 `DEEPSEEK_API_KEY` | 只读凭证、只向 `api.deepseek.com` 发请求；不落盘 key |
| `td.py upstream run <tool>` | 用户显式调用 | 以子进程执行 vendored 上游原件，**不经 shell**（列表参数） |

全仓有守卫 `t_no_dynamic_execution` 禁止 `os.system` / `shell=True` / 裸 `eval` / `exec`，
AST 判定而非文本匹配——所以"注入一条 shell 命令"这类攻击在本包内没有落点。

## 报告漏洞

请**不要**为安全漏洞开公开 issue。请通过下列任一方式私下联系维护者：

- GitHub Security Advisory（`gh advisories` 或仓库页 Security → Report a vulnerability）
- discussion 中私信维护者

请在报告中包含：

1. 受影响的版本与复现步骤；
2. 你实际运行的命令与输出（本项目的规矩：**无证据不立案**）；
3. 若与"某条声明与实际不符"相关，请指出是哪一条声明（`docs/CLAMES.md` 的 21 条声称之一，或 README 的边界说明）。

## 响应承诺

- 确认收到：**3 个工作日**内；
- 给出评估与修复计划或缓解措施：**14 天**内；
- 修复发布后，在 `CONSTRAINTS.md` 缺陷台账登记并附回归测试
  （本项目的纪律：**修了不登记 = 没修**）。

## 已知边界（非漏洞，但是设计取舍）

- PyYAML / tiktoken 缺失时自动降级到内置子集校验器，降级与完整校验**可能给出不同结论**；
  降级时会显式输出 `mode` 让使用者看见（这是有意的，不是疏漏）。
- 语料核验只能证明"它检查过的那一面"：`verify-quotes` 验存在、`anchor` 验段号归属、
  `lint-quotes` 验用字，三者都过 ≠ 内容正确。详见 README「诚实声明」第 7 条。
