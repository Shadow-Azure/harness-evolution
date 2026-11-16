# PotentialMatcher 与三段预览

[English](m10-02-potential-matcher-preview.en.md) | 中文

```yaml flow
kind: issue
id: m10-02
milestone: m10
depends:
  - m9-03
  - m9-04
  - m9-05
  - m10-01
priority: P0
status: in-progress
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/service/catalogs.py
  - apps/api/app/api/**
  - apps/api/conftest.py
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/app/errors.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 211
  url: https://github.com/Shadow-Azure/harness-evolution/issues/211
```

## 背景

向导、run 和总览必须用同一实现判断对象出现、潜在 case 和复缓存，避免三处数量漂移。

## 目标

- 实现 Skill、Agent、knowledge 的 associated_sessions。
- 实现默认与自定义潜在策略。
- 实现 sessions、potential、attribution 三段预览。

## 设计依据

- [07 §5.12、§5.14](../../../plans/fullstack-design/07-backend-implementation.md)：潜在匹配与预览。
- [15 §9.3、§9.5](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：知识触发和里程碑落点。

## 实现内容

- 按规范化 revision 精确关联。
- 未知 revision 返回原因码，不做名称猜测。
- 预览不执行归因，只计算缓存命中数。

## 实施步骤

1. 先写策略真值表和三类对象测试。
2. 实现 matcher、分页和 conditions。
3. 让 run prepare 复用同一服务。

## 依赖与交付边界

- 依赖：m9-03、m9-04、m9-05、m10-01
- 交付边界：不实现归因引擎和前端向导。

## 独立验证

```sh
pnpm test:api -- tests/evolution tests/potential; pnpm contract:check
```

- 默认策略两支并集正确。
- unknown revision 不计命中。
- 预览与 prepare 对同输入一致。

## 验收标准

- 三处潜在口径只有一份实现。
- knowledge 与 skill/agent 使用同一坐标比较。

## 门禁与 CI

- API、契约、性能与 flow 门禁。

## 非目标

- 不按名称模糊匹配。
- 不在预览阶段写归因结论。
