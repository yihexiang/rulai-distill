# -*- coding: utf-8 -*-
"""tdlib.defects — 本包自身的失败用例集（上游 failure-case 契约）。

为什么要把自己的缺陷写成契约对象：
`CONSTRAINTS.md` 的缺陷台账是**给人读的**，这里是把同一批缺陷写成**机器可校验**的
failure-case —— 每条都含"当时怎么错的 / 应该是什么 / 严重级 / 归属类别 / 计划动作"。
新发现的缺陷必须同时进两个地方，否则 `t_defect_regression_ledger` 会红。

严重级判定（不凭感觉）：
  critical  让结论反向（假阴性/假阳性会误导决策）
  major     让能力不可用或误导使用者
  minor     表述/格式层面
"""
from __future__ import annotations

from .evals import failure_case

DEFECTS = [
    ("td.py validate", "对上游 cangjie 产物报 2 条假阳性（E 段标题、source_book）",
     "只认 `E — Execution` 与 `source_locator`", "双语段标题与 source_book/chapter 都应被接受",
     "minor", "structure_gap", "交叉互评时发现；已改为双语正则 + 多键溯源",
     ["t_validate_upstream_format"]),
    ("td.py validate", "要求人物卡有 E 段（带显式步骤）",
     "对人物卡报『未发现 E — Execution 段』", "人物卡模板禁止显式步骤，不应要求 E 段",
     "major", "structure_gap", "与 PERSONA 模板自相矛盾", ["t_persona_no_e_section"]),
    ("tdlib.evals.score_suite", "诱饵通过率误报 0%、FP=2",
     "把 Agent 返回的字符串 \"none\" 当成有效 slug", "none/null/不适用 应归一化为不触发",
     "critical", "eval_gap", "真实盲测（sample-bundle）首次判分即暴露", ["t_answer_normalization"]),
    ("tdlib.chunking._cjk_bigrams", "英文查询 precision@10 仅 0.22，单词 cost 命中 816 块",
     "把英文逐字母拆成 c o s t", "英文整词入库，仅 CJK 做 bigram", "critical", "tool_gap",
     "tests/bench_index.py 对照基准首次运行", ["t_bigram_tokenizer"]),
    ("tdlib.chunking._cjk_bigrams", "中文查询返回空串",
     "CJK 缓冲区在追加当前字之前就 flush", "先累积再结算 bigram", "critical", "tool_gap",
     "修上一个 bug 时引入，方向相反", ["t_bigram_tokenizer", "t_lexindex_both_scripts"]),
    ("tdlib.evals.verify_quotes", "18 条引语里 16 条假阴性",
     "只截取引用编号【第N条】之前的窗口", "引号在编号之后，应向后取窗", "critical", "eval_gap",
     "卡片作者按『日期+编号+引语』书写，核验方向反了", ["t_verify_quotes_direction"]),
    ("tdlib.evals.verify_quotes", "跨引用错配：把下一条的引语算到本条",
     "固定 320 字窗口", "窗口止于下一个引用", "major", "eval_gap", "同上",
     ["t_verify_quotes_direction"]),
    ("tdlib.evals.verify_quotes", "17144 条语料只匹配到 27 条表头",
     "表头正则 `[^]]*】` 在超长文本上退化", "用 `【第N条 |` 定位 + 位置切片", "critical", "tool_gap",
     "马斯克 3.3MB 语料", ["t_verify_quotes_direction"]),
    ("tdlib.research.merge_research", "2/6 车道缺失被『一手占比 100%』掩盖",
     "占比只按幸存条目计算", "必须同时输出车道覆盖审计，缺失车道显式标注", "major", "eval_gap",
     "马斯克人物蒸馏", ["t_research_lane_coverage"]),
    ("tdlib.chunking 缓存键", "改了分块算法仍命中旧缓存",
     "缓存键只用 (source_sha256, max_chars)", "键须含实现版本与契约版本", "major", "tool_gap",
     "对照上游 cangjie_common.deterministic_cache_key 时发现", ["t_cache_versioning"]),
    ("tdlib.contracts 降级校验器", "jsonschema 判不合规、降级判合规，结论相反",
     "内置校验器不认识 const", "降级校验须覆盖 const，并显式输出 mode", "critical", "eval_gap",
     "schema_version 被我写成字符串时，降级放行、完整校验拦下", ["t_contract_list"]),
    ("tdlib.chunking 契约产出", "content_hash 格式不合契约",
     "写成裸 hex", "契约要求 sha256:<hex>", "major", "structure_gap", "契约层当场拒绝落盘",
     ["t_contract_source_document"]),
    ("tdlib.publish registry", "registry 条目塞了契约外字段",
     "额外写 fidelity/source/bundle_version", "registry-entry-v2 是 additionalProperties:false，"
     "本包信息旁挂 _td-meta.json", "major", "structure_gap", "契约层当场拒绝",
     ["t_contract_registry_entry"]),
    ("tests/e2e.py 自身", "record_sheet 函数被字符串切片替换整段吞掉",
     "用切片做代码替换，未做结构校验", "代码编辑后必须跑守卫测试", "critical", "tool_gap",
     "P2 改造 eval-suite 时；当时被另一个更早的失败遮住", ["t_cli_handlers_intact"]),
    ("tdlib.transcript.dedupe", "英文字幕被误删：15 条 cue 掉了 2 条",
     "用字符集合 Jaccard 算相似度，英文常用字母天然重叠", "用字符 3-gram Jaccard", "critical",
     "tool_gap", "P3 视频管线验证（自制 SRT 样本）", ["t_transcript_dedupe_precision"]),
    ("tdlib.transcript.build_transcript", "cue 级时间戳引用被判『语料中不存在』",
     "逐字稿只存段落起点，不存 cue 明细", "json 里保留 cues（index/start_ms/text）",
     "critical", "structure_gap", "P3 视频管线验证", ["t_verify_quotes_timestamp"]),
    ("tdlib.evals.verify_quotes", "视频/播客来源的卡片完全无法自检",
     "核验器只认【第N条】定位，不认 [HH:MM:SS.ss]", "支持时间戳定位并入 cue 级索引",
     "critical", "eval_gap", "P3 同上", ["t_verify_quotes_timestamp"]),
    ("tdlib.evals.verify_quotes", "时间戳引用串到下一条引语",
     "窗口未止于下一个时间戳引用", "窗口边界与【第N条】一致", "major", "eval_gap",
     "同类错误第 2 次（上次是固定 320 字窗口）", ["t_verify_quotes_timestamp"]),
    ("tdlib.evals.verify_quotes", "卡片排版『引语在前、时间戳在后』时必然错配",
     "只向前取窗", "前后两个窗口都取", "major", "eval_gap", "P3 同上", ["t_verify_quotes_timestamp"]),
    ("tdlib.evals._index_by_timestamp", "cue 索引加载不上",
     "with_suffix 只替换最后一段后缀 → x.transcript.transcript.json",
     "显式按文件名去后缀拼接", "major", "tool_gap", "P3 同上", ["t_verify_quotes_timestamp"]),
    ("tdlib.evals._index_by_timestamp", "真实 TED 字幕 5/6 条引语判成核不到",
     "索引 cue 优先，段落起点只映射到 cue 第一句", "段落优先、cue 补充", "critical",
     "tool_gap", "P3 真实素材（TED 逐字稿）", ["t_verify_quotes_real_transcript"]),
    ("tdlib.evals._norm_frag", "同一句话因破折号形态不同判成核不到",
     "SRT 用 --、卡片用 em dash，未归一", "em/en dash 与连续连字符统一", "major",
     "eval_gap", "P3 同上", ["t_verify_quotes_real_transcript"]),
    ("tdlib.evals.verify_quotes", "核验报告自相矛盾：verified=6 但 quotes_checked=0",
     "时间戳型引用未计入统计字段", "refs_by_kind 分离统计并合并总数", "minor",
     "eval_gap", "TED 视频卡 FIDELITY 评分时被抓出", ["t_verify_quotes_timestamp"]),
    ("能力卡撰写（我）", "把讲者经历编成『找人代写论文』",
     "凭合理想象补全，未回原文核对", "A1 段所有事实句必须能回逐字稿定位", "critical",
     "structure_gap", "FIDELITY 硬性核查（要求回原文点名）", []),
    ("tests/e2e.py 自身", "t_trigger_split_metrics 里期望值按旧字段写，导致 KeyError",
     "契约改造后测试仍读 suite['cases']", "测试与实现同轮切换字段", "minor", "eval_gap",
     "P2 eval-suite 改造期间", []),
    ("主 Agent 判断", "把 #10581 误判为『编号引错』并写进评分指令",
     "未查证就断言存在缺陷", "下结论前必须回原始数据核验", "critical", "eval_gap",
     "同一 tweet_id 在该数据集有两条近重复记录，我误判成只有一条", []),
    # ── 第五轮前夜：一次「引用 44 个但只核到 3 条」的误判（#31~#39）──
    ("verify_quotes 工具", "TED 卡报『引用 44 个，实际核验引语 3 条』，我一度判定为窗口收紧导致漏检",
     "把『统计口径失真』误读成『漏检』，方向就错了",
     "引用数 ≠ 核验数时，先逐条列出每个引用的归宿证明差额去向，再谈漏检",
     "critical", "eval_gap",
     "逐条打印 44 个引用的上下文后，真相是 7 条真引语 + 37 条表格定位锚点，"
     "工具把后者静默 continue 掉了（#32）", ["t_verify_quotes_accounting"]),
    ("verify_quotes 工具", "长引语（216~248 字符）整条核不到",
     "_WINDOW_CAP=200 把引语切成半句，「(.+?)」缺闭合符匹配失败",
     "窗口约束只能有一套：已有逻辑行边界就别再叠固定字符上限（#31）",
     "critical", "eval_gap", "TED 卡 38/44 个引语的上一行超过 200 字符",
     ["t_verify_quotes_accounting"]),
    ("verify_quotes 工具", "只认 `「」` 不认英文直引号 `\"`",
     "引号形态假设过窄；中文卡片两种引号混用是常态",
     "引语抓取必须同时支持 `「」` / `\"…\"`（#34）",
     "major", "eval_gap", "`讲者原话是 \"That's one box for every week of a 90-year life.\"` 被记成无引语",
     ["t_verify_quotes_accounting"]),
    ("verify_quotes 工具", "英文语料卡片里 10 条中文「」被判 unverified，verdict 永远 fail",
     "把作者自己的中文行文当成了来源引语",
     "引语语言必须与语料一致；但**只在表格/出处标注里过滤**，"
     "不能把「中文引语在英文语料里不存在」这种真问题的检出能力一起丢掉（#35/#37）",
     "critical", "eval_gap",
     "第一版过滤太激进，回归测试 t_verify_quotes_timestamp 直接挂掉（真问题被降级成 pass）",
     ["t_verify_quotes_accounting"]),
    ("verify_quotes 工具", "更正记录里写的 `[00:02:27.20]` 被当成真实引用去核，产生假失败",
     "元信息（front matter / 代码块 / 更正记录里提到的 ts）与引用未区分",
     "**同一类问题连犯三次**才动手修卡片措辞——治标。必须在工具侧挖空非引用区域（#36）",
     "major", "eval_gap",
     "第一次改卡片、第二次又冒出来、第三次才悟到要动工具", ["t_verify_quotes_accounting"]),
    ("verify_quotes 工具", "为解决跨 cue 引语而无条件开邻接窗口 → 引语串到隔壁 cue 判 pass",
     "邻接窗口没有开启条件",
     "邻接窗口**只在引语于当前 cue 处被截断时**才开（#38）", "critical", "eval_gap",
     "回归测试 D 用例直接抓到：00:00:05.50 的引语被判核到 00:00:20.00",
     ["t_verify_quotes_accounting"]),
    ("verify_quotes 工具", "并列时间戳 `[ts1]、[ts2]` 只核第一个，引语落在第二个时误判 fail",
     "并列定位未分组；且分组正则漏了前一个时间戳的闭合方括号（gap 形如 `]、`）",
     "同一条引语的多个并列定位必须合并为同一个 body（#39）",
     "major", "eval_gap", "Dark Playground 引语在 00:06:43.90，卡片两个都写了但只核第一个",
     ["t_verify_quotes_accounting"]),
    ("能力卡撰写（我）", "`\"We can visualize the future… make long-term plans\"` 被核验判 fail",
     "用 `…` 把原文里由句号分隔的两个分句连成一段，当成连续引语",
     "引语里的 `…` 只能在原文该处确有省略时使用；跨句合并要引全",
     "major", "structure_gap", "语料原文是 `We can visualize the future. We can see the big picture. "
     "We can make long-term plans.`", []),
    ("能力卡撰写（我）", "`72 小时 90 页` 被当成英文引语去核，必然核不到",
     "**中文换算**被写成了引语形态",
     "凡本卡做过换算/概括的内容，必须显式标注「换算由本卡完成」，不得放进引号",
     "major", "structure_gap",
     "讲者原话是 `I wrote 90 pages over 72 hours`，中文表述是本卡的", []),
    ("能力卡撰写（我）", "引语挂在了 `[00:02:27.20]`，但该引语只存在于 `[00:02:00.10]`",
     "第二版遗留的时间戳错位；更正记录里写了但正文没改",
     "更正记录**不等于**修正——同一问题在正文里必须同步改掉，并重跑核验确认",
     "major", "structure_gap",
     "`I thought that was the end of everything` 段落归属 00:02:00.10", []),
    ("verify_quotes 工具", "引语覆盖率的分母里混进了表格里的纯定位锚点",
     "未区分「这条引用承不承载引语」",
     "表格 / 出处标注里的时间戳归入 `locator_only_refs`，不计入引语分母（#35）",
     "major", "eval_gap",
     "TED 卡 42 个引用里 25 个是表格锚点，混进分母会让引语覆盖率虚低",
     ["t_verify_quotes_accounting"]),
    ("度量环节（工具）", "默认阈值 0.60 报出『覆盖率 100%』——真实值在 0.70 档只有 76%",
     "audit-coverage 只输出单点覆盖率；最低段落 cov=0.61 距阈值仅 0.012，"
     "结论完全由阈值决定却被当成客观结论",
     "**谁报 100%，谁负责证明它站得住**：满覆盖时必须输出 threshold_fragile / "
     "threshold_margin / threshold_sensitivity / strict_reference，"
     "让单点数字无法被单独引用",
     "major", "eval_gap",
     "同一劣行第三次：0.30 给过虚假 100%，改成 0.60 后仍然虚假 100%——"
     "调默认值是治标，把自检放进工具才是根治",
     ["t_audit_coverage_runs"]),
    ("回归测试（我）", "把卡片某句的具体措辞硬编码进断言，改措辞后立刻假失败",
     "assert \"他没说被关住的是\" in text——卡片把该句改写为『代价没有被消除』后，"
     "申报其实更完整了，测试却报『自加论断未申报』",
     "断言要锁定**语义性质**（该处的自加概括是否登记、是否带性质标注），"
     "不得锁定字面。否则测试会阻止人改进表述",
     "major", "tool_gap",
     "脆性与匮乏是同一件事：用字面当判据，等于把测试绑死在当前的表达方式上",
     ["t_disclosure_completeness"]),
    ("能力卡撰写（我）", "写『逐字稿中找不到支持该论断的文本』——被原文推翻",
     "讲者本人就说论文 very very bad（[00:02:27.20]）、也说无期限时 Panic Monster 不出现"
     "（[00:11:32.10]），两处都是该判断的文本支持",
     "『素材里没有 X』这种**全称判断**必须先限定到具体一处；"
     "要写就写『讲者给了事实，但没做这一步概括』，而不是『没有文本支持』",
     "major", "eval_gap",
     "**这是本卡早先已在更正记录里写过教训的同类复发**——写了教训不等于不再犯，"
     "必须靠工具或测试兜住，而不是靠记得",
     ["t_verify_quotes_attribution_block"]),
    ("度量环节（工具）", "卡片『归属声明块』里的引号被当成来源引语去核",
     "`> ⚠️ **归属拆分**：……他只诊断到「某某做法名」这层（[ts]）`——"
     "块里的「」引用的是**被描述的做法**，不是素材原话，按引语核必然核不到，"
     "卡片没错却报『来源不实』",
     "工具必须认得元描述框：块内出现 归属拆分 / 措辞修正 / 口径统一 / 更正记录 "
     "即视为作者行文，其内引号不作为引语；检测范围按**空行分块**",
     "major", "eval_gap",
     "**同类问题第四次**：前三次都靠改卡片措辞躲过去（治标）。"
     "另注：检测范围用固定字符窗口会吞掉相邻正文块导致真引语漏核，回归用例已抓到",
     ["t_verify_quotes_attribution_block"]),
    ("度量环节（工具）", "`_expand` 向上扩展时，若上一行是文本开头就直接 break",
     "`> 「…」\n> —— [ts]` 这种两行引用块，第一行之前没有换行 → 返回当前位置，"
     "于是**第一行（真正的引语行）永远进不了窗口** → 整条引语漏检且无任何提示",
     "`p_nl < 0` 表示上一行就是文本开头，不是『没有上一行』，仍需判断它是否属于同一块；"
     "且上一行范围严格取 `[prev_start, pos-1)`",
     "major", "eval_gap",
     "由新增回归用例 t_verify_quotes_attribution_block 的对照组抓出——"
     "**写测试反而发现了工具的既有边界缺陷**",
     ["t_verify_quotes_attribution_block"]),
    ("tdlib.fidelity", "nuwa 第三条铁律（交叉复核）只存在于文档，代码里没有任何强制",
     "`gate()` 只判总分与评测模式，多评分 Agent 的分差完全没人管——"
     "CAPABILITIES 曾写「继承女娲质检机制」，实际上只继承了前两条",
     "必须有 `cross_review()`：2 个独立评分 agent、分差 >10 判 needs_human_review，"
     "且 gate 见到 needs_human_review 必须拒绝放行；人数不足判 insufficient_scorers",
     "critical", "eval_gap",
     "对照上游 nuwa-skill 的 FIDELITY 三条铁律逐条清点时发现——"
     "前两条有代码，第三条只有散文",
     ["t_cross_review_gate"]),
    ("全局副本同步", "改完项目目录没同步 `~/.workbuddy/skills/rulai-skill`，"
     "技能实际加载的是旧版——cross-review 门禁、3 个 workflow、VENDOR.sha256 全都没生效",
     "回归测试跑的是项目目录，永远绿；**两处开发、无守卫**",
     "开发目录与已安装副本必须逐文件一致，由 `t_installed_copy_in_sync` 强制"
     "（缺失与内容不一致都判红）",
     "critical", "tool_gap",
     "补完 nuwa 第三铁律后核对全局副本时发现——"
     "**门禁写了等于没写，因为它不在被加载的那份里**",
     ["t_installed_copy_in_sync"]),
]


def build_cases() -> list[dict]:
    out = []
    for skill, prompt, actual, expected, sev, cat, evidence, planned in DEFECTS:
        out.append(failure_case(
            skill=skill, prompt=prompt, actual=actual, expected=expected, severity=sev,
            category=cat, evidence=evidence,
            planned=[f"回归测试：{t}" for t in planned] + ["登记进 CONSTRAINTS.md 缺陷台账"]))
    return out
