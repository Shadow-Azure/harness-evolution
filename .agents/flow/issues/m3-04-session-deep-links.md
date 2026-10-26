# m3-04 session deep links

[English](m3-04-session-deep-links.en.md) | 中文

```yaml flow
kind: issue
id: m3-04
milestone: m3
depends:
  - m3-03
priority: P0
status: in-progress
scope:
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 44
  url: https://github.com/Shadow-Azure/harness-evolution/issues/44
```

## 背景

Session 浏览器与 Agent 执行流已具备真实数据和交互，但选中 Agent 与证据位置仍只保存在内存；刷新、新窗口和浏览器历史无法恢复同一视图，也没有稳定的 URL 解析边界。

## 目标

- 以 URL 作为 `/sessions/:sid?agent=&evidence=` 的唯一状态源。
- 非法参数和过期 Agent 使用明确页面/内联错误，不串到其他 Session。
- 为后续 `/errors?case=&tab=` 提供纯解析与归属 resolver 接缝。

## 设计依据

- [05 §5 深链契约](../../../plans/fullstack-design/05-api-design.md)
- [08 §6.2 深链状态](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 R6 风险](../../../plans/fullstack-design/README.md)

## 实现内容

- `sessionId/agent/evidence/case/tab` 严格解析、规范化与范围校验。
- Agent 和 evidence 从 URL 恢复，节点点击写回 URL，刷新、新窗口、前进后退保持同一位置。
- 无效 Agent 清空深链状态并内联提示；越界 evidence 保留 Agent、清除证据。
- bad-case 归属只提供 resolver seam；真实跨会话 409 由 m4-02 查询结果驱动。

## 实施步骤

1. 先写 parser、页面恢复、历史和新窗口失败测试。
2. 实现 URL 派生状态、树加载后校验和节点写回。
3. 用真实四 Session/Agent 数据验证刷新、新窗口和 390px 原型壳。

## 依赖与交付边界

- 依赖：m3-03
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:web -- deepLink sessions
pnpm typecheck:web
pnpm test:e2e --pattern "deep links survive"
pnpm build
pnpm verify:bundle
```

- 非法 parser 输入不触发详情/树请求。
- 刷新、新窗口与前进后退恢复 Session、Agent 与 evidence。
- 当前 Session 树失败时不应用过期深链；重试成功后恢复。

## 验收标准

- 深链可分享，Agent/证据恢复稳定，且不会跨 Session 串用资源。

## 门禁与 CI

- parser 单测、真实 Chrome E2E 与既有 typecheck/build/bundle 门禁。

## 非目标

- 不做短链服务。
- 不在 m3-04 注册 `/sessions/:sid/errors` 页面，也不伪造 bad-case 归属响应。
