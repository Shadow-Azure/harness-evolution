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

- [15-v2-workspaces.md](../../../plans/fullstack-design/15-v2-workspaces.md)：鉴权接入接缝、空间/成员/额度/凭据模型、上报接口、空间化迁移与权限矩阵。
- [16-v2-overview.md](../../../plans/fullstack-design/16-v2-overview.md)：总览双视角口径、聚合接口、Session 最新 10 条 + 回车查询。
- [17-v2-attribution.md](../../../plans/fullstack-design/17-v2-attribution.md)：七步流程、触发点坐标、潜在策略、归因缓存、多归因错误详情、probe 链路退役。
- [README.md 决策表 D21–D23](../../../plans/fullstack-design/README.md)：V2 顶层决策与 V1 冻结语义。
- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md)：V2 原型验收基线。

## 实现内容

- 新增三篇补篇 `15-v2-workspaces.md` / `16-v2-overview.md` / `17-v2-attribution.md`（沿续 11–14 号体例：背景、数据模型、API 契约、代码改动地图、测试与验收、非目标、已确认决策）。
- README：文档地图加三行、决策表追加 D21/D22/D23、系统一句话说明与数据边界段落更新、V2 与仓库现状关系。
- 02-features：新增 §2.4（F21–F27 七个 V2 功能点 + 五个 V1 功能点变更表）。
- 05-api-design：§4 端点清单追加 V2 增补块；§8 错误码表追加 12 个 V2 错误码。
- 06-database-design：§1 表分类追加 V2 增补块（新表 + 加列 + 冻结清单）。
- 01-architecture / 07-backend-implementation / 08-frontend-implementation：边界修订（空间输入/输出/不做清单、workspaces 服务）与 V1 冻结注记。
- 新增 Agent Note 三件套 `.agents/notes/proposed/feature/2026-11-11-v2-design-docs.*`（补篇方案与关键取舍）。

## 实施步骤

1. 通读 V1 设计文档与当前代码实现，确认差距基线（端点/表/服务逐项核对）。
2. 对比 V1/V2 原型，核实 7 点需求的 UI 覆盖与出入。
3. 撰写三篇补篇（含 API/表结构/代码改动地图/测试）。
4. 同步修订 README/01/02/05/06/07/08 指针与增补块。
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

- 三篇补篇覆盖 7 点需求的每一项，且都有明确的数据模型、API 契约与代码改动地图。
- 总览/向导/run 三处的「潜在 bad case」口径声明为同一实现（PotentialMatcher）。
- V1 已实现行为在 05/06/07/08 中有冻结标注，历史 run 渲染兼容（steps_schema 双轨）写明。
- README 决策表含 D21–D23；02 功能点表含 F21–F27；05 错误码表含 V2 新码。
- Agent Note 双语三件套配对记录完整。

## 门禁与 CI

- `pnpm verify:flow`：issue 三件套、状态机与 scope 覆盖。
- `pnpm lint:docs` / `pnpm verify:docs`：Agent Note 配对与文档门禁。
- 纯文档改动，不触发 API/Web 构建与测试 lane 的行为变化。

## 非目标

- 不实现任何 V2 功能代码或数据库迁移。
- 不重写 V1 文档正文（只加补篇与指针）。
- 不在本 issue 内裁决 V2 实现 issue 的排期与切分。
