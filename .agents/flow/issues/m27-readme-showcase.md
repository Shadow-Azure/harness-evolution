# 重写 README：项目介绍、核心能力与一张关键截图

[English](m27-readme-showcase.en.md) | 中文

```yaml flow
kind: issue
id: m27-01
milestone: m27
depends: []
priority: P2
status: ready
scope:
  - README.md
  - README.en.md
  - README.i18n.yaml
  - docs/assets/readme/**
  - scripts/doc-budgets.manifest.json
  - docs/**
  - .agents/**
adr: []
github:
  number: 461
  url: https://github.com/Shadow-Azure/harness-evolution/issues/461
```

## 背景

根 `README.md` 仍以“M1 工程骨架推进中”开头，正文主体是快速开始、生产部署前置与目录结构；它没有回答新读者最关心的问题：这个工程解决什么问题、现在能做什么、界面长什么样。项目已交付到 M25（工作空间、轨迹归一化、多归因、七步自进化与 lane DAG），这份状态描述与实现脱节，也和 `docs/architecture.md` 的“已具备 / 未具备”不一致。

常见的高 star 项目 README 用一句话定位、一组能力要点、一张主界面截图和可复制的快速开始构成第一屏，再链接到详细文档。本 issue 按这个结构重写根 README，并补一张来自本地 fixtures 的关键截图；生产环境只用于人工走查，不把生产 Session 内容或截图提交到仓库。

## 目标

- 用一句话说明服务定位，并用“核心能力”覆盖轨迹查看、问题归因、自进化闭环与工程边界。
- 首次访问即可看到一张产品主界面截图：Session 浏览器、执行流 lane DAG 与问题卡；截图来自本地 `pnpm fixtures:seed` 的合成数据，不含生产内容。
- 保留可复制的本地快速开始；生产部署、架构与开发细节继续由 `docs/` 承载，README 只链接。
- 中英两侧保持结构镜像并重录配对；`README.md` 仍是中文 base。
- 截图作为受版本管理的静态资源落在 `docs/assets/readme/`，路径在 GitHub 上可直接渲染。

## 设计依据

- [02 §2 功能点明细](../../../plans/fullstack-design/02-features.md)：核心能力条目以 Session 错误查看、自进化与横切能力的功能点为准。
- [01 §2 组成与分层](../../../plans/fullstack-design/01-architecture.md)：快速开始后的目录结构按 `apps/web`、`apps/api`、`packages/contracts` 等实际分层描述。
- [01 §5.3 演示数据的边界](../../../plans/fullstack-design/01-architecture.md)：截图使用 fixtures 演示数据，不提交生产 Session、提示词、文档正文或凭据。
- [docs/AGENTS.md](../../../docs/AGENTS.md) 与 [docs/i18n/README.md](../../../docs/i18n/README.md)：根 README 是常驻文档，需双语成对、登记词数预算并重录配对。
- [Best-README-Template](https://github.com/othneildrew/Best-README-Template)：一句话定位 → 截图 → 能力 → 快速开始 → 文档入口的常见组织方式。

## 实现内容

- `README.md`：替换 M1 状态段，新增产品截图、核心能力、快速开始与文档入口；删除与 `docs/deployment.md` 重复的生产部署前置，只保留指路链接。
- `README.en.md`：按同一结构重写英文侧，链接改 `.en.md`，代码围栏内容与中文侧逐字一致。
- `docs/assets/readme/session-overview.png`：在本地 fixtures 演示环境用 1440×900、2× DPR、浅色主题截取 Session 浏览器、执行流与问题卡；图中只有合成数据和“演示数据”标识。
- `README.i18n.yaml`：重录两侧 blob hash；两侧结构镜像由 `verify:docs` 校验。
- `scripts/doc-budgets.manifest.json`：把 `README.md` 预算从 400 调到 500，理由是新版增加定位、能力与截图说明，同时把生产部署细节移出 README；PR 说明该调整。
- 新增一条 `process` Agent Note，记录 README 的读者、截图数据边界与只保留一张截图的取舍。

## 实施步骤

1. 在本地 fixtures 环境登录并截取 Session 详情页，确认图中只有合成数据与“演示数据”标识。
2. 重写中英 README，按“定位 → 截图 → 能力 → 快速开始 → 文档 → 结构”组织，并删除过时的 M1 状态与重复部署段。
3. 新增图片资源与 Agent Note，调整词数预算，重录 README 配对。
4. 运行 `pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`，检查渲染后的图片路径与链接。
5. 提交并开 PR，标题带 issue 编号；PR 描述给出截图来源与预算调整理由。

## 依赖与交付边界

- 依赖：无代码依赖；使用现有 `pnpm fixtures:seed` 与本地演示环境。
- 交付：README 双语、截图资源、Agent Note、预算与配对记录；不改应用代码、接口、契约或 UI。
- 边界：不使用生产截图或 Session 内容；不新增第二张截图、GIF 或视频；不把部署细节搬进 README。

## 独立验证

```sh
node --input-type=module -e "import { countWords } from './scripts/verify-doc-budgets.mjs'; import { readFileSync } from 'node:fs'; console.log(countWords(readFileSync('README.md','utf8')))"
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
```

- 词数输出 ≤ 500；`lint:docs` 与 `verify:docs` 通过（含配对、死链、图片路径与换行门禁）；`verify:flow` 通过。
- 本地渲染 README，确认截图可见、说明写明“本地合成 fixtures”，所有相对链接可达。
- 用 `git diff --stat` 确认只改 README、图片、Note、预算与流程文件。

## 验收标准

- 首次打开 README 能在第一屏看到定位、关键截图与能力摘要；快速开始命令可直接复制执行。
- README 描述与 `docs/architecture.md` 的当前能力一致，不再出现“M1 工程骨架推进中”。
- 中英两侧结构镜像、配对记录一致；图片文件入库且 GitHub 渲染正常。
- 无生产 Session 内容、提示词、凭据或真实用户数据进入仓库。
- 文档、流程与配对门禁全绿。

## 门禁与 CI

- 命中文档门禁：`lint:docs`、`verify:docs`（含词数预算、配对、死链、图片路径、换行）。
- 命中流程门禁：`verify:flow`，PR 期间 `verify:flow --diff` 校验标题与 scope。
- CI 的 docs-flow lane 覆盖上述检查；不新增代码测试。

## 非目标

- 不改应用 UI、交互、路由或截图以外的产品行为。
- 不重写 `docs/` 的架构、部署与开发文档，只删除 README 中重复的部署段并保留链接。
- 不引入徽章、GIF、视频或多张截图；不加工或伪造生产数据。
- 不调整 README 之外的双语文档。
