# Agent Note: V2 跨栈验收的证据分层

Status: implemented

[English](2026-11-17-v2-cross-stack-acceptance.en.md) | 中文

## Problem

V2 的每个模块都有自己的绿测，但用户七点需求跨越身份、空间、上报、总览、归因和页面。逐模块绿不能证明「登录 → 空间切换 → 上报 → 总览 → 向导 → run → 错误详情 → lane DAG」这条真实链路成立：权限矩阵、跨空间不可见、额度与幂等、三处潜在数一致、缓存复用、迁移/重放/SSE 都可能在模块边界上失配。

## Decision

- 新增 API 验收套件 `apps/api/tests/m11-05-v2-cross-stack/`，用同一套多空间 fixture 分成三组：安全矩阵（不可见空间 404、只读/成员写 403、空间管理员不能授予空间管理员、跨空间凭据 403）、潜在数与缓存一致性（向导预览、run 候选、对象总览三处同数；第二次归因复用缓存；非该对象问题不进簇）、迁移/重放/SSE（SQLite 升到 head、Skill/Agent/knowledge 三类触发与派生父子关系、重复重放幂等、一次性 SSE 票据）。
- 新增一条真实浏览器 E2E `tests/e2e/m11-05-v2-cross-stack.test.mjs`：临时 SQLite + demo corpus，真实登录表单、空间切换、带凭据上报（含幂等与额度 409）、bad case 与对象总览、Session 最新十条与回车查询、多归因错误详情、四步向导、cluster-only run、七步 run 详情和 lane DAG/结构树切换；关键步骤同时断言 API 事实。
- 冒烟截图与 smoke report 作为 PR 的临时 release 资产保存，不进入代码仓；PR 描述只放脱敏后的场景结论与资产链接。
- 冒烟发现 `ClusterPreview` 复用 run 列表缓存且没有轮询，cluster-only run 完成后页面停在「准备中」。改为读取 `useEvolutionRunDetail` 并复用 `runDetailRefetchInterval`，活动 run 每 15 秒刷新，完成后自动显示终态。

## Alternatives considered

- 扩写各模块既有测试：覆盖面仍停在模块内，无法证明跨栈顺序与共享 fixture，且同一场景会散落在多个目录。
- 只做快照或 mock：无法验证真实 HTTP、真实 SQLite、真实浏览器和真实 run 推进，和「不以手工截图替代 API 断言」相冲突。
- 让 run 列表全局轮询来救 cluster 预览：会把所有历史 run 一起拉取，成本高于按 runId 读详情；详情端点已有稳定的轮询语义与单测。
- 只刷新页面绕过「准备中」：测试能绿，但用户仍会看到卡住的页面，等于把缺陷留在产品里。

## Consequences

- E2E 增加约 25 秒、API 套件增加约 100 个用例；MySQL 用例沿用现有 `mysql` marker，在无服务时跳过，CI 由 `test:db:mysql` 执行。
- cluster 预览在活动 run 期间每 15 秒读一次详情，终态后停止轮询；这是对页面缓存的补齐，不改变 run 状态机。
- 验收报告和截图不进仓库，长期证据依赖 PR 上的 release 资产；release 资产被清理时只能从 PR 描述与检视文档回溯结论。
- fixture 仍以合成内容为主，真实会话形状通过重放用例覆盖，不引入原始 prompt 或文档正文。
