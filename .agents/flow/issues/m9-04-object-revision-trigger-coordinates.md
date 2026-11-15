# 对象 revision 解析、触发坐标与重放

[English](m9-04-object-revision-trigger-coordinates.en.md) | 中文

```yaml flow
kind: issue
id: m9-04
milestone: m9
depends:
  - m9-02
  - m9-03
priority: P0
status: backlog
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 239
  url: https://github.com/Shadow-Azure/harness-evolution/issues/239
```

## 背景

真实 Skill 列表可能只有内容摘要而没有语义版本；只比较 targetVersion 会漏掉整个 Session。

## 目标

- 支持 tag、digest 和 unknown 三类 object revision。
- 保存 tree_index、triggered_at 与稳定事件坐标。
- 升级 parser version 并重放形成可比较证据。

## 设计依据

- [15 §9.2–§9.3](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：revision 与触发规则。
- [06 §7.5](../../../plans/fullstack-design/06-database-design.md)：对象进入点与比较。

## 实现内容

- 解析 skill_listing 名称与 digest 映射。
- 显式工具触发和 attributionSkill 分开保存。
- triggered_at 优先，坐标字典序兜底。

## 实施步骤

1. 先写 tag/digest/unknown 解析测试。
2. 实现触发坐标与 parser version 增量重放。
3. 验证旧数据不回退为名称猜测。

## 依赖与交付边界

- 依赖：m9-02、m9-03
- 交付边界：不实现 PotentialMatcher。

## 独立验证

```sh
pnpm test:api -- tests/acquisition; pnpm data:replay:sessions; pnpm test:db
```

- 同一 digest 跨会话可稳定匹配。
- 无 digest 且无 tag 时为 unknown。
- 重放后触发时刻可跨 Agent 比较。

## 验收标准

- 对象身份不再依赖单一 version。
- 未知 revision 有明确原因。

## 门禁与 CI

- API、数据库、重放与 flow 门禁。

## 非目标

- 不把名称相同视为版本相同。
- 不保存 Skill 全文。
