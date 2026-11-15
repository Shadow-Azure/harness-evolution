# 聚类算法升级

[English](m12-04-clustering-upgrade.en.md) | 中文

```yaml flow
kind: issue
id: m12-04
milestone: m12
depends:
  - m10-04
priority: P2
status: backlog
scope:
  - apps/api/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 245
  url: https://github.com/Shadow-Azure/harness-evolution/issues/245
```

## 背景

本 issue 承接原 M6 issue #64，并于 2026-11-15 迁入 M12。旧 issue 关闭只表示里程碑重排，工作没有取消；新实现入口是 `m12-04-clustering-upgrade`。

m12-04 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m12-04 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [07 §5.5 占位聚类](../../../plans/fullstack-design/07-backend-implementation.md)
- [06 §5.3 probe_clusters](../../../plans/fullstack-design/06-database-design.md)
- [09 R11](../../../plans/fullstack-design/README.md)

## 实现内容

- 升级聚类算法但仍写 probe_clusters/probe_cluster_probes
- 保证确定性、空输入、单元素和大输入行为

## 实施步骤

1. 先写算法边界与稳定性失败测试
2. 实现新算法
3. 对比占位结果并保留 run 参数

## 依赖与交付边界

- 依赖：m10-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m12-04-clustering-upgrade
pnpm test:db
```

- 新算法测试通过且表/API 不变

## 验收标准

- 结果可复现且迁移无 schema 破坏

## 门禁与 CI

- algorithm gate、dual-db tests、fixture regression

## 非目标

- 不承诺诊断准确性
