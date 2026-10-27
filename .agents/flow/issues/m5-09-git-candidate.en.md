# m5-09 Git Candidate

English | [中文](m5-09-git-candidate.md)

```yaml flow
kind: issue
id: m5-09
milestone: m5
depends:
  - m5-08
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - plans/*.md
  - plans/fullstack-design/**
  - scripts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 58
  url: https://github.com/Shadow-Azure/harness-evolution/issues/58
```

## Background





m5-09 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-09 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [07 §5.6 git 链路](../../../plans/fullstack-design/07-backend-implementation.md)
- [01 §6 分支策略](../../../plans/fullstack-design/01-architecture.md)
- [09 R12/R13](../../../plans/fullstack-design/README.md)

## Implementation





- 实现临时 workspace、clone tag/ref、run 分支、candidate commit/ref、push 重试、接纳 amend+ff、拒绝删 ref
- 同步修正 candidate 可见 ref 的存储事实：run 分支在 `refs/heads`，同名 candidate 路径存 `refs/tags`，避免 Git ref 前缀冲突
- 绝不 reset run 分支
- 接通 `evolution_prepare` 真实编排（workspace/ref 校验、筛选、聚类、状态推进）与引擎注册表校验（`engine_key` → 422 `ENGINE_INVALID`）

## Implementation steps





1. 用临时 git 和 bare remote 写 happy/failure/conflict/恢复失败测试
2. 实现 GitWorkspace
3. 验证 candidate message 追溯

## Dependencies and boundary





- 依赖：m5-08
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-09-git-candidate
pnpm test:db
```

- push 失败标 blocked
- 接纳后 run 分支 ff
- 拒绝后 candidate 删除且 run 不污染

## Acceptance





- 每次候选都有 commit 与远端 ref

## Gates and CI





- git integration gate、failure injection、workspace cleanup test

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
