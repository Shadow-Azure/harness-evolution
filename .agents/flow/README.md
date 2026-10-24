# 开发流程

[English](README.en.md) | 中文

> 契约 home：roadmap → milestone → issue → ADR 四层工作文件的格式、状态机与门禁。机械执行归 `verify:flow` / `verify:flow --diff` / `verify:flow-online`，本页只说规则。

## 层级

| 层 | 文件 | 职责 |
|---|---|---|
| roadmap | `roadmap.md` | 愿景、milestone 有序序列和实施规则 |
| milestone | `milestones/<id>-*.md` | 阶段目标、范围、验收与非目标 |
| issue | `issues/<milestone-id>-*.md` | 可独立验收的最小工作单元 |
| ADR | `../notes/` | 决策记录，issue 用 `adr` 关联 |

## 机读面：yaml flow 围栏

每个工作文件带且仅带一个 yaml flow 围栏；中英两侧围栏逐字节一致。roadmap 记 `kind` 与 `milestones`；milestone 记 `kind/id/title/status/github`。issue 记：

```text
kind: issue
id: m2-03
milestone: m2
depends: [m2-01, m2-02]
priority: P0
status: backlog
scope: [允许修改的 glob]
adr: [相对 Agent Note 路径]
github: {number, url}
```

`id` 是仓库内稳定规划编号；`github.number` 才是远端编号。`depends` 只能指向同 milestone 或更早 milestone 的已存在 id，且不得成环。

## Issue 正文契约

中文正文必须包含：背景、目标、设计依据、实现内容、实施步骤、依赖与交付边界、独立验证、验收标准、门禁与 CI、非目标。英文侧保持等价章节结构。`设计依据` 必须链接 `plans/fullstack-design` 的具体章节；实现冲突时以链接章节为准。`独立验证` 必须给出命令、数据和预期结果。

## 封闭集合

- issue status：`backlog` / `ready` / `in-progress` / `done`
- milestone status：`planned` / `active` / `done`
- priority：`P0` / `P1` / `P2`（P0 最高）

## 编号、依赖与推进

- draft 的 `github.number` 为 null 时只能在 backlog；`flow:sync` 回填后可流转。
- `bootstrap: true` 全库至多一个，仅允许 roadmap 第一个 milestone；编号回填后移除。
- 跨 milestone 同 priority 串行；milestone 内按既有退档规则解锁。
- in-progress/done 的依赖必须在同档或更早 milestone 且已完成；依赖环即红。

## 门禁与拦截点

| 检查 | 内容 |
|---|---|
| `pnpm verify:flow` | 全部离线规则、稳定 id、依赖、章节与状态机 |
| `verify-flow --diff <base>` | 提交/PR 标题 `(#N)`、issue 资格与 diff scope 覆盖 |
| `pnpm verify:flow-online` | GitHub milestone/issue/PR 关联一致性 |
| `pnpm test:gates` | flow 解析、依赖、正文、GitHub 正文、退休计划与路由自测试 |

## GitHub 同步

`pnpm flow:sync` 是唯一 GitHub 写入口。它按本地详细中文正文创建/更新 issue body，同步状态，并在显式 `-- --retire-missing` 时关闭不在本地流程树中的开放 issue/milestone。**远端对象只关闭，不物理删除。** 需要 gh 已登录；Projects v2 强校验需 `FLOW_TOKEN`。

## 工具

`pnpm flow:new-issue -- --milestone <id> --id <milestone-NN> --priority <P0> --slug <kebab> --title <中文标题> --title-en <English title> --scope <glob,glob> --depends <id,id>` 生成三件套骨架；生成后必须补齐正文契约。
