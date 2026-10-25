# m2-02 Local Session Import

English | [中文](m2-02-local-session-import.md)

```yaml flow
kind: issue
id: m2-02
milestone: m2
depends:
  - m2-01
priority: P0
status: done
scope:
  - AGENTS.md
  - apps/api/**
  - scripts/**
  - .github/workflows/ci.yml
  - fixtures/**
  - package.json
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 34
  url: https://github.com/Shadow-Azure/harness-evolution/issues/34
```

## Background





m2-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m2-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [01 §4.1 原始轨迹链路](../../../plans/fullstack-design/01-architecture.md)
- [04 §5.2 payload 与归一化](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3.0 trajectory_payloads](../../../plans/fullstack-design/06-database-design.md)

## Implementation

- Implement a development-only scanner and transactional importer from Claude session directories into `trajectory_payloads`.
- Store one row per Agent and cross-check root/subagent identity across directory names, JSONL, and sidecar metadata.
- Report 4 roots, 66 JSONL files, 62 subagents, and 66 payload rows; repeated imports have zero side effects.
- Consume only JSONL and Agent metadata while ignoring local tool results and error text; fail before writing when preparation fails.

## Implementation steps





1. 写本地导入命令与 baseline 断言
2. 用合成 fixture 覆盖接口
3. 本地执行真实导入
4. 生成 gitignored data/harness-evolution.sqlite

## Dependencies and boundary





- 依赖：m2-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-02-local-session-import
pnpm test:db
pnpm data:import:sessions
pnpm verify:local-sessions
pnpm verify:local-data
```

- pnpm data:import:sessions 成功
- pnpm verify:local-sessions 输出 4/66/62 且 sqlite 行数为 66
- git status 无 data

## Acceptance





- 66 条 agent payload 入 SQLite
- 重复导入不新增
- 本地数据不进 Git

## Gates and CI





- `verify:local-data`, payload schema tests, and synthetic-directory import run in CI; the MySQL lane continues to validate the dual-dialect schema.

## Non-goals

- 不做生产文件扫描
- 不把本地数据用于 CI
