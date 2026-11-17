# 四步启动向导与启动集成

[English](m10-05-four-step-launch-wizard.en.md) | 中文

```yaml flow
kind: issue
id: m10-05
milestone: m10
depends:
  - m10-02
  - m10-03
  - m7-08
priority: P1
status: done
scope:
  - apps/web/src/pages/evolution/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - apps/api/app/service/evolution/**
  - apps/api/tests/**
  - packages/contracts/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 214
  url: https://github.com/Shadow-Azure/harness-evolution/issues/214
```

## 背景

用户需要在上游看到对象出现、潜在 case 和缓存预览，再选择仅聚类或启动完整自进化。

## 目标

- 实现范围策略、Session、潜在、归因预览四步。
- 支持 focusCaseId 从错误详情进入。
- 202 后跳准备中的 run 或 cluster preview。

## 设计依据

- [08 §9](../../../plans/fullstack-design/08-frontend-implementation.md)：启动向导。
- [05 §4.20](../../../plans/fullstack-design/05-api-design.md)：预览与启动端点。

## 实现内容

- 对象列表按空间加载。
- 策略 custom 必须至少选一条规则。
- 缓存开关切换重新请求预览。

## 实施步骤

1. 先写状态机与空态测试。
2. 实现四步表单和预览表格。
3. 补启动与仅聚类 E2E。

## 依赖与交付边界

- 依赖：m10-02、m10-03、m7-08
- 交付边界：不实现七步详情。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern launch-wizard-v2
```

- 修改普通输入不重算前置步骤。
- 无关联/无潜在时禁用前进。
- 两个出口跳正确路由。

## 验收标准

- 四步信息与原型一致。
- 前端不自行重算潜在口径。

## 门禁与 CI

- Web、E2E、bundle 与 flow 门禁。

## 非目标

- 不收集模型多选。
- 不在向导内执行归因。
