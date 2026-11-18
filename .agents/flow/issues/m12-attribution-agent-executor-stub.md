# Agent Skill 归因执行器接缝与契约桩

[English](m12-attribution-agent-executor-stub.en.md) | 中文

```yaml flow
kind: issue
id: m12-19
milestone: m12
depends:
  - m12-17
  - m12-18
priority: P0
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 315
  url: https://github.com/Shadow-Azure/harness-evolution/issues/315
```

## 背景

M10 已建立纯函数 `AttributionEngine`、对象 revision 缓存和候选写入，但唯一可执行实现仍是固定规则 `rule-v1`。生产内网的 LLM、Agent 与归因 Skill 当前不可访问；若直接在 Runner 中预埋某个内网调用，后续会把输入组装、Skill 解析、远程执行和报告校验重新耦合进缓存事务，也无法在 CI 中稳定验证真实引擎替换路径。

## 目标

- 消费 m12-16 的版本化报告契约和 m12-18 的上下文输入，不另建并行模型。
- 建立归因执行器协议，使内网 adapter 后续可独立接入。
- 提供确定性 `agent-skill-stub-v1` 引擎，贯通现有 Runner、缓存、Probe Report 与候选关联。
- 保持 `rule-v1` 默认值和既有公开 API 行为不变。

## 设计依据

- [07 §5.12–5.14](../../../plans/fullstack-design/07-backend-implementation.md)：潜在匹配、归因引擎纯函数边界与缓存。
- [06 §4.2、§5.8–5.9](../../../plans/fullstack-design/06-database-design.md)：Probe Report、缓存键和候选快照。
- [04 §5、§8](../../../plans/fullstack-design/04-backend-architecture.md)：外部接缝、任务与 executor 扩展路径。

## 实现内容

- 消费 m12-17 的 `AttributionSkillResolver`，新增 `AttributionExecutor` 协议；stub executor 不访问网络、文件或模型。
- 输入契约承载选定对象、Badcase、对象/上报触发坐标、最小证据清单、Skill 引用和上下文快照；缺失完整 Trace 时显式带 warning，不伪造证据。
- 输出契约承载 schema 版本、结论、分类、置信度、说明、推导、证据引用与 warning；执行器输出先校验再投影到现有 `AttributionResult`。
- 注册 `agent-skill-stub-v1` 引擎 key；stub 只按固定输入生成稳定输出，便于缓存、失败和后续 adapter 合同测试。
- 按 m12-16 的执行清单计算缓存身份，确保引擎、Skill revision、模型配置和上下文快照隔离。

## 实施步骤

1. 先补执行器输入输出、stub 和引擎注册失败测试。
2. 实现协议与 `agent-skill-stub-v1`，让 Runner 仍只负责缓存和持久化。
3. 补完整链路测试，验证 stub 新建、复用、non-target 与失败语义。
4. 更新设计说明与 Agent Note，运行 API、类型、契约、文档和 Flow 门禁。

## 依赖与交付边界

- 依赖：m12-17、m12-18
- 交付边界：只交付可替换接缝、版本化契约和确定性桩；不访问内网模型，不改变真实对象选择与 PotentialMatcher 语义。

## 独立验证

```sh
pnpm test:api -- tests/test_attribution.py
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
```

- `agent-skill-stub-v1` 对同一输入生成稳定结果，第二次运行命中独立于 `rule-v1` 的缓存。
- 未注册 resolver/executor 或非法输出会产生可诊断错误，不写入半成品 Probe Report。
- 默认配置继续选择 `rule-v1`，既有测试与 API 契约不回归。

## 验收标准

- 内网 adapter 只需实现 executor 协议并注册 key，不修改 Runner、repository 或候选状态机。
- 执行器输入明确区分选定归因对象与 Badcase 上报来源，并保留对象/上报触发坐标。
- stub 输出可通过结构校验并落入现有 Probe Report 字段；缺少完整 Trace 时带固定 warning。
- 引擎超时或异常沿用 `blocked(attribution)` 恢复路径，已完成候选不重复计算。

## 门禁与 CI

- API 单测、mypy、契约、文档、Flow 与现有双库门禁。

## 非目标

- 不接入内网 LLM、Agent 服务或生产凭据。
- 不实现对象级自定义 Skill 的 CRUD、绑定页面或持久化版本仓库。
- 不保存完整 Session Trace，不扩展 Probe Report 数据库结构或公开分类枚举。
- 不把 stub 描述为真实归因质量实现，也不把它设为默认引擎。
