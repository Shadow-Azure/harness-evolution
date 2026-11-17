# V2 文档收口、兼容层与退役计划

[English](m11-06-v2-compatibility-retirement.en.md) | 中文

```yaml flow
kind: issue
id: m11-06
milestone: m11
depends:
  - m11-05
priority: P1
status: in-progress
scope:
  - docs/**
  - plans/**
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 221
  url: https://github.com/Shadow-Azure/harness-evolution/issues/221
```

## 背景

V2 落地后，architecture、roadmap、兼容端点和原型边界需要反映已交付事实，并给出旧入口删除条件。

## 目标

- 更新 docs/architecture 与 development 当前事实。
- 记录 V1 probe、旧路由和旧深链退役条件。
- 把设计 Note 与实际实现同步。

## 设计依据

- [15 §7–§9](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：实施与兼容边界。
- [README 与仓库现状](../../../plans/fullstack-design/README.md)：文档同步要求。

## 实现内容

- 记录旧 /api/probes、旧路由和旧 run schema 的下个大版本移除条件。
- 更新双语常驻文档并重录 i18n。
- 把证据门禁和 knowledge trigger 写入架构现状。

## 实施步骤

1. 逐项核对已实现端点与表。
2. 更新中英常驻文档和 Agent Note。
3. 运行 docs/flow 门禁并确认无未登记预算。

## 依赖与交付边界

- 依赖：m11-05
- 交付边界：不删除仍处于兼容窗口的端点。

## 独立验证

```sh
pnpm record:i18n -- docs/architecture.md; pnpm verify:docs; pnpm verify:flow
```

- 常驻文档无 V1 单组织或单归因错误描述。
- 兼容退役有触发版本与验证条件。
- 中英配对哈希最新。

## 验收标准

- 一个事实一个 home 的原则保持。
- 后续删除兼容层有机械检查清单。

## 门禁与 CI

- 文档、流程与发布门禁。

## 非目标

- 不在兼容窗口内直接删除旧接口。
- 不把未来计划写成当前已实现。
