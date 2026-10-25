# Agent Note: M1 全局壳与演示状态

Status: implemented

[English](2026-10-25-app-shell-states.en.md) | 中文

## Problem

M1 尚无领域数据，但登录用户仍需要看见产品稳定入口、统一状态反馈和安全的全局异常出口。若页面各自实现 loading/empty/error，或在 CLI 中先造虚构会话，M2 接入真实数据时会产生重复状态组件和演示数据清理成本。

## Decision

- 已鉴权壳固定展示 Sessions、Errors、Evolution 三个顶层入口；Errors 在 M1 只说明问题归属将在后续 milestone 接入，不渲染假问题行。
- 页面共享 `LoadingSkeleton`、`EmptyState`、`ErrorState`；health 首载在 shell 内显示骨架，故障显示可重试错误态，404 使用“不存在或已删除”的终态文案。查询/变更的 409 `RUN_BUSY` 通过带样式的 `ElMessage` 提示并保留当前页面；Vue 未捕获错误统一写控制台并显示通用 `ElMessage`，保留已挂载 shell。
- health 的 `phase` 是唯一演示标志；只有 `demo` 显示“演示数据”，`scaffold` 与 `live` 不显示。
- `fixtures/m1-shell.json` 是 M1 seed 的严格封闭 manifest；`python -m app.cli seed` 只运行迁移并复用幂等管理员播种，拒绝 production/live，不创建会话、问题、探针、运行或其他领域数据。
- 真实 Chrome E2E 走 API/Vite 进程，覆盖登录后三入口、空态、Errors 占位、demo 角标、控制台清洁和窄视口布局。

## Alternatives considered

- 在 M1 造四条演示会话让空态“看起来丰富”：会混淆 M2-01 的 fixture 所有权并掩盖真实接入缺口；否决。
- 允许页面各自写状态样式：短期少建组件，长期会分裂错误文案、重试和无障碍语义；否决。
- 把 demo 数据作为运行时 stub provider：会形成真实表之外的第二条数据路径；否决。

## Consequences

- M1 的演示入口是真实可运行的壳和 CLI，但领域区域保持诚实的空态。
- M2-01 接管完整 fixture schema 与会话数据；它应扩展 seed manifest/action，而不是绕开 CLI。
- 会话级问题详情仍归后续 milestone；顶层 Errors 入口在 M1 只承担导航与边界说明。
