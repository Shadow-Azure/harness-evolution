# Agent Note: 自进化真实模型化的四项结构性取舍

Status: proposed

[English](2026-11-22-evolution-real-ai-design.en.md) | 中文

## Problem

自进化的聚类、置信度、严重度与 patch 生成是占位实现（词面聚类、固定置信度、常量公式、placeholder patch），要接入真实模型能力时必须在四个结构问题上做决定：模型出站调用收口在哪；聚类的模型介入放在哪一层、如何随归因报告量扩展；结构化 JSON 结论如何可靠回收；编辑 patch 用什么表示。2026-11-22 的定稿设计（[07 §5.5.1–§5.5.4](../../../../plans/fullstack-design/07-backend-implementation.md)）锁定了四个答案，本文记录为什么以及放弃了什么。

## Decision

- **模型出站收口到 `third_party_api/ai_agent` 的父类接口**：`analyze` / `edit_workspace` 两个能力面 + 工厂按 `AI_AGENT_PROVIDER` 选择子类（当前仅 claude-code 与 fake）；接口按能力而非厂商划分，换后端只新增子类。它不是早期「统一 Provider 层」的复活——只服务模型出站一个接缝。
- **聚类分三层，LLM 输入输出与归因报告总量 N 解耦**：分组层 O(N) 无 LLM（lexical 首实现、向量化升级位）；审查层 O(K×s) 只做合并/命名（草稿键引用 + 草稿划分完整性硬闸）；评分层 O(K×s) 簇置信度直评 + 严重度维度分。case 级置信度保持规则信号不上模型——逐条盲评丢掉跨 case 佐证且成本 O(N)。
- **结构化回收走自建提交通道**：agent 写 `result.json5`（JSON5 宽松字面量），`submission.py` 确定性解析 + 校验 + 失败回喂重试；不依赖任何 CLI 内部机制（Claude Code 的 `--json-schema` 降为可选快路径，默认关）。「用 JS 生成 JSON」的价值被提炼为字面量容错 + 确定性序列化，且不执行模型代码。
- **patch 用 SkillOpt 式 Edit 指令**：agent 只读探索后提交 EditPlan（op/file/target/content/rationale），锚文本必须存在且唯一（多义回喂），`edits.py` 确定性应用，`git diff` 为唯一真值；`edit_budget` 双重执行（prompt 约束 + 硬截断）；reject 后 `--resume` 同会话注入反馈与 rejected-edit buffer。agent 工具面收敛为只读 + 写一个 json5，无需文件编辑权限。

## Alternatives considered

- **逐 case 模型置信度（聚类前）**：与归因证据缓存天然契合，但单条盲评丢掉佐证效应、成本 O(N)；被「规则信号 + 簇级直评」取代，逐条模型分留作预算开关。
- **依赖 `--json-schema` 原生通道为主路径**：Claude Code 上免维护且可靠，但属于 CLI 内部机制，换 opencode 等后端时层 1 强度骤降且要重写回喂闭环；降为 env 开关的快路径。
- **agent 直改文件（agentic editing）收 diff**：复杂重构能力更强，但意图不可计数、需要 acceptEdits 权限面；目标对象是技能/配置文档，指令式主场，直改留作未来开关位。
- **让 agent 调 JS 脚本生成 JSON**：数据仍需以参数或文件形态由模型手写，或需执行模型代码；被「写宽松字面量 + 确定性解析」取代，脚本仅保留为内容计算工具的形态。

## Consequences

- 设计已落 `plans/fullstack-design`（07 §5.5.1–§5.5.4、04 目录树与接缝表），后续实现 issue 以其为设计依据；本文随实际落地同步状态与事实。
- 实现按阶段推进（骨架 → 聚类三层 → 可选向量化 → 指令式 patch），每步 env 可回退（fake / placeholder），最坏情况等于今天的行为。
- 新增纯 Python 依赖 `json5` 与 `json-repair`；`edit_workspace` 语义从「直接编辑」变为「提交计划 + 确定性应用」，round 内无试错循环，由 round 级迭代闭环补偿。
- 声明（EditPlan）与实际（git diff）的对照成为每 round 的审计信号；两者不一致即质量报警。
- 2026-11-22 骨架已落地（bugfix-15）：`ai_agent` 四模块、Settings 仅两个配置项、确定性的 `fake` 与 `claude-code` 占位；真实 CLI 子类与业务接入仍在后续 issue。
- 2026-11-22 提交通道已落地（bugfix-16）：`third_party_api/ai_agent/submission.py` 以一次性任务目录收货，唯一工具白名单为 `Write(./result.json5)`；解析顺序为严格 JSON → JSON5 → json-repair（仅兜底），结果交 Pydantic `model_validate`，失败文案经 `feedback_prompt` 回喂 `--resume` 重试一轮。
- 2026-11-22 提交通道是当前默认且唯一路径：`HE_AI_AGENT_NATIVE_SCHEMA` / `--json-schema` 仅是设计文档中的可选快路径，刻意不实现，待真实需求出现再评估；`SubmissionOutcome.parsed_by` 与有界 `repair_log` 是层 5 的出处字段，记录由哪层解析、修复器改动过什么；结果文件名与工具白名单暂不参数化，`edits.json5` 的复用推迟到 bugfix-21（届时需要文件名/路径参数与后端特定工具覆盖）。
