# Real patch generation and evaluation execution

English | [中文](m12-03-real-patch-eval.md)

```yaml flow
kind: issue
id: m12-03
milestone: m12
depends:
  - m10-04
  - m12-02
priority: P1
status: backlog
scope:
  - apps/api/**
  - scripts/**
  - plans/**
  - docs/**
  - deploy/**
  - .github/workflows/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 244
  url: https://github.com/Shadow-Azure/harness-evolution/issues/244
```

## Background

This issue continues M6 issue #63 and moved to M12 on 2026-11-15. Closing the old issue only records the milestone rebalance; the work remains active through `m12-03-real-patch-eval`.





m12-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m12-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [07 §5.6–5.8 执行](../../../plans/fullstack-design/07-backend-implementation.md)
- [01 §4.3 自进化](../../../plans/fullstack-design/01-architecture.md)
- [09 R11](../../../plans/fullstack-design/README.md)

## Implementation





- 替换占位 patch/评测：生成最小配置变更、真实提交、candidate push、真实评测结果与终评
- 前端零改动
- `deploy/**` and `.github/workflows/**` are in scope: the user requires the production eval config (`HE_EVAL_*`) to be injected into the server `.env` via GitHub Secrets, covering the deploy template, the release workflow, and the deployment docs; secrets never enter the repository, only `/opt/harness/shared/.env` on the server.

## Implementation steps





1. 实现 patch/eval adapter 和 opt-in 真实用例
2. 选择一条真实 bad case 走完整闭环
3. 记录证据

## Dependencies and boundary





- 依赖：m5-11
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m12-03-real-patch-eval
pnpm test:db
pnpm contract:check
```

- 一条真实问题完成 patch→push→eval→接纳/拒绝
- UI 类型不变

## Acceptance





- 闭环结果有 run/cluster/probe/bad_case 追溯

## Gates and CI





- real integration gate、redaction tests、E2E smoke

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
