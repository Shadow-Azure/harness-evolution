# M29 轨迹原始负载分层存储

[English](m29-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m29
title: M29 轨迹原始负载分层存储
status: planned
github:
  number: 39
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/39
```

## 目标

- 在不丢失原始证据与重放能力的前提下，降低 `trajectory_payloads` 对主库空间的占用：先做 payload 压缩，再把低频 payload 分层到对象存储。
- `trajectory_payloads` 仍是原始轨迹的唯一事实源；归一化、幂等重放、按 `(runtime_key, root_session_id, agent_id)` 回读的语义不变。
- 上游回源只作为对象存储缺失时的可选恢复路径，不作为唯一副本；`script` 来源不得依赖回源。
- 给出可度量的容量、读路径与失败处理验收口径，先讨论选型再进入实现。

## 范围

`apps/api` 的 `trajectory_payloads` 模型、迁移、读取与写入仓储、acquisition 回放与本地归因读取路径、配置；`deploy`、`.env.example`、`docs`；对象存储适配层与测试；本 milestone 下的流程与设计文档。具体每个 issue 的允许修改面由该 issue 的 `scope` 收口。

## 验收

- 主库中 `trajectory_payloads` 的 payload 字节数显著下降，且容量不再随低频历史 payload 线性增长。
- 压缩、对象存储读取、缺失对象、哈希不一致四类路径都有可重复的验证；归一化结果与改动前一致。
- 迁移与回滚可执行；生产容量、读延迟、失败率有可观测指标。
- 选型结论落在 issue 中，实现 PR 按结论交付。

## 非目标

不改变归一化与业务表语义，不改变现有 API；不把上游回源作为唯一存储方式；不删除没有持久副本的历史 payload；不改变上游轨迹契约；不做与存储无关的 UI 或产品改版。
