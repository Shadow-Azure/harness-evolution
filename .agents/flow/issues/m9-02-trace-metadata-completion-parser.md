# 真实元数据兼容与完成状态解析

[English](m9-02-trace-metadata-completion-parser.en.md) | 中文

```yaml flow
kind: issue
id: m9-02
milestone: m9
depends:
  - m9-01
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/fixture_corpus.py
  - fixtures/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 237
  url: https://github.com/Shadow-Azure/harness-evolution/issues/237
```

## 背景

真实 meta.json 已出现 isBuiltIn、pickedEffortModel、finished 等新字段，当前闭集校验会拒绝整份 Session；根会话也可能停在 tool_use。

## 目标

- 未知元数据不阻断整份导入。
- 解析未配对 tool_use、无 end_turn 子 Agent 和最终任务快照。
- 分离 requested_model、reported_model 与 model evidence。

## 设计依据

- [15 §9.2、§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：revision 与完成状态。
- [07 §2.3–§2.5](../../../plans/fullstack-design/07-backend-implementation.md)：归一化与事务。

## 实现内容

- 已知元数据严格校验，未知标量脱敏进入 meta 并产生 warning。
- 识别 tool_use 与 tool_result 配对缺口。
- 读取 task_reminder 最后快照和 stop_reason。

## 实施步骤

1. 先加入脱敏真实形状失败 fixture。
2. 实现扩展元数据和完成度解析。
3. 补重放幂等与 warning code 测试。

## 依赖与交付边界

- 依赖：m9-01
- 交付边界：不建立父子关系。

## 独立验证

```sh
pnpm test:api -- tests/acquisition; pnpm data:normalize:sessions
```

- 新字段 fixture 可导入。
- root 最后 tool_use 产生 TOOL_USE_OPEN。
- 无 end_turn 子 Agent 产生 MISSING_FINAL_REPORT。

## 验收标准

- 真实元数据漂移不会整树丢弃。
- 完成度与工具错误分开。

## 门禁与 CI

- API、数据、fixture 与 flow 门禁。

## 非目标

- 不保存原始消息或工具输出。
- 不对未知字段做业务推断。
