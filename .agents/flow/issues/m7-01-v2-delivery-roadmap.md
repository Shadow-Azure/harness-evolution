# V2 交付路线图与证据门禁

[English](m7-01-v2-delivery-roadmap.en.md) | 中文

```yaml flow
kind: issue
id: m7-01
milestone: m7
depends: []
priority: P0
status: in-progress
scope:
  - .agents/flow/**
  - .agents/notes/**
  - docs/roadmap*.md
  - docs/roadmap.i18n.yaml
  - plans/fullstack-design/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/proposed/process/2026-11-15-v2-delivery-roadmap.md
github:
  number: 222
  url: https://github.com/Shadow-Azure/harness-evolution/issues/222
```

## 背景

PR #209 已合入 V2 目标态设计，但仓库流程树仍只有 M1–M6；真实 Session ccbdb2f0 又证明对象版本、父子关系和完成状态必须在归因前单独收口。

## 目标

- 新增 M7–M11 的完整 roadmap、milestone 与实现 issue。
- 把 M6 的 V2 边界调整为实现工作下沉到 M7–M11。
- 将真实 Session 暴露的版本、关系和知识库触发需求固化为 M9 门禁。

## 设计依据

- [15 §7–§9](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：实施顺序、验收重点与真实会话证据门禁。
- [README D21–D23](../../../plans/fullstack-design/README.md)：V2 顶层决策。

## 实现内容

- roadmap 增加 m7–m11；新增五个 milestone 三件套与 31 个 issue 三件套。
- m6-25 标记完成，m6 里程碑明确不承载 V2 实现。
- 新增 Agent Note 记录证据门禁与知识库触发的取舍，并同步 docs/roadmap 双语。

## 实施步骤

1. 更新 roadmap 与 milestone 文件。
2. 生成中英 issue 三件套并补齐十个正文章节。
3. 更新 M6 边界、完成既有设计 issue并同步 docs/roadmap。
4. 运行 flow/docs 门禁后同步 GitHub 流程对象。

## 依赖与交付边界

- 依赖：无
- 交付边界：只新增和调整规划、流程与决策文档，不改业务代码。

## 独立验证

```sh
pnpm verify:flow; pnpm lint:docs
```

- M7–M11 顺序、issue 依赖和 scope 全部通过离线校验。
- roadmap 与 Agent Note 的中英配对哈希最新。

## 验收标准

- roadmap、五个 milestone 和全部 issue 可从 M7 连续追溯到 M11。
- 既有 M6 文档不再宣称 V2 实现由设计 issue 承担。

## 门禁与 CI

- `pnpm verify:flow`、`pnpm lint:docs` 与 PR 的 `verify-flow --diff` 必须通过。

## 非目标

- 不启动任何 V2 业务实现。
- 不关闭与 V2 无关的 M6 开放 issue。
