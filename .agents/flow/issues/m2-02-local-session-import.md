# m2-02 local session import

[English](m2-02-local-session-import.en.md) | 中文

```yaml flow
kind: issue
id: m2-02
milestone: m2
depends:
  - m2-01
priority: P0
status: backlog
scope:
  - apps/api/**
  - scripts/**
  - fixtures/**
  - package.json
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 34
  url: https://github.com/Shadow-Azure/harness-evolution/issues/34
```

## 背景

m2-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m2-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [01 §4.1 原始轨迹链路](../../../plans/fullstack-design/01-architecture.md)
- [04 §5.2 payload 与归一化](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3.0 trajectory_payloads](../../../plans/fullstack-design/06-database-design.md)

## 实现内容

- 实现开发专用 Claude session 目录到 trajectory_payloads 的导入器
- 按每 agent 一行写入 SQLite
- 聚合输出 4 root、66 JSONL、62 subagent、约 50MB
- 不读取或提交正文以外的本地状态

## 实施步骤

1. 写本地导入命令与 baseline 断言
2. 用合成 fixture 覆盖接口
3. 本地执行真实导入
4. 生成 gitignored data/harness-evolution.sqlite

## 依赖与交付边界

- 依赖：m2-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m2-02-local-session-import
pnpm test:db
pnpm data:import:sessions
pnpm verify:local-sessions
```

- pnpm data:import:sessions 成功
- pnpm verify:local-sessions 输出 4/66/62 且 sqlite 行数为 66
- git status 无 data

## 验收标准

- 66 条 agent payload 入 SQLite
- 重复导入不新增
- 本地数据不进 Git

## 门禁与 CI

- local-data gate、payload schema 测试、数据卫生 gate

## 非目标

- 不做生产文件扫描
- 不把本地数据用于 CI
