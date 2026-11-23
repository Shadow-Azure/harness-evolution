# V2 跨栈 fixture、迁移与安全验收

[English](m11-05-v2-cross-stack-verification.en.md) | 中文

```yaml flow
kind: issue
id: m11-05
milestone: m11
depends:
  - m8-05
  - m10-06
  - m11-02
  - m11-04
  - m11-07
priority: P0
status: done
scope:
  - tests/**
  - fixtures/**
  - reports/**
  - plans/**
  - apps/api/**
  - apps/web/**
  - scripts/run-api.mjs
  - .github/workflows/ci.yml
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 220
  url: https://github.com/Shadow-Azure/harness-evolution/issues/220
```

## 背景

V2 变更横跨身份、空间、上报、轨迹证据、归因和多归因页面，需要一套跨栈验收而不是逐个模块绿。

## 目标

- 建立完整 V2 fixture 与权限矩阵。
- 验证 SQLite/MySQL、迁移、重放和 SSE。
- 以真实形状覆盖 Skill、Agent、knowledge 三类触发。

## 设计依据

- [15 §8–§9](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：验收重点和证据门禁。
- [02 §4–§5](../../../plans/fullstack-design/02-features.md)：V2 阶段和验收。

## 实现内容

- fixture 覆盖默认空间、多空间和派生父子关系。
- E2E 覆盖登录、空间切换、上报、总览、向导、run、错误详情、lane DAG 与结构树切换。
- 输出脱敏 smoke evidence。

## 实施步骤

1. 先写完整失败场景清单。
2. 实现 fixture 与跨栈用例。
3. 执行双库、门禁和视觉 E2E 并归档报告。

## 依赖与交付边界

- 依赖：m8-05、m10-06、m11-02、m11-04、m11-07
- 交付边界：发现问题回到 owning issue，不在本 issue 改写产品语义。

## 独立验证

```sh
pnpm test:all; pnpm verify:docs; pnpm verify:bundle; pnpm verify:web-style
```

- 跨空间越权全部返回 404/403。
- 上报额度、缓存复用和三处潜在数一致。
- 无控制台错误和明显视觉回归。

## 验收标准

- V2 七点需求均有自动化证据。
- 真实形状 fixture 不包含原文敏感内容。

## 门禁与 CI

- 全仓测试、双库、E2E、docs、bundle、style 与 flow 门禁。
- MySQL lane 通过 `test:db:mysql` 执行 V2 迁移验收用例。

## 非目标

- 不隐瞒环境预存失败。
- 不以手工截图替代 API 断言。
