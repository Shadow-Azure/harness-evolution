# 七步 prepare、聚类输入与历史 run 适配

[English](m10-04-seven-step-prepare.en.md) | 中文

```yaml flow
kind: issue
id: m10-04
milestone: m10
depends:
  - m10-03
priority: P0
status: in-progress
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/service/jobs.py
  - apps/api/app/db/**
  - apps/api/app/api/**
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 213
  url: https://github.com/Shadow-Azure/harness-evolution/issues/213
```

## 背景

新 run 必须从空间 bad case 依次经过 Session、潜在、归因和聚类；历史六步 run 仍需只读。

## 目标

- 实现 unit 0–6 状态与 prepare 管线。
- 聚类只消费 attributed 候选。
- 服务端把历史 run 适配成统一七步 DTO。

## 设计依据

- [07 §5.11](../../../plans/fullstack-design/07-backend-implementation.md)：七步 prepare。
- [05 §3.6](../../../plans/fullstack-design/05-api-design.md)：七步产出。

## 实现内容

- 候选批量写入并保持 run 内幂等。
- blocked attribution 可按阶段重试。
- 七步端点共享同一 build_step_payload。

## 实施步骤

1. 先写状态机和重入测试。
2. 替换 prepare 链路并切换聚类输入。
3. 补历史 run 快照测试。

## 依赖与交付边界

- 依赖：m10-03
- 交付边界：不改 patch/eval 真实执行器。

## 独立验证

```sh
pnpm test:api -- tests/evolution; pnpm contract:check
```

- unit 仅按 0–6 推进。
- 重复 prepare 不重复候选。
- 历史 run 映射后键序一致。

## 验收标准

- 新 run 七步可恢复。
- cluster_only 只走到聚类。

## 门禁与 CI

- API、状态机、契约与 flow 门禁。

## 非目标

- 不伪造评测结果。
- 不删除历史六步数据。
