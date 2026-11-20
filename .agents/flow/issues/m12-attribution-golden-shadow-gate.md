# 归因 Golden Cases、影子运行与引擎晋级门禁

[English](m12-attribution-golden-shadow-gate.en.md) | 中文

```yaml flow
kind: issue
id: m12-20
milestone: m12
depends:
  - m12-19
priority: P0
status: done
scope:
  - apps/api/**
  - fixtures/**
  - scripts/**
  - package.json
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 316
  url: https://github.com/Shadow-Azure/harness-evolution/issues/316
```

## 背景

Agent-Skill 归因的输出会进入聚类、Proposal 和真实 Patch 链路，仅验证 JSON 合法无法证明对象结论和证据可靠。内网执行器接入前后都需要一套脱敏、可复现的质量基线，并且新引擎或 Skill revision 不能未经对照直接替换生产默认。

## 目标

- 建立覆盖核心归因语义和失败模式的 Golden Cases。
- 支持 rule、stub、Default Skill 与对象定制 Skill 的离线对比和影子运行。
- 定义引擎/Skill revision 的晋级、阻断和回滚门槛。

## 设计依据

- [09 R2、R11](../../../plans/fullstack-design/README.md)：多归因缓存与真实执行风险。
- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md)：归因结论、confidence 与 Runner。
- [01 §4.3](../../../plans/fullstack-design/01-architecture.md)：自进化闭环与证据边界。

## 实现内容

在根 package.json 注册离线评测入口 `pnpm attribution:evaluate`。

- 建立脱敏 fixture，覆盖 self/discovery、对象出现但非根因、多 occurrence、多对象、缺 Trace、关系降级、非 Skill 问题和提示注入。
- 定义结论准确率、证据有效率、引入/检测点命中率、schema 合规率、延迟、Token 与失败率指标。
- 影子执行只写隔离的 execution/result，不改变正式 Probe Report、候选、聚类或缓存命中。
- 提供人工对照与接受/驳回记录；达到阈值后才能把引擎或 Skill revision 标记为 production-eligible。
- 保留一键回滚到上一有效 Skill revision 或 `rule-v1` 的路径。

## 实施步骤

1. 定义 Golden Case schema、脱敏规则、指标和晋级阈值。
2. 建立 fixture 与离线 evaluator，先验证 rule/stub 的确定性。
3. 实现影子运行和差异报告，不写正式归因链。
4. 接入晋级状态、人工判断和回滚证据。

## 依赖与交付边界

- 依赖：m12-19。
- 交付边界：评价归因引擎和 Skill 质量并控制晋级；不训练模型、不自动修改 Skill。

## 独立验证

```sh
pnpm test:api -- tests/attribution_eval
pnpm fixtures:check
pnpm test:gates
```

- 固定引擎和 Skill revision 在同一 Golden Set 上得到可复现指标。
- 影子运行不会改变正式报告、候选、聚类或 Run 状态。

## 验收标准

- 未通过阈值的引擎/Skill revision 不能成为生产默认。
- 每次晋级和回滚可追溯到评测集、指标、执行清单和人工决策。
- Prompt injection、虚假 evidence 和缺失上下文均有负向用例。

## 门禁与 CI

- API、fixture、评测确定性、安全、文档与 Flow 门禁。

## 非目标

- 不训练或微调模型，不自动发布 Skill，不生成真实 Patch。
- 不用线上用户原始 Trace 作为仓库 fixture。
