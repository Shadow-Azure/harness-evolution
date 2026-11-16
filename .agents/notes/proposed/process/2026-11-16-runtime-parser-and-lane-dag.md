# Agent Note: 多 runtime 轨迹 parser 与 lane DAG 执行流

Status: proposed

[English](2026-11-16-runtime-parser-and-lane-dag.en.md) | 中文

## Problem

当前归一化器写死 Claude Code 的 record、meta 和事件语义；`source_type` 又被误当成 runtime，`parser_version` 是全局整数。接入第二个 AI agent 时，只能继续在 `normalize.py` 加条件分支，并同时改 replay、唯一键和版本判断。另一个偏差是 V2 原型已把执行流改成小窗口 lane DAG，但设计文档和 M11 仍按 Vue Flow 节点树、`>8` 折叠、按问题过滤来写，且没有 issue 承接布局迁移。

## Decision

轨迹侧以 `runtime_key` 区分 AI agent，接入通道继续用 `source_type`。`TraceParserFactory` 按 `runtime_key` 选择 `BaseTraceParser` 子类；基类固定 JSONL 帧、坏行、隐私边界、计数与 finalize，子类只解释 record/meta/event/evidence。`parser_version` 按 runtime 解释，新增 runtime 只新增子类并注册。执行流侧默认 lane DAG：日志行区间、`A1/A1.1` 深度、跨 lane 并发、全部 lane 展开、小窗口缩放/平移；结构树保留为切换视图，选中 case 保留全部分支并高亮。

## Alternatives considered

在单一 `normalize_transcript` 里加 `runtime == ...` 分支，会把 provider 差异扩散到公共流程和测试。继续用 `source_type` 表示 runtime 会把接入方式和 agent 类型混在一起。继续用 Vue Flow 节点树承载 56 个 lane，会重新引入折叠、按问题过滤和布局裁切；用过滤表达选中 case 也会隐藏并发关系。

## Consequences

M9 增加 runtime parser factory 前置切片，M11 增加 lane DAG 切片；M9-01/02/04 与 M11-02/05 需要同步更新。新增 runtime 的改动面收敛到 parser 子类、fixture 与注册测试，不再修改 replay/agent_tree。未知 runtime fail fast，不静默回退 Claude。执行流的小窗口和全部 lane 展开会增加视口操作成本，但避免折叠掩盖并发。PR 只更新设计与 flow 草案，`flow:sync` 在 review 后执行；新 issue 的 GitHub 编号在同步时回填。
