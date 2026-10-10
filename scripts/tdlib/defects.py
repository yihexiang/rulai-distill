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
    ("全局副本同步", "改完项目目录没同步 `~/.workbuddy/skills/rulai-distill`，"
     "技能实际加载的是旧版——cross-review 门禁、3 个 workflow、VENDOR.sha256 全都没生效",
     "回归测试跑的是项目目录，永远绿；**两处开发、无守卫**",
     "开发目录与已安装副本必须逐文件一致，由 `t_installed_copy_in_sync` 强制"
     "（缺失与内容不一致都判红）",
     "critical", "tool_gap",
     "补完 nuwa 第三铁律后核对全局副本时发现——"
     "**门禁写了等于没写，因为它不在被加载的那份里**",
     ["t_installed_copy_in_sync"]),
    ("tests/e2e.py", "回归测试**定义了却没登记进运行清单**，因此从来没跑过",
     "`t_overlap_detector`（素材零重叠检测）写好了却漏登记——"
     "「换素材必须证明与旧素材零重叠」这条要求**从未被机器验证过**，"
     "而 README/CAPABILITIES 里的项数是按「定义数」算的，看着一直是绿的",
     "任何 `def t_*` 都必须出现在 main() 的运行清单里，由 `t_no_unregistered_tests` 强制"
     "（定义集合与清单集合必须相等，双向报差）",
     "critical", "tool_gap",
     "2026-10-07 补 README 安装章节时，`t_docs_no_drift` 报「声明 64 项、实际 65 项」"
     "顺藤摸瓜查出来的——**写了不跑比不写更坏，它给人虚假的安全感**",
     ["t_no_unregistered_tests", "t_overlap_detector"]),
    ("tdlib.anchor", "「引语真实存在、但挂在错误的段号上」这类错误**没有任何工具能发现**",
     "`verify-quotes` 只做全文搜索——只要引语逐字存在于语料里就判 PASS，"
     "它挂在§233 还是 §232 完全不管。2026-10-05 我据此写下「§232 提到 except with Uber」，"
     "而§233 原话是 `except with Uber Lilith`（《暗黑破坏神》boss，接上一段游戏话题的玩笑）——"
     "**伪造的引用就这么通过了全部机械核验**",
     "必须有段号锚定核验：引语不仅要存在于语料，还必须出现在它**声明的那一段**里；"
     "由 `anchor.verify_file` 强制，`td.py anchor <卡片> --corpus <逐字稿…>`",
     "critical", "tool_gap",
     "独立评分 Agent 抓出这条伪造引用后做的复盘——"
     "**机械核验只能验「存在」，验不了「归属」**",
     ["t_anchor_verifier"]),
    ("tests/e2e.py", "零重叠测试的**夹具不真实**，导致它一登记就假失败",
     "`sentences()` 按 `[.!?]` 或空行切句，而夹具是无标点的单段文本，"
     "整篇被当成一整句 →「整句复制」根本没形成两句 → `exact_duplicate_sentences` 恒为 0。"
     "**注意检测器是对的**：`verdict` 仍然判FAIL（包含率 0.2 > 0.005）",
     "夹具必须用真实语料形态（有标点、能切成句子）；"
     "并且**两层防护要分别断言**：有标点时靠逐句检查，无标点时靠 8-gram 包含率",
     "major", "tool_gap",
     "把 #45 那条漏注册的测试登记进清单后第一次运行就红——"
     "**假失败比不跑更费时间**：会让人怀疑检测器而不敢用",
     ["t_overlap_detector"]),
    ("tdlib.util", "**代码里的版本号**与文档脱节，`doctor` 打印的是过期版本",
     "`VERSION = \"1.1.0\"` 硬编码在 util.py，而包已是1.6.0——"
     "于是 `td.py doctor` 在 1.6.0 的包上打印「td.py v1.1.0」。"
     "**用户看到的就是错的那个**，而文档守卫只查文档、查不到代码",
     "版本号只能有一个真源：从 `SKILL.md` 的 `metadata.version` 读取；"
     "并由 `t_docs_no_drift` 断言 `tdlib.util.VERSION == SKILL.md 的版本`",
     "major", "tool_gap",
     "2026-10-07 写安装说明时实跑 `td.py doctor` 看见的——"
     "**不实跑就发现不了**，文档类测试永远抓不到代码里的常量",
     ["t_docs_no_drift"]),
    ("td.py index", "`index --grep` **只检索标题树，不检索正文**",
     "正文里的词一个都搜不到（实测「分块」「正文」「演示」全部命中 0 块），"
     "只有标题里出现的词才命中。而 `chunk` 的输出恰恰提示"
     "「下一步：td.py index <sidecar> --grep <关键词>」——**承诺了做不到**",
     "标题匹配 OR 正文子串匹配（大小写不敏感）并集；"
     "由 `t_chunk` 用只出现在正文里的词（「前提」）守住",
     "critical", "tool_gap",
     "2026-10-07 写安装说明时照着 `chunk` 的提示去检索正文词，命中 0 块——"
     "**这类缺陷只有在真的按文档走一遍时才会暴露**",
     ["t_chunk"]),
    ("tdlib.evals", "`count` 传**单个文件**时静默报 0/0",
     "`token_metrics` 对 root 做 `rglob(\"*\")`，而单个文件 rglob 返回空——"
     "于是 `td.py count 某.md` 显示「语料总量 0」，看起来像\"这文件不耗 token\"。"
     "**假绿比报错危险**：它不报错，只是安静地给一个错误的数",
     "root 是文件时直接计量该文件；由 `t_count` 断言 `file_count == 1 且 corpus_total > 0`",
     "major", "tool_gap",
     "同一次实跑发现——写说明时顺手测了 `count 一个 md`，输出 0 让我停下来查",
     ["t_count"]),
    ("tests/e2e.py", "**没有一条测试走用户的实际路径**：实现写了、测试写了、文档写了，"
     "但「init → chunk → index → count → validate → strategy → output-eval」"
     "这串用户真正会走的路从未被端到端跑过",
     "#48/#49/#50 三条是同一个病的三个实例——**只在读代码/写文档时顺手碰到才暴露**。"
     "这不是随机失误，是验收顺序错了：先写实现、再写测试、最后才「用」",
     "必须有 `t_guide_walkthrough`：按 GUIDE 的黄金路径端到端执行，"
     "断言每步都有**实质产出**（数字不为 0、命中不为空、产物非空），而不只是「没崩」",
     "critical", "tool_gap",
     "用户追问「为什么每次会话都能发现新问题，是不是有根本性逻辑问题」——"
     "查台账 50 条后确认：**这不是随机，是缺少端到端验收这一环**。"
     "补上后该测试**第一次运行就抓出 #52**，证明它确实在补那个缺口",
     ["t_guide_walkthrough"]),
    ("tdlib.overlap", "`overlap` **对中文完全失明**：纯中文语料切出 0 个词 → 包含率恒为 0.0000% "
     "→ **永远判 PASS**",
     "`normalize()` 用 `WORD_RE = [a-z0-9']+` 切词，中文一个都不匹配。"
     "于是「两批素材零重叠」这个结论，对任何中文素材都是**空结论**——"
     "工具在跑、报告在打印、数字是 0，但那个 0 什么也没证明。"
     "**假绿比报错危险：它不报错，只给一个错的安心感**",
     "分词改为「中文按字符 bigram（沿用 chunking 口径）+ ASCII 整词」；"
     "断句正则补中文句末标点 `。！？；`（否则整篇中文被当成一句话）；"
     "由 `t_guide_walkthrough` 用中文语料自身对自身必须判 FAIL 守住",
     "critical", "tool_gap",
     "2026-10-07 新写的端到端测试**第一次运行就红**——"
     "用中文夹具跑 `overlap --new src.md --old src.md`，居然判定 PASS。"
     "**这正是「补上端到端验收」的价值：它抓到了我完全不知道存在的洞**",
     ["t_guide_walkthrough", "t_overlap_detector"]),
    ("td.py overlap", "`overlap` 的**退出码文档与实现不符**：文档写「2 = 检出重叠」，实际是 1",
     "`cmd_overlap` 检出重叠时走 `die()` → exit 1（与本包其它命令的拒绝语义一致）。"
     "文档里的 2 来自我当时**误传两个 `--new` 触发 argparse usage error**，"
     "把用法错误码当成了业务退出码——**我把一次自己的操作失误读成了工具的行为**",
     "统一为 1，并在 `overlap.py` docstring 与 `GUIDE.md` 两处改正；"
     "`t_guide_walkthrough` 断言 `expect=1`",
     "major", "tool_gap",
     "写端到端测试时按文档写了 `expect=2`，实测得到 1，才发现文档错了——"
     "**文档里的每个数字都该被测试钉住，否则它就是传闻**",
     ["t_guide_walkthrough"]),
    ("docs", "批量替换时 `'66\\2'` 里的 `\\2` 被 Python 当作**八进制转义 chr(2)** 而非组引用，"
     "把 `SKILL.md` 里「 项，零依赖」整段吃掉",
     "文档守卫**只校验数字**，67 项全绿、谁也发现不了——"
     "**守卫只钉住它关心的数字，周边文字可以被悄悄毁掉**。"
     "而这种损坏肉眼几乎不可见（终端里就是一段空白）",
     "`t_no_control_chars`：git 跟踪的每个文本文件做字节级扫描，"
     "只放行 \\n \\t \\r；非 git 环境明确跳过不误判",
     "major", "tool_gap",
     "改回归项数时自己引入的——**修复动作本身也会写坏文件，"
     "所以「改完必须能被机器验一遍」不能只针对被改的那个字段**",
     ["t_no_control_chars"]),
    ("tdlib.transcript", "把中文从句的冒号误判成说话人，**改写了逐字稿正文**",
     "`SPEAKER_RE` 对「X：」一律认定说话人，而中文「我想通一件事：听众其实…」极常见。"
     "于是逐字稿被写成 `**那半分钟里我想通一件事**： 听众其实…`——插入了原文没有的 `**` 与空格。"
     "后果链最恶劣的一环：卡片**逐字引用原话** → `verify-quotes` 判"
     "「❌ 未在语料中找到，这类来源不实必须修掉」→ 用户为\"修好\"只能把 `**` 抄进卡片，"
     "**等于教用户伪造引语**。实测真实英文 TED 字幕 315 条 cue 零误判、纯中文必中",
     "逐字稿正文**原样输出**（从构造上不可能被改写）；说话人只认**重复出现**的标签，"
     "且只写进 JSON 元数据；由 `t_transcript_lossless` 断言正文与字幕原文逐字一致",
     "critical", "tool_gap",
     "用自造的中文 SRT 做端到端探针时，发现输出里多了一对不是我写的 `**`——"
     "**只要换成中文素材就会撞上**，而这是本项目的主要目标素材",
     ["t_transcript_lossless"]),
    ("tdlib.anchor", "`anchor` **对中文完全失明**，而且**空集还打印 PASS**",
     "三处英文假设：`norm_words` 只认 `[a-z0-9']+`、引语抽取要求 `[A-Za-z]{2}`、"
     "只认 `\"…\"` 不认 `「…」`。结果：**专门为防「伪造引语」而建的命令**"
     "对中文卡片一条引语都抽不出来，打印「引语 0 条」+「✅ 判定 PASS」。"
     "而本项目的主力素材就是中文——等于头号安全特性在最常见的场景里是空的",
     "分词与引语抽取改为语言无关（中文 bigram、「」与“”一并识别）；"
     "新增 `vacuous` 字段：有 §N 标注却 0 条引语时 CLI 必须报错退出，**空集不得判 PASS**；"
     "由 `t_anchor_chinese_not_vacuous` 四段断言守住",
     "critical", "tool_gap",
     "接着 #52/#55 的同一类假设继续静态扫，发现 `anchor.py` 里写着与 overlap 一模一样的 "
     "`WORD_RE = [a-z0-9']+`——**同一类假设的第三例**",
     ["t_anchor_chinese_not_vacuous"]),
    ("tdlib.evals", "`verify-quotes` 把「引语挂错位置」报成「未在语料中找到」",
     "引语明明在语料里、只是位置标错时，用户看到那句话会去**删掉一条真引语**——"
     "核验器反而在破坏卡片。二者对用户的意义完全相反：一个改位置，一个删掉并追查来源。\n"
     "拆分时引入并当场堵上的假绿：misplaced 排除出 unverified 后 verdict 差点整批变 PASS",
     "核验不到时先在**全文**再搜一遍：命中即归 misplaced 并报出真实位置；"
     "全文都没有才归 unverified（疑似编造）。verdict 必须三者都空才 pass",
     "major", "tool_gap",
     "用三条引语（对/错位/编造）做反向探针时发现，两条失败的性质完全不同却被报成同一句话",
     ["t_verify_quotes_misplaced_vs_fabricated"]),
    ("tdlib.evals", "`audit-coverage` 用 `split()` 判实质段落 → **中文段落全被跳过**",
     "中文没空格，整段只算 1 个词 < min_words → 每个中文段落都被当成衔接语跳过。\n"
     "实测报告「语料段落 3（实质 0）」：老实读的人以为卡片很差；"
     "**扫一眼的人把「未覆盖 0」读成「全都覆盖了」**——与虚假满覆盖同形",
     "`_unit_count()` 中文按字计数；并加 `vacuous` 守卫：实质 0 段时不给任何覆盖结论",
     "critical", "tool_gap",
     "接着中文专项审查做覆盖率探针——卡片明明覆盖了 2/3 段，工具却说实质 0 段",
     ["t_chinese_unit_count_and_honest_capability"]),
    ("tdlib.research", "`research merge` 的冲突检测只看得见措辞重叠的条目，" 
     "真正的对立主张永远检测不到，摘要却打印「冲突 0 处」",
     "实测真矛盾句对 3-gram 相似度 0.000~0.077，而非矛盾只换宾语的一对反而 0.400——\n"
     "**矛盾天然不相似**，相似度阈值在原理上分不开。「冲突 0 处」读起来像「没矛盾」。\n"
     "中途加过「话题相关+否定极性相反」的启发式，在该抓住的用例上返回 0 处，已撤——"
     "**失效的启发式比没有更坏**",
     "不假装能做：显式声明「本工具查不到对立主张」+ 附实测相似度证据 + "
     "给出必须人工做的下一步；contradiction_detection=unsupported；"
     "**不给计数字段**（会被读成「0 处=没问题」）",
     "critical", "tool_gap",
     "两条一手来源给出明确相反的说法（前提必须固定 / 不需要固定），工具报「冲突 0 处」",
     ["t_chinese_unit_count_and_honest_capability"]),
    ("tdlib.evals", "语言过滤**静默丢弃**中文候选：表格行里的编造中文引语被放过",
     "`_keep()` 对「语料判为英文 + 作者行文行」的中文候选直接 continue，"
     "候选变空后又被误归类成「表格行=纯定位锚点」，于是完全不计数。\n"
     "实测同一位置放编造的英文引语判 FAIL、放中文打印「✅ 全部引语在语料中核到」——"
     "**在「防伪造引语」这件事上假绿**",
     "新增 lang_skipped 记账：单独归类（不再混进 locator_only）、计入对账表、"
     "CLI 显式打印「未核验」且不再给干净的 ✅；不硬判失败（中文作者行文在英文语料里是常态）",
     "critical", "tool_gap",
     "接着 #52~#59 的同类假设审「按语言做判断」那一处——用英文为主语料 + 中文表格行做探针",
     ["t_verify_quotes_lang_filter_not_silent"]),
    ("tdlib.anchor", "引语长度门槛按**英文尺度**设计，8~11 字的中文引语整类被丢且计入 noise 静默消失",
     "两道闸门都卡在同一个英文尺度：抽取正则 `[「“]([^」”\\n]{12,600})[」”]` 的下限、"
     "`_is_quote()` 的 `len(q) < 12`。中文 7 个字已是完整命题——"
     "「天行健，君子以自強不息」(11 字)、「不可為典要，唯變所適」(10 字) 从未进入核验。\n"
     "实测 zhouyi-yili 卡 25 条候选只认出 9 条（16 条被丢，其中 8 条为 8~11 字）",
     "长度门槛语言自适应：中文按汉字数判（≥8 且密度 ≥0.4），ASCII 才用 12 字符下限；"
     "抽取正则下限放宽到 4 字符；新增 quote_candidates / skipped_cjk_short / "
     "short_but_in_corpus 与 extraction_reconciliation.balanced，"
     "候选 = 认出 + 噪声 + 中文太短跳过**必须对账平**",
     "critical", "tool_gap",
     "用最终版工具体检 guoxue 四技能时，zhouyi-yili 的 quotes_seen=9 与卡片 25 条候选对不上——"
     "**C10 纪律（引用数≠核验数必须逐条对账）第 2 次抓到同类「中文失明」**",
     ["t_anchor_cjk_short_quotes"]),
    ("tdlib.lintquotes", "把引号里的文件名/通配当成引语；且卡片按建议标注「节引」后省略号提示照旧反复报",
     "①卡片写 `任一返回\"未找到 references/…md\"时…`，被判成「含省略号的引语」——"
     "**工具自己的假阳性**（假阳性比漏报更坏：逼人去改一句本来正确的正文）。\n"
     "②省略号给用户的处置是「补全为原文，**或明确标注为节引**」，但标注后提示不停——"
     "**工具不认自己给的建议**",
     "_looks_like_path()：`://`/`*`/`?` 或**斜杠后为非中文内容**即判技术 token，"
     "technical_tokens_skipped 单独计数（中文夹斜杠的正文不误杀），vacuous 判定扣掉技术 token；"
     "上下文出现「节引/節引」时省略号提示即停",
     "major", "tool_gap",
     "用最终版工具体检 guoxue 四技能时，zhouyi-yili 报「未找到 references/…md 含省略号」——"
     "一看就不是引语；同轮 geju-yunshi 的合法节引在标注后仍被反复提示",
     ["t_lint_quotes_technical_and_sectional"]),
    ("tdlib.validate", "死链检查把「该 md 所在的目录」当成\"根\"，正常的 `../` 相对链接一律被判「路径逃逸」",
     "`check_dead_links` 调的是 `safe_target(md.parent, tgt)`，而 `safe_target` 的语义是"
     "「解析基准与根是同一个」——那是给 bundle `src` 用的（必须待在自己目录里）。"
     "用在链接上就成了：`skills/a/README.md` 里写 `[配套](../b/)`（同级技能，仍在包内）被判逃逸。\n"
     "实测给 guoxue-skills 补四份技能介绍后**一次报出 27 条假阳性**，把正常文档判成「不允许发布」。\n"
     "**这类假阳性的代价不是多看一行警告，而是逼人删掉正确的链接。**",
     "新增 `util.safe_target_under(origin, rel, root)`：**解析基准**是链接所在目录、"
     "**边界**才是校验根；`check_dead_links` 改用它。反方向同时守住——"
     "真逃出校验根（`../../../etc/passwd`）与真死链仍照报",
     "critical", "tool_gap",
     "给 guoxue 四技能写介绍（用正常相对链接互相引用）后跑 validate 才发现——"
     "**新写的文档成了这个守卫的第一个真实用户，它的假阳性这才第一次暴露**",
     ["t_dead_link_relative_within_root"]),
    ("tests/ + docs-check", "文档结构检查把**代码段里的 markdown 链接语法**当真链接；"
     "且这两步检查**只存在于 CI**，本地回归跑不到",
     "我在 CONSTRAINTS.md 的 #63 条目里写 `[配套](../b/)` 举例说明"
     "「什么叫合法的相对链接」，反引号并没有让扫描器豁免它。"
     "本地 96 项全绿，推上去 **CI 两处红**（pipeline-check 的 `validate .` + docs-check 的结构自检）。\n"
     "**与 #51 同类：改了文件却没按用户的路径跑一遍**——那两步只写在 workflow 里，本地测试网没覆盖。",
     "①`util.strip_code()`：剥掉围栏代码块与行内代码段，`iter_links` 先过它——"
     "**代码段里的 markdown 语法不是 markdown**；"
     "②把内联在 `docs-check.yml` 里的结构检查搬进 `tests/doc_structure_check.py`，workflow 只调用；"
     "③新增 `t_self_validate_clean_and_doc_structure`：把 CI 的那两步钉进本地回归，"
     "并双向断言「代码段里的链接不算链接 / 正文里的死链仍要报」",
     "critical", "tool_gap",
     "又一次「新写的文档成了扫描器的第一个真实用户」——"
     "**同一个模式当天连犯两次（#63/#64），说明缺的不是细心而是本地可跑的检查**",
     ["t_self_validate_clean_and_doc_structure"]),
    ("tests/e2e.py", "回归测试**耦合作者工作区**：本机假红 / CI 静默跳过（**「空集假绿」在测试层的变体**）",
     "`t_anchor_cjk_short_quotes` 第⑤步只检查 `../guoxue-skills` 存在，没检查 `../yijing-run/corpus` "
     "是否存在：**本机（有 guoxue 克隆、无工作区语料）94/95 假红**；"
     "**CI（两个目录都没有）整体跳过——绿是\"跳过\"而非\"跑过\"**。"
     "断言外部卡片 `quotes_seen≥16` 还构成跨仓库耦合（那张卡一改测试就红）。",
     "改为 **fixture 驱动**：`tests/fixtures/cjk-short-quotes/{card,corpus}.md` 把 #61 的缺陷"
     "固化成自足样本；断言 quotes_seen=6 / 命中 4 / 短引语失配只报警 / 双向对账平衡 / 长引语挂错仍 FAIL。"
     "**与任何外部工作区无关，本机与 CI 跑的是同一条。**",
     "critical", "tool_gap",
     "复审 5 实测指出：\"本机 94/95 的差 1 项已定位为测试对作者工作区的耦合\"，"
     "而这恰恰是本项目最忌讳的模式——**跳过伪装成通过**",
     ["t_anchor_cjk_short_quotes"]),
    ("examples/sample-bundle", "样例历史报告的 frontmatter 与正文**自相矛盾**：同一字段两种说法",
     "`eval/fidelity-report.md` 的 `cross_grader_gap` 被回填成 `8`（那是**第二**轮交叉复核的结果），"
     "而正文写着「cross_grader_gap 为空」（**第一**轮确为单评分）。"
     "文件虽标了 superseded，读者看到的却是两个互相矛盾的数。",
     "历史文件写历史：字段恢复为 `未做第二评分者交叉校验`，指针（第二轮 8 分）只放正文标注；"
     "新增 `t_sample_report_consistent`：历史字段**不得以数字开头**、必须显式标注已被取代，"
     "数字唯一真源在权威 `FIDELITY.json`（gap=8、≥2 评分者）",
     "major", "structure_gap",
     "复审 5 检出——为了让新报告「可被发现」而回填历史字段，结果制造了新的自相矛盾",
     ["t_sample_report_consistent"]),
    ("tests/ci_local.sh",
     "bash 把紧跟变量名的多字节字符读进变量名，打印 `（��`",
     "脚本照常往下跑，最后打印「✅ 全部通过」",
     "bash 把「紧跟 `$var` 的多字节字符」读进变量名 → 变量内容**静默丢失**、"
     "打印乱码，**而退出码仍是 0**。`ci_local.sh` 写 `echo \"…（rc=$rc）\"`，"
     "全角括号紧跟 `$rc`。**报错会停下，乱码会继续**——所以它比报错更危险。\n"
     "同一文件同一写法栽了两次（第二次是 `$VENV）`），肉眼完全看不出问题",
     "critical", "tool_gap",
     "新增 `scripts/shell_safety.py`（判据全部跑过 bash 验证：紧跟非空白 = 真错，"
     "后面有空格 = 安全；首版把两者混为一谈报出 6 处假阳性，已收紧）；"
     "修 install.sh 两处真 bug（`dir=$1` 未加引号 → 带空格路径被拆成两段；"
     "`未知参数：$1（…` 截断）。P0 批次做本地 CI 预演脚本时踩到；"
     "同一坑在同一文件栽两次，说明缺的是能跑 bash 的守卫而不是细心",
     ["t_shell_scripts_safe"]),
    ("README.md / GUIDE.md",
     "README 写「12 张真实卡」，逐卡数只有 9 张；写「只对 2 张卡跑通交叉复核」，"
     "磁盘上已有 6 份 FIDELITY.json",
     "声称与实际不符时必须有东西变红",
     "对外声称（卡片数、交叉复核卡数、回归项数…）完全没有台账。"
     "两处都不是笔误，是做完事没回头改声称——而这正是本项目最高频的一类缺陷。"
     "本条是 P0-4 建台账时**逐条实测数出来的**，不是推测",
     "critical", "structure_gap",
     "新增 `docs/CLAIMS.md` + `docs/verify_claims.py`：每条声称给真实存在的"
     "测试名/命令 + 核验日期；事实数字集中在 facts 段，`--sync` 一条命令同步全部文档。"
     "**校验器自己也被校验**：首版「数字腐烂」检查写成找 `{tests} = N`（文档里没这种写法）"
     "→ 永远匹配不到，看着有、实际从不触发（#54 同一个病）",
     ["t_claims_have_evidence"]),
    ("benchmarks/token-savings/measure.py",
     "输出「窗口比整本还贵：0.56×」",
     "省 token 的数字必须 ≥1，且脚本在字段不存在时必须报错而不是静默算错",
     "量具本身是坏的却毫无报错：读 `document.json` 的 `elements`"
     "（而 `index --grep` 真正返回的是 `chunks.jsonl` 的 `ck-*` 块）、"
     "字段名写成根本不存在的 `id`/`title` → 命中块 id 全空、邻块去重失效。\n"
     "**一个看起来像数字的错结果比不测更坏**",
     "major", "tool_gap",
     "计量单元改回 chunks.jsonl；邻块去重；退化样本（只命中标题块→倍数四位数）"
     "标为「退化」不进区间；命中 0 块不给倍数；`--corpus` 用 `action='extend'`"
     "（argparse `nargs='+'` 重复传时后者覆盖前者，实测少一本书却零报错）；"
     "没装 tiktoken 时报「未运行」退出码 2。P0-3 第一版就错，"
     "靠实跑并逐条核对 schema 字段才抓到",
     ["t_token_savings_benchmark"]),
    ("td.py corpus-anchor",
     "628 行的公版典籍只规整出 6 段（每段近万字），并打印「✅ 规整完成」",
     "按 markdown 标题切段；段数过少时必须警告段号已失去定位意义",
     "只按**空行**切段。维基文库导出的典籍是「一行一段、无空行」格式，"
     "628 行只切出 6 段。段号是给引语定位用的，一段近万字时「第12 段」≈「整卷」，"
     "**定位等于没有**。\n"
     "比切错更隐蔽：它给出的是一个**看起来合法**的段号体系，没有任何异常信号",
     "critical", "tool_gap",
     "①normalize_book_corpus 改为先按 markdown 标题切（#～######），无标题才退回空行；"
     "②新增 --max-chars，超长段按句边界再切、不丢内容；"
     "③CLI 打印切段依据，段数 ≤3 且原文 >4000 字时警告。"
     "实测《資治通鑑》5 卷：6 段 → 147 段。"
     "P0-2 批次取到真实公版典籍后立刻暴露",
     ["t_corpus_anchor_splits_by_structure"]),
    ("tdlib.anchor.verify_file",
     "anchor 不认《論語》式「篇-章号」细粒度段号（一之三），且「有引语但零条可核验」的卡被默认判 PASS（软 PASS 假绿）",
     "只认 §N / 时间戳 / 【第N段】三类标记；《論語》等语录体经典用独占一行的「一之三」作段号，12 条真实引语全部无法锚定（UNANCHORED 或报错）；且 verify_file 在「有引语但 0 条可核验」时返回 PASS——「没核验出错误」就印 ✅",
     "新增篇-章号标记（VERSE_LABEL_LINE_RE 独占一行 + VLABEL_RE 卡片侧三种形状：行首标签 / 出处行 —— 标签 / 同行紧邻引号）；Corpus 子类挂 verses/labels 索引；index_corpus 在语料含篇-章号时丢弃粗粒度【第N段】wrapper 只留细粒度；三态收口 FAIL/PASS/UNVERIFIED（0 核查 ≠ 通过，CLI die）",
     "critical", "eval_gap",
     "开放素材臂蒸馏《論語》时暴露：卡片 12 条篇-章号引语整类不可核；软 PASS 收口是「声称≠实际」的典型",
     ["t_anchor_verse_locators", "t_anchor_zero_anchor_is_na"]),
    ("examples/open-bundle/skills/lunyu-conduct",
     "卡片与文档做出无法佐证的「已核验」声称（「评分 Agent 核查确认」是假的；「引语逐字锚定」暗示自动段级锚定）",
     "論語卡 A1 写「评分 Agent 核查确认：叙事出现次数为 0」，但实际没有评分 Agent 做过这件事（只是建卡时全库检索）；SOURCES/scale-evidence 写「引语逐字锚定」暗示自动段级锚定，而当时 anchor 根本不认篇-章号",
     "改为「建卡时对 anchored 语料全库检索确认」；段级锚定改由 `td.py anchor` 真实跑出（32 候选 / 12 命中 / 0 挂错）并写明命令可复跑",
     "major", "structure_gap",
     "进度研判（2026-10-10）点名：論語卡 A1 的「评分 Agent 核查确认」无法佐证；同模式还存在于 sample-bundle 的 five-affairs 卡（已由 #73 收尾修正）",
     ["t_lunyu_card_no_overclaim"]),
    ("examples/sample-bundle/skills/five-affairs-seven-questions",
     "#72 同款：卡片 A1 用「评分 Agent 核查确认」当背书，而评分 Agent 并未在建卡环节核查过任何东西",
     "措辞与論語卡（#72）同构。与論語卡的区别：这里的事实（第1段叙事关键词出现次数全为 0）"
     "在第一轮质检历史报告（eval/fidelity-report.md 108-109 行）确有记录——**声称有据，但出处是被"
     "标注 superseded 的历史文件**，读者按卡片措辞找不到可追溯的权威出处，且把建卡期事实核查"
     "错记成了质检者的功劳",
     "A1 改为「建卡时对 anchored 语料全库检索确认（可机械复算）」+ 显式引用历史报告并注明"
     "「已被结构化 FIDELITY.json 取代，字段以 JSON 为准」；机制化收尾：新增成品卡扫描守卫"
     "（评分者背书属质检环节，记录在 FIDELITY.json/报告，不进卡片正文），含负向探针",
     "major", "structure_gap",
     "真实水平评估（2026-10-10）杠杆 1：收尾 #72 同类。查证后确认与 #72 的差异——five-affairs "
     "有历史报告背书，病灶是「出处是被取代的文件+角色错记」，不是凭空捏造",
     ["t_cards_no_grader_backed_claims"]),
]


def build_cases() -> list[dict]:
    out = []
    for skill, prompt, actual, expected, sev, cat, evidence, planned in DEFECTS:
        out.append(failure_case(
            skill=skill, prompt=prompt, actual=actual, expected=expected, severity=sev,
            category=cat, evidence=evidence,
            planned=[f"回归测试：{t}" for t in planned] + ["登记进 CONSTRAINTS.md 缺陷台账"]))
    return out
