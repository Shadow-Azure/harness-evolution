# m4-02 problem api

[English](m4-02-problem-api.en.md) | 中文

```yaml flow
kind: issue
id: m4-02
milestone: m4
depends:
  - m4-01
priority: P0
status: in-progress
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 47
  url: https://github.com/Shadow-Azure/harness-evolution/issues/47
```

## 背景

m4-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m4-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §4.6–4.7 API](../../../plans/fullstack-design/05-api-design.md)
- [05 §5 深链](../../../plans/fullstack-design/05-api-design.md)
- [06 §7.4 口径](../../../plans/fullstack-design/06-database-design.md)

## 实现内容

- 提供 Session 问题/Probe 列表、问题详情、归因和 Probe 详情五个只读端点。
- 以单数据库快照组合 Session 标题、Agent/事件、外部问题、归因和 Probe，复用树的锚点语义。
- 可选 `sessionId` 校验深链归属；跨会话返回 `409 BAD_CASE_SESSION_MISMATCH`，不存在返回稳定 404。
- 未分析或缺少归因行返回 `unanalyzed` 占位；五态通过同一 `analysis` 对象供前端渲染。

## 实施步骤

1. 写列表、详情、跨会话 409、probe 反查失败测试
2. 实现 service/routes
3. 生成契约

## 依赖与交付边界

- 依赖：m4-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m4-02-problem-api
pnpm test:api
pnpm test:db
pnpm contract:check
pnpm test:web
pnpm test:e2e
```

- API 测试通过且 contract:check 无漂移
- 固定五态响应可精确断言

## 验收标准

- ID 深链安全且归因状态合并正确

## 门禁与 CI

- route gate、contract gate、双方言测试

## 非目标

- 不生成新归因
