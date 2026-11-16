# 真实元数据兼容与完成状态解析

[English](m9-02-trace-metadata-completion-parser.en.md) | 中文

```yaml flow
kind: issue
id: m9-02
milestone: m9
depends:
  - m9-01
priority: P0
status: in-progress
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/db/**
  - apps/api/app/fixture_corpus.py
  - apps/api/tests/**
  - fixtures/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 237
  url: https://github.com/Shadow-Azure/harness-evolution/issues/237
```

## 背景

真实 meta.json 已出现 isBuiltIn、pickedEffortModel、finished 等新字段，subagent JSONL 还包含 prompt_snapshot、api-request-shape、agent_listing_delta、attributionSkill 和 toolUseResult；当前闭集校验会拒绝整份 Session，也会把 Skill body 与 agent 定义证据漏掉。根会话也可能停在 tool_use。

## 目标

- 未知元数据不阻断整份导入；已知字段严格校验。
- 解析未配对 tool_use、无 end_turn 子 Agent 和最终任务快照。
- 从 prompt_snapshot.systemPrompt[0] / api-request-shape 提取 agent 定义 body 的 stable hash。
- 从 isMeta + sourceToolUseID 的 Skill 注入提取 path 与 body hash。
- 从 toolUseResult（Read/Bash/Edit）提取文件 path、range、complete 与 content hash。
- 分离 requested_model、reported_model 与 model evidence。

## 设计依据

- [15 §9.2、§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份)：revision 与完成状态。
- [07 §2.3–§2.6](../../../plans/fullstack-design/07-backend-implementation.md#2-原始轨迹接入与归一化serviceacquisition)：parser 工厂与归一化。
- [07 §2.6 多 runtime parser 工厂](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂)：子类必须实现的 record/meta/evidence hook。

## 实现内容

- 已知元数据严格校验，未知标量脱敏进入 meta 并产生 warning。
- 识别 tool_use 与 tool_result 配对缺口。
- 读取 task_reminder 最后快照和 stop_reason。
- Claude 子类实现 agent 定义、Skill 注入和文件读取的 evidence hook；只保存 hash/路径/范围，不保存正文。
- 对 common suffix（subagent 权限提示、Notes、token budget）做归一化，排除在 agent 定义 hash 之外。

## 实施步骤

1. 先加入脱敏真实形状 fixture，覆盖 prompt_snapshot、skill meta、toolUseResult。
2. 实现扩展元数据、完成度和 evidence hook。
3. 补重放幂等、warning code 和定义/文件 hash 测试。

## 依赖与交付边界

- 依赖：m9-01
- 交付边界：不建立父子关系；不实现第二个 runtime。为把解析结果写入既有证据列，scope 增加 `apps/api/app/db/**`、`apps/api/tests/**` 与 `plans/**`（检视文档）；对象 revision、触发坐标与关系分级仍归 M9-03/M9-04。

## 独立验证

```sh
pnpm test:api -- tests/acquisition; pnpm data:normalize:sessions
```

- 新字段 fixture 可导入。
- root 最后 tool_use 产生 TOOL_USE_OPEN。
- 无 end_turn 子 Agent 产生 MISSING_FINAL_REPORT。
- 同一 agent 类型不同任务得到相同定义 hash；不同 runtime 不串 hash。

## 验收标准

- 真实元数据漂移不会整树丢弃。
- 完成度、工具错误和定义证据分开。
- Skill body/agent prompt 不落原文，只落 hash 与来源。

## 门禁与 CI

- API、数据、fixture 与 flow 门禁。

## 非目标

- 不保存原始消息或工具输出。
- 不对未知字段做业务推断。
- 不把 provider 私有字段写入 ParsedTranscript 公共字段。
