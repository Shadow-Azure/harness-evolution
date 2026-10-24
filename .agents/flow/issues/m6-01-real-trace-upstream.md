# m6-01 real trace upstream

[English](m6-01-real-trace-upstream.en.md) | 中文

```yaml flow
kind: issue
id: m6-01
milestone: m6
depends:
  - m5-11
priority: P1
status: backlog
scope:
  - apps/api/**
  - plans/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 61
  url: https://github.com/Shadow-Azure/harness-evolution/issues/61
```

## 背景

m6-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m6-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §10 上游契约](../../../plans/fullstack-design/05-api-design.md)
- [04 §5 数据接缝](../../../plans/fullstack-design/04-backend-architecture.md)
- [09 R9/R10](../../../plans/fullstack-design/README.md)

## 实现内容

- 将 HttpApiSource 接到真实上游，验证凭据注入、按需 pull、分页、失败隔离和版本监控
- PR CI 仍用 mock

## 实施步骤

1. 用环境凭据做 opt-in 集成测试
2. 实现健康/漂移日志和手动重放
3. 保持 fixtures CI

## 依赖与交付边界

- 依赖：m5-11
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m6-01-real-trace-upstream
pnpm test:db
```

- 本地/受控环境真实 pull 成功
- CI 不访问真实上游

## 验收标准

- 上游故障不阻塞 payload 表路径

## 门禁与 CI

- integration opt-in gate、contract monitor tests

## 非目标

- 不提交凭据
