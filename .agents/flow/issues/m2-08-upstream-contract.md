# m2-08 upstream contract

[English](m2-08-upstream-contract.en.md) | 中文

```yaml flow
kind: issue
id: m2-08
milestone: m2
depends:
  - m2-07
priority: P1
status: backlog
scope:
  - apps/api/**
  - plans/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 40
  url: https://github.com/Shadow-Azure/harness-evolution/issues/40
```

## 背景

m2-08 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m2-08 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §10 上游查询契约](../../../plans/fullstack-design/05-api-design.md)
- [01 §5 数据来源](../../../plans/fullstack-design/01-architecture.md)
- [09 R9 风险](../../../plans/fullstack-design/README.md)

## 实现内容

- 定义轨迹包与窗口列举契约、版本头和错误模型
- 实现 HttpApiSource 并用 mock 上游验证分页、重试、版本不兼容与按条隔离

## 实施步骤

1. 先把 05 §10 转成 OpenAPI/fixture
2. 实现 source 接口与 mock 测试
3. 保留 payload 表为主路径

## 依赖与交付边界

- 依赖：m2-07
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m2-08-upstream-contract
pnpm test:db
pnpm contract:check
```

- HttpApiSource 对 mock 上游通过
- 版本不兼容返回明确错误且不写库

## 验收标准

- 契约快照稳定
- 失败按条隔离

## 门禁与 CI

- contract gate、mock 上游测试

## 非目标

- 不要求真实上游在 M2 可用
