# 修复归因 Skill 将外部根因标记为当前对象缺陷

[English](bugfix-explicit-skill-conclusion.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-58
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - attribute-badcases/**
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/tests/attribution/**
  - plans/evidence/attribution-verdict-588/*.png
  - .agents/flow/issues/bugfix-explicit-skill-conclusion*
  - .agents/notes/implemented/architecture/2026-11-17-attribution-report-v2*
adr: []
github:
  number: 588
  url: https://github.com/Shadow-Azure/harness-evolution/issues/588
```

## 背景

生产发现正文将失败归于外部评分环境、当前 Skill 仅能改善验证汇报的报告，在详情页仍显示「可归因到本对象」。同一源报告的对象身份与分析对象相同，类别为 error，正文排除了 Skill 的直接责任，保存的正向结论已被复用三次。自动化回归使用合成数据，PR 另附同一生产样例在修改前后的详情页截图。

## 目标

每份新执行的 Skill 报告独立判定当前选定对象是否导致这个 bad case，保留外部根因、证据缺口和改进建议。

## 设计依据

[后端设计 §5.13 归因生成与缓存](../../../plans/fullstack-design/07-backend-implementation.md)。

## 实现内容

PR #421 引入的本地执行器按原始报告中的对象身份与类别推导结论。合成样本通过了 writer、规范化和入库，且能进入聚类候选。将结论改为 Skill 必填三态，writer 从输入固定被评估对象，并将根因与分析分别保存。

## 实施步骤

先走共享 Claude Provider 验证非交互执行，再同步平台执行指令、内置 Skill、writer 与入库路径，最后比较固定正反例及旧快照。

## 依赖与交付边界

当前绑定包和平台内置包共用平台 writer。历史报告与已完成批次保留原记录。

## 独立验证

`pnpm test:api -- tests/attribution/test_local_runtime.py` 在独立 SQLite 内验证四类样本。真实 CLI 分别验证合成输入和本地 SQLite 中的生产导出样例。

共享 Claude Provider 使用服务配置的 600 秒超时完成内置 Skill 的非交互执行，经校验写入 SQLite，第二次运行命中缓存。新版协议在脱敏评分证据上返回 inconclusive 并给出两处证据引用。用完整轨迹（8 个 Agent）对 swe-5a7e0d8d69419188a326 关闭缓存重新执行后，Skill 返回 non_target 和 8 处证据引用；该结论入库后详情页显示「非该对象问题」，聚类候选数为 0。评分容器的原始 traceback 未包含在导出中。

## 验收标准

同一选定对象可得到三种结论，外部根因兼有改进建议时为 non_target，证据不足时为 inconclusive，只有 attributed 可进入聚类；缺失或非法的新格式结论应在入库前暴露。

## 门禁与 CI

运行 API 归因测试、类型检查、文档与 flow 门禁。

## 非目标

历史生产报告重算、生产配置变更和通过正文关键词自动判断因果均在本次范围之外。
