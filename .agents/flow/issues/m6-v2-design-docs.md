# V2 设计文档：工作空间、总览与归因进自进化

[English](m6-v2-design-docs.en.md) | 中文

```yaml flow
kind: issue
id: m6-25
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/fullstack-design/**
  - .agents/notes/**
  - .agents/flow/**
adr: []
github:
  number: 206
  url: https://github.com/Shadow-Azure/harness-evolution/issues/206
```

## 背景

V2 原型（`plans/ui-prototype-v2/`）确立了四类新能力：多用户登录与鉴权接入预留、多工作空间与 bad case 上报额度、工作空间总览、归因移入自进化流程。但 `plans/fullstack-design` 仍停留在 V1 目标态：D10 声明单组织共享不做行级隔离，自进化输入以外部 `probe_reports` 为唯一来源，错误详情一个 bad case 只有一条归因，也没有总览/空间/上报接口的定义。V2 实现类 issue 需要可链接的设计依据（issue 正文契约：冲突时以链接章节为准），必须先把目标态设计补进文档树。

## 目标

- 定义 V2 三大主题的目标态设计：鉴权接入与工作空间、总览与 Session 列表、归因进自进化与多归因错误详情。
- 覆盖用户 7 点需求：多用户不开放注册 + 鉴权接入预留；多工作空间与角色；空间 bad case 上报接口与额度；总览双视角与下钻；Session 最新 10 条 + 回车查询；归因进自进化（关联 Session → 潜在策略 → 归因/非该对象 → 缓存）；错误详情左栏多归因。
- 保持 V1 已实现行为的陈述可追溯：V1 文档冻结标注 + 补篇指针，不全文改写。
- 给出代码改动地图与实施切片顺序，供后续 V2 实现 issue 直接引用。

## 设计依据

- [01-architecture.md §4.4](../../../plans/fullstack-design/01-architecture.md)：鉴权链路与空间授权在总体架构中的位置。
- [05-api-design.md §3.7–§3.10、§4.16–§4.20](../../../plans/fullstack-design/05-api-design.md)：空间/成员/凭据/上报/总览/归因端点与 DTO。
- [06-database-design.md §3.10–§3.12、§4.2、§5.3–§5.4、§5.9、§7.5、§9](../../../plans/fullstack-design/06-database-design.md)：空间表、归因表（由 `probe_reports` 演进）、簇与成员表、候选表、V2 口径与迁移。
- [07-backend-implementation.md §5.11–§5.15、§8.2.1](../../../plans/fullstack-design/07-backend-implementation.md)：七步管线、潜在匹配、归因缓存、空间服务与鉴权接缝。
- [08-frontend-implementation.md §1.4、§4.2、§5.2.1、§6、§7、§9、§10](../../../plans/fullstack-design/08-frontend-implementation.md)：空间壳、总览、最新 10 条、多归因、四步向导、七步详情。
- [README.md 决策表 D21–D23](../../../plans/fullstack-design/README.md)：V2 顶层决策与 V1 冻结语义。
- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md)：V2 原型验收基线。

## 实现内容

- 按域把 V2 设计并入 01–08（不新增补篇）：01 架构边界/模块/链路；02 功能点 F21–F27 与验收；03 路由/状态/组件/目录；04 模块/接入/配置/扩展/测试；05 DTO 与端点；06 表结构与迁移；07 管线与实现；08 页面与交互。
- 01：空间输入/输出/不做清单、workspaces 服务、七步执行链、auth/session 与空间授权、数据接入表、扩展与风险。
- 02：§2.4（F21–F27 + 五个 V1 功能点变更）与 §2.5（V2 验收口径）。
- 03：空间前缀路由、空间守卫、queryKey 带 `wid`、空间/总览/多归因组件与目录。
- 04：workspaces/overview 模块、上报写入边界、归因引擎占位、V2 配置项与测试策略。
- 05：§3.7–§3.10 新 DTO（Workspace/Member/Credential/Ingest/Attribution/Overview）；§3.6.2 七步 payload；§4.16–§4.20 端点；§5 深链；§8 完整 V2 错误码；§9 映射。
- 06：workspaces/workspace_members/workspace_ingest_credentials；bad_cases.workspace_id；evolution_runs 三个新列；归因与簇表在既有表上演进（`probe_reports → bad_case_attributions`、`probe_clusters → evolution_clusters`、`probe_cluster_probes → evolution_cluster_members`），`bad_case_analysis` 删除；新增 `evolution_run_candidates`；§7.5 口径；§9 迁移。
- 07：归一化补 tree_index/triggered_at；七步 prepare；潜在匹配；归因缓存；预览端点；空间服务与依赖；鉴权接缝；测试与切片顺序。
- 08：路由与重定向；api 模块与 queryKeys；空间管理四 Tab；最新 10 条 + 回车；总览页；多归因错误详情；四步向导；七步详情与 `stepsSchema` 双轨。
- 新增 Agent Note 三件套 `.agents/notes/proposed/feature/2026-11-11-v2-design-docs.*`（决策与取舍）。

## 实施步骤

1. 通读 V1 设计文档与当前代码实现，确认差距基线（端点/表/服务逐项核对）。
2. 对比 V1/V2 原型，核实 7 点需求的 UI 覆盖与出入。
3. 按域把 V2 设计写进 01–08（不新增补篇），同步修正跨文档不一致（错误码、列、`blocked_stage`、admin 路径规则）。
4. 删除临时补篇 15–17，清理全部引用（README/02/09）。
5. 新增 Agent Note 并重录 i18n 配对。

## 依赖与交付边界

- 依赖：无
- 非目标：不改任何生产代码（`apps/api`、`apps/web`、`packages/contracts`）；不建 V2 实现 issue；不改 V2 原型 HTML。

## 独立验证

```sh
pnpm verify:flow; pnpm lint:docs
```

- 全绿；`verify-flow --diff origin/main` 对本 PR diff 的 scope 覆盖通过。

## 验收标准

- 01–08 覆盖 7 点需求，且每项都有数据模型、API 契约与代码改动地图。
- 总览/向导/run 三处的「潜在 bad case」口径声明为同一实现。
- V1 已实现行为有冻结标注，历史 run 渲染兼容（`stepsSchema` 双轨）写明。
- 05 错误码表覆盖 V2 全部错误码；06 列定义与 05/07 引用一致；归因/簇表为「演进」而非新增（与 D23 一致）。
- README 决策表含 D21–D23；02 含 F21–F27；Agent Note 双语配对完整。

## 门禁与 CI

- `pnpm verify:flow`：issue 三件套、状态机与 scope 覆盖。
- `pnpm lint:docs` / `pnpm verify:docs`：Agent Note 配对与文档门禁。
- 纯文档改动，不触发 API/Web 构建与测试 lane 的行为变化。

## 非目标

- 不实现任何 V2 功能代码或数据库迁移。
- 不重写 V1 文档正文（只加补篇与指针）。
- 不在本 issue 内裁决 V2 实现 issue 的排期与切分。
