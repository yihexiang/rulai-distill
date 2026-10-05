# -*- coding: utf-8 -*-
"""tdlib — rulai-distill 确定性工具库。

模块划分（每个模块对应来源技能的一组能力）：
  util        基础设施：异常/输出/frontmatter/路径安全/token 计量
  chunking    结构感知分块 + 索引 + 确定性缓存      ← cangjie build_chunks + build_index
  transcript  SRT/VTT → 带时间戳逐字稿（离线）        ← nuwa srt_to_transcript
  research    人物六路调研骨架 + 合并去重 + 冲突标记  ← nuwa 六路 research + merge_research
  validate    技能卡静态校验（结构/死链/步骤禁令/来源占比）← cangjie validate + yeadon quality_check + nuwa quality_check
  fidelity    FIDELITY 报告解析 / 门槛 / 自测降级      ← nuwa fidelity-scorecard
  strategy    single vs pack 输出决策                 ← cangjie select_output_strategy
  publish     原子发布 / 快照 / 回滚 / 手改检测        ← cangjie compile_pack + compile_single
  evals       触发评测判分 / 输出体检 / token 计量 / 基准 ← cangjie run_trigger_evals + run_output_evals + count_tokens + benchmark
  evolve      diff / impact / repair / update / patch ← cangjie 五个演进脚本
  promptc     单文件 prompt 编译                      ← yeadon compile-prompt

全包约束：零网络、零动态执行、零第三方依赖可跑。
"""
__all__ = ["util", "chunking", "transcript", "research", "validate", "fidelity",
           "strategy", "publish", "evals", "evolve", "promptc"]
__version__ = "1.1.0"
