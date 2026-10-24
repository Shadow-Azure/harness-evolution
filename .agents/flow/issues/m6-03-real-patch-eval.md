# m6-03 real patch eval

[English](m6-03-real-patch-eval.en.md) | 中文

```yaml flow
kind: issue
id: m6-03
milestone: m6
depends:
  - m5-11
priority: P1
status: backlog
scope:
  - apps/api/**
  - scripts/**
  - plans/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 63
  url: https://github.com/Shadow-Azure/harness-evolution/issues/63
```

## 背景

m6-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m6-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [07 §5.6–5.8 执行](../../../plans/fullstack-design/07-backend-implementation.md)
- [01 §4.3 自进化](../../../plans/fullstack-design/01-architecture.md)
- [09 R11](../../../plans/fullstack-design/README.md)

## 实现内容

- 替换占位 patch/评测：生成最小配置变更、真实提交、candidate push、真实评测结果与终评
- 前端零改动

## 实施步骤

1. 实现 patch/eval adapter 和 opt-in 真实用例
2. 选择一条真实 bad case 走完整闭环
3. 记录证据

## 依赖与交付边界

- 依赖：m5-11
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m6-03-real-patch-eval
pnpm test:db
pnpm contract:check
```

- 一条真实问题完成 patch→push→eval→接纳/拒绝
- UI 类型不变

## 验收标准

- 闭环结果有 run/cluster/probe/bad_case 追溯

## 门禁与 CI

- real integration gate、redaction tests、E2E smoke

## 非目标

- 不自动合并到默认分支
