# Agent Note: Agent 树组装边界

Status: implemented

[English](2026-10-25-agent-tree-assembly.en.md) | 中文

## Problem

逐 payload 归一化只得到独立节点；若持久化前不建立父调用关系，普通 Agent、Workflow、teammate 和 forked skill 会变成无法回溯的平铺记录。

## Decision

树组装是只消费规范化结果的纯函数。每个 root 必须恰有一个 main；普通 subagent 通过 `toolUseId` 关联父 Agent 调用，teammate 直接挂 main，forked skill 按 Skill trigger 关联，Workflow trigger 生成零统计合成节点。缺失或未知父调用保留节点并降级到 main，在 main 末尾补确定性合成 `agent` 事件锚点，child 与锚点共享新的合成 `toolUseId`，`messageOffset` 取锚点前 main 的 unique assistant 数；重复父调用 id 对依赖它的 child 使用 `AMBIGUOUS_PARENT_TOOL_USE_ID` 降级，避免共享歧义边。所有结构降级都产生只含身份、行号、稳定 code 和固定消息的告警。节点先完成父链校验与环检测，再按结构 depth、源位置和稳定 id 排序；公开 `spawnDepth` 始终保留 provider 值，结构 depth 不回写。

节点统计直接复制解析结果，会话统计对完整树求和；`agents_count` 只计非 forked 的 subagent。用户轮次只取 main，模型与 Skill 名称去重，任意错误块令会话为 `partial`；最后会话记录不是 assistant，或任一 transcript 的 provider API 错误未被后续成功 assistant 恢复时，会话为 `fail`。会话首末时间取全部 transcript 记录边界且必须非空；完整 title 保留首个用户提问，`shortTitle` 才做展示截断；`searchText` 仅为小写 title 与 repo 拼接；匹配到的父 trigger 决定 subagent/fork 描述，forked skill 不保留 meta name。本切片只提供纯树和本地聚合，不写业务表、不更新 `source_records.processed_*`，也不实现完整重放。

## Alternatives considered

- 在归一化阶段直接写树：单 payload 失败会跨越事务边界，且无法统一检测缺父与环。
- 丢弃缺父 subagent：会让真实本地 62 个 subagent 中可回放节点数下降，并掩盖 provider 异常。
- 让普通 Skill 建节点：它与 forked skill 的独立 transcript 语义冲突，会制造虚假 Agent。

## Consequences

本地树对账必须保持 4 个 root、66 个节点、62 个可回溯 subagent，并显式报告缺父告警。m2-05 可复用当前不可变节点结果执行事务删除重写；改变关联或统计口径时，必须同时升级 parser/assembler 契约与 golden fixtures。
