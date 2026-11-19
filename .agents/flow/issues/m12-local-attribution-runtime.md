# 本地 Agent 按生效 Skill 逐 Badcase 生成归因报告并入库

[English](m12-local-attribution-runtime.en.md) | 中文

```yaml flow
kind: issue
id: m12-26
milestone: m12
depends:
  - m12-23
priority: P0
status: done
scope:
  - scripts/flow-sync.mjs
  - apps/api/**
  - apps/web/**
  - attribute-badcases/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 387
  url: https://github.com/Shadow-Azure/harness-evolution/issues/387
```

## 背景

空间包和对象绑定需要在启动运行时解析为实际可执行的归因指令。

## 目标

为每个入选候选使用配置的 Agent 和模型生成规范报告。

## 设计依据

[执行与持久化设计](../../../plans/fullstack-design/07-backend-implementation.md)

## 实现内容

固定所选包，准备证据与对象提示词，调用 Agent，校验平台脚本输出，并在同一数据库事务中提交报告与候选关联。

## 实施步骤

1. 整合 main。
2. 接通生效包与执行器。
3. 验证 SQLite 入库和重试。

## 依赖与交付边界

复用 #374 包管理与 #315 执行器边界。

## 独立验证

使用临时 SQLite 库运行 `pnpm test:api -- tests/attribution/test_local_runtime.py`。合成 Badcase 生成单条脚本报告，SQLite 关联同一 case，二次运行复用结果。

## 验收标准

对象绑定优先于空间和平台默认包；flow/context 贯通报告和聚类；非法输出不会入库。

## 门禁与 CI

API 测试、类型检查与接口契约生成。

## 非目标

历史 Run 保留自身的执行器身份。
