# Session 归因上下文组装与证据坐标

[English](m12-session-attribution-context.en.md) | 中文

```yaml flow
kind: issue
id: m12-16
milestone: m12
depends:
  - m10-02
  - m12-01
  - m12-14
priority: P0
status: done
scope:
  - apps/api/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 321
  url: https://github.com/Shadow-Azure/harness-evolution/issues/321
```

## 背景

`PotentialMatcher` 已能按选定对象 revision 找到关联 Session 和潜在 Badcase，但当前归因输入只有 Badcase 摘要、触发坐标与少量 metadata。真实 Agent 需要完整 Trace 树、目标对象所有 occurrence、Badcase 上报节点和可验证证据；若逐 Badcase 重复拉取整棵树，会放大上游延迟并让同一 Session 的上下文快照不一致。

## 目标

- 复用 `PotentialMatcher` 的选定对象与 Session 关联结果，不新增真实对象路由。
- 每个 Session 只构建一次可 hash、可脱敏的 `AttributionContextBundle`。
- 为同 Session 的每个 Badcase 派生独立、证据坐标可验证的执行输入。

## 设计依据

- [07 §5.12](../../../plans/fullstack-design/07-backend-implementation.md)：PotentialMatcher 与对象 occurrence 口径。
- [06 §7.4–7.5](../../../plans/fullstack-design/06-database-design.md)：Badcase 锚点、对象进入点与 Session 投影。
- [04 §5.2](../../../plans/fullstack-design/04-backend-architecture.md)：原始 payload 与归一化接缝。

## 实现内容

- 组装 Session Trace 树、选定对象全部 occurrence、同 Session Badcases、上报节点、对象到上报点路径、对象定义、知识证据和历史报告。
- 输出稳定 context snapshot hash、数据来源版本、脱敏结果与缺失/关系降级 warning。
- 先批量读取归一化事实；需要原始内容时通过 m12-01 上游接缝按需获取并在执行结束后释放。
- 逐 Badcase 输入只引用共享 bundle 与自己的上报节点，不复制或长期保存完整 Trace。
- 对象只表示用户选定 target；模型不能在本阶段替换 `probe_object`。

## 实施步骤

1. 写多 occurrence、多 Badcase、缺 Trace、版本未知和关系降级 fixture。
2. 实现 context provider、Session bundle 和 per-case projection。
3. 加入脱敏、大小限制、稳定 hash 与证据坐标验证。
4. 接归因 Runner 的批量准备阶段并验证无 N+1 拉取。

## 依赖与交付边界

- 依赖：m10-02、m12-01、m12-14。
- 交付边界：形成 Agent 可消费的上下文输入；不执行模型、不修改潜在策略、不自动选择其他归因对象。

## 独立验证

```sh
pnpm test:api -- tests/session_attribution_context
pnpm performance:report -- --local
pnpm contract:check
```

- 同一 Session 的多个 Badcase 只组装一次 bundle，各自得到独立上报节点和证据路径。
- 缺失原始 Trace 时显式 warning 或阻塞，不伪造消息、Tool 或对象版本。

## 验收标准

- 输入明确区分选定对象、对象 occurrences 与 Badcase 上报来源。
- 所有 evidence reference 可回查到同一 context snapshot 中的真实节点。
- 原始 Trace 默认不写入 Probe Report 或长期业务表。

## 门禁与 CI

- API、性能、契约、脱敏、文档与 Flow 门禁。

## 非目标

- 不实现真实对象发现、模型调用、Skill 注册或归因结论。
- 不复制一套 PotentialMatcher 或改变对象 revision 精确匹配口径。
