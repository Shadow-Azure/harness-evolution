# M2 真实轨迹服务：Session Family 导入与存储

[English](m2-trace-service.en.md) | 中文

```yaml flow
kind: milestone
id: m2
title: M2 真实轨迹服务：Session Family 导入与存储
status: planned
github:
  number: 6
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/6
```

## 目标

把原型的数据来源替换为本机 rollout 的确定性导入与查询服务。

## 范围

- 流式解析 JSONL，保留 raw record 与归一化视图
- 按 parent_thread_id 组装 session family，记录深度与 agent 路径
- SQLite migration、repository 与 session/family/ingest/timeline API
- 重复扫描幂等，解析失败可重放

## 验收

- 4 个主会话家族共 64 个 rollout 可完整导入
- 重复导入不新增 session、turn 或 item
- API 返回的家族、agent 树和时间线与原型 fixture 对齐
- 单文件超过 20MB、单会话超过 3,000 条记录时可流式处理

## 非目标

- 多用户、权限与生产数据库
- AI 诊断与自动改进
