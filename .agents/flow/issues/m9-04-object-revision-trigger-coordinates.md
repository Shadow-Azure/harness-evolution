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
status: in-progress
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - apps/api/tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 239
  url: https://github.com/Shadow-Azure/harness-evolution/issues/239
```

## 背景

真实 Skill 列表可能只有内容摘要和 16 位不透明 digest，而没有语义版本；subagent 的 prompt_snapshot 则包含 agent 定义 body。只比较 targetVersion 会漏掉整个 Session，只依赖 skill_listing.digest 也无法确认算法。

## 目标

- 支持 tag、digest 和 unknown 三类 object revision。
- Skill revision 优先使用 path + 归一化 body hash；listing digest 只作 fallback。
- Agent revision 使用 agentType + isBuiltIn + systemPrompt[0] body hash。
- 保存 tree_index、triggered_at 与稳定事件坐标。
- 升级 parser version 并重放形成可比较证据。

## 设计依据

- [15 §9.2–§9.3](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份)：revision 与触发规则。
- [06 §7.5](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态)：对象进入点与比较。
- [07 §2.6 多 runtime parser 工厂](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂)：evidence hook 的 runtime 边界。

## 实现内容

- 解析 Skill meta 注入的 path/body hash，以及 agent prompt_snapshot/definition hash。
- skill_listing digest 仅保留为 opaque fallback；算法未确认前不作为主键。
- 显式工具触发和 attributionSkill 分开保存。
- triggered_at 优先，坐标字典序兜底；无坐标的 runtime 记 unknown。
- 升级 parser version 只重放对应 runtime。

## 实施步骤

1. 先写 tag/digest/body-hash/unknown 解析测试。
2. 实现触发坐标与 parser version 增量重放。
3. 验证 agent/skill 定义 hash 可跨任务稳定、跨 runtime 不串。
4. 验证旧数据不回退为名称猜测。

## 依赖与交付边界

- 依赖：m9-02、m9-03
- 交付边界：不实现 PotentialMatcher。

## 独立验证

```sh
pnpm test:api -- tests/acquisition; pnpm data:replay:sessions; pnpm test:db
```

- 同一 Skill body 跨会话可稳定匹配。
- 同一 agent 类型不同任务得到相同定义 hash。
- 无 body 且无 tag 时为 unknown。
- skill_listing digest 只在算法确认后作为 fallback。
- 重放后触发时刻可跨 Agent 比较。

## 验收标准

- 对象身份不再依赖单一 version 或名称。
- 未知 revision 有明确原因。
- Skill/agent 全文不落库，只落 path/hash/source。

## 门禁与 CI

- API、数据库、重放与 flow 门禁。

## 非目标

- 不把名称相同视为版本相同。
- 不保存 Skill 或 agent 定义全文。
- 不依赖未确认算法的 skill_listing digest。
