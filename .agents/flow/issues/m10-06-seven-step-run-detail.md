# 七步运行详情与执行事件

[English](m10-06-seven-step-run-detail.en.md) | 中文

```yaml flow
kind: issue
id: m10-06
milestone: m10
depends:
  - m10-04
  - m10-05
priority: P1
status: done
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/composables/**
  - apps/web/src/api/**
  - tests/e2e/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 215
  url: https://github.com/Shadow-Azure/harness-evolution/issues/215
```

## 背景

运行详情必须解释每个 Session、潜在 case、归因、簇和阻塞阶段，并支持历史运行。

## 目标

- 渲染服务端七步 DTO。
- 展示归因来源 fresh/cached 与 non_target。
- 执行日志支持 step、cluster 和 error 联动。

## 设计依据

- [08 §10](../../../plans/fullstack-design/08-frontend-implementation.md)：运行详情。
- [05 §3.6](../../../plans/fullstack-design/05-api-design.md)：七步响应外壳。

## 实现内容

- Step 2–4 使用分页表。
- 簇按 severity 降序并默认展开首簇。
- blocked attribution 显示自动与手动重试。

## 实施步骤

1. 先写七步 key 与 blocked 展示测试。
2. 实现动态 step 组件与分页。
3. 补事件日志和重试 E2E。

## 依赖与交付边界

- 依赖：m10-04、m10-05
- 交付边界：不改 event 存储。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern run-detail-v2
```

- 历史 run 与新 run 都显示七步。
- 未就绪步骤不请求。
- non_target 不出现在簇但可在 Step4 查看。

## 验收标准

- 页面只消费 run.steps。
- SSE 与 REST 刷新结果一致。

## 门禁与 CI

- Web、E2E、bundle 与 flow 门禁。

## 非目标

- 不新增第二套步骤 schema。
- 不展示自由文本错误。
