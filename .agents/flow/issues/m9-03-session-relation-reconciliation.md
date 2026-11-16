# Session 父子关系重建与未解析分支

[English](m9-03-session-relation-reconciliation.en.md) | 中文

```yaml flow
kind: issue
id: m9-03
milestone: m9
depends:
  - m9-01
  - m9-02
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/agent_tree.py
  - apps/api/app/service/acquisition/**
  - apps/api/app/api/sessions.py
  - apps/web/src/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 238
  url: https://github.com/Shadow-Azure/harness-evolution/issues/238
```

## 背景

父 Agent tool_use 与子 metadata 的 toolUseId 一致但缺少 tool result 时，真实导出会误判 unlinked，而当前内部解析器却能关联。2026-11-15 的 5 个子 Agent 导出已经能提供 relation_evidence+metadata 的 authoritative 关系；本 issue 仍要覆盖缺 tool result、synthetic 和 unresolved 的降级路径。

## 目标

- 按 authoritative、derived、synthetic、unresolved 输出关系。
- derived 子 Agent 仍挂入树并显示未返回报告。
- unresolved 节点保留在诊断视图。

## 设计依据

- [15 §9.1](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：父子关系证据。
- [06 §3.3–§3.4](../../../plans/fullstack-design/06-database-design.md)：agents 与 agent_events。

## 实现内容

- 统一父 Tool call + 子 metadata 的匹配算法。
- 缺少结果只降低 confidence，不切断节点。
- API 和前端展示关系证据与 completion warning。

## 实施步骤

1. 先写 derived、synthetic、unresolved 三组树测试。
2. 实现关系分级和 canonical ordering。
3. 补节点 UI 证据标签。

## 依赖与交付边界

- 依赖：m9-01、m9-02
- 交付边界：不实现潜在匹配。

## 独立验证

```sh
pnpm test:api -- tests/acquisition tests/sessions; pnpm test:web
```

- ccbdb2f0 四子 Agent 全部挂入。
- 2026-11-15 五子 Agent 导出保持 authoritative 关系，并保留 derived/unresolved 降级样本。
- 最后复审为 derived 且标记缺最终报告。
- 无父工具身份节点为 unresolved。

## 验收标准

- 导出与内部树对同一 Session 给出一致关系。
- 未解析节点不会静默消失。

## 门禁与 CI

- API、Web、fixture 与 flow 门禁。

## 非目标

- 不按开始时间猜测父 Agent。
- 不隐藏未解析节点。
