# Agent Note: Session 共享归因上下文与证据坐标

Status: implemented

[English](2026-11-17-session-attribution-context.en.md) | 中文

## Problem

逐 Badcase 重新读取和组装 Session 会产生 N+1、让同一 Session 的输入快照不一致，并诱使执行器从摘要中猜测对象 occurrence 或上报节点；长期保存原始消息又会扩大敏感数据边界。

## Decision

归因 Runner 在执行引擎前按 Session 批量读取归一化 Agent 节点和用户选定对象的全部匹配 occurrence，每个 Session 只构建一个 `attribution-context/v1` bundle，再为各 Badcase 派生只含 bundle 引用、上报坐标和对象到上报节点路径的 projection。Bundle 同时包含知识证据、历史 probe ID、来源版本、脱敏声明和降级 warning；所有 event reference 都在 bundle 的 evidence points 中可回查。清单使用 bundle 的规范 JSON SHA-256，不再使用逐 case 的临时坐标哈希。原始消息、凭据和完整 payload 默认不进入 bundle、报告或业务表。

## Alternatives considered

把完整 bundle 复制进每个 Probe Report 会放大存储并长期保留 Trace，因此否决。逐 case 调用上游接口会导致同 Session 快照漂移，因此批量归一化事实是默认来源；未来只有执行器明确需要且 m12-01 接缝可用时才短暂补取原始内容。让模型选择其他 `probe_object` 会绕过用户选定对象和 PotentialMatcher 的 revision 口径，因此上下文只描述选定 target。

## Consequences

同 Session 多 Badcase 共享同一 hash 和结构快照，但各自保留独立上报坐标；缺节点、关系降级或截断会显式产生 warning，不伪造消息或版本。当前边界最多保留 512 个 Agent 节点和 256 个对象 occurrence，超限进入稳定截断并警告。Bundle 只存在于一次 Runner 调用内，后续 Agent 执行器可直接消费 projection；若需要跨重试审计完整 bundle，应新增短期执行工件而不是写入 Probe Report。
