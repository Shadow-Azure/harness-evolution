# Session 与 bad case 读路径空间化

[English](m7-06-session-bad-case-workspace-scope.en.md) | 中文

```yaml flow
kind: issue
id: m7-06
milestone: m7
depends:
  - m7-03
  - m7-05
priority: P0
status: done
scope:
  - apps/api/app/api/sessions.py
  - apps/api/app/api/problems.py
  - apps/api/app/service/sessions/**
  - apps/api/app/service/problems/**
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-session-bad-case-workspace-scope.md
github:
  number: 227
  url: https://github.com/Shadow-Azure/harness-evolution/issues/227
```

## 背景

空间隔离不能只靠前端路由；Session、问题卡和错误详情都必须按空间 bad case 投影过滤。

## 目标

- 所有 Session 与 bad case 读取增加 workspace 约束。
- 不可见 Session 与空间统一按 404 处理。
- 保留一个版本的旧端点兼容层。

## 设计依据

- [06 §7.5](../../../plans/fullstack-design/06-database-design.md)：空间 Session 投影。
- [07 §5.15](../../../plans/fullstack-design/07-backend-implementation.md)：服务端空间边界。

## 实现内容

- 新增 /workspaces/{wid}/sessions 与 bad-case 路由。
- Session 集合由空间 bad case 根会话投影得到。
- 旧端点按用户全部可见空间过滤。
- 注册空间路由需要 API 装配，跨空间测试与检视记录需要 API 测试与 plans，故 scope 覆盖这些文件。

## 实施步骤

1. 先写跨空间直连测试。
2. 迁移 service 查询并注册空间路由。
3. 更新快照与兼容说明。

## 依赖与交付边界

- 依赖：m7-03、m7-05
- 交付边界：不改 Agent 树布局。

## 独立验证

```sh
pnpm test:api -- tests/sessions tests/problems; pnpm contract:check
```

- 跨空间 Session 返回 404。
- 同 Session 被多空间上报时各空间只看到自己的 bad case。
- V1 端点仍可用。

## 验收标准

- 所有读写都经过 workspace 限制。
- 空间投影口径与设计一致。

## 门禁与 CI

- API、数据库、契约与 flow 门禁。

## 非目标

- 不在本 issue 实现最新 10 条交互。
- 不再给轨迹表增加 workspace_id。
