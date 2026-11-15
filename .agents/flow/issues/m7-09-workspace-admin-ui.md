# 空间管理、成员、上报与鉴权接入界面

[English](m7-09-workspace-admin-ui.en.md) | 中文

```yaml flow
kind: issue
id: m7-09
milestone: m7
depends:
  - m7-05
  - m7-08
priority: P1
status: in-progress
scope:
  - apps/web/src/pages/workspaces/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - apps/web/src/stores/**
  - apps/web/src/router/**
  - apps/web/src/components/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/feature/2026-11-15-workspace-admin-ui.md
github:
  number: 230
  url: https://github.com/Shadow-Azure/harness-evolution/issues/230
```

## 背景

管理员需要通过界面创建空间、调整额度、管理成员和轮换上报凭据。

## 目标

- 实现空间、成员、上报接入、鉴权接入四 Tab。
- 只在服务端权限允许时显示写入口。
- 凭据明文仅展示一次并支持轮换。

## 设计依据

- [08 §4.2](../../../plans/fullstack-design/08-frontend-implementation.md)：空间管理页。
- [design-v2.md §3–§4](../../../plans/ui-prototype-v2/design-v2.md)：原型验收。

## 实现内容

- SpacesTab 支持创建、额度与管理员多选。
- MembersTab 使用候选搜索和角色限制。
- IngestTab 提供地址、curl 示例、额度和凭据轮换。

## 实施步骤

1. 先写角色可见性和凭据一次性测试。
2. 实现四个 Tab 与表单校验。
3. 补空间管理与错误态 E2E。

## 依赖与交付边界

- 依赖：m7-05、m7-08
- 交付边界：不实现总览页。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern workspace-admin
```

- 成员和 viewer 不出现写按钮。
- 空间管理员不能编辑 space_admin 行。
- 凭据关闭后不可再次读取。

## 验收标准

- 四 Tab 与原型信息架构一致。
- 直接调用 API 仍受服务端权限约束。

## 门禁与 CI

- Web、E2E、契约与 flow 门禁。

## 非目标

- 不做全局用户目录。
- 不允许注册或第二个全局管理员。
