# 归因置信度改为证据完整度规则分

[English](bugfix-attribution-rule-confidence.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-18
milestone: bugfix
depends: []
priority: P2
status: backlog
scope:
  - apps/api/app/db/crud/bad_cases.py
  - apps/api/app/service/**
  - apps/api/tests/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 491
  url: https://github.com/Shadow-Azure/harness-evolution/issues/491
```

## 背景

现状 case 级归因置信度是写入时固定默认 0.8（`crud/bad_cases.py`）。设计（#487）决定模型置信度不放归因步：证据是否齐全是规则可判的，case 级分数只作步骤4展示与可选低置信门槛；模型评分移到聚类后的簇级（bugfix-19）。

## 目标

- `bad_case_analysis.confidence` 改为**证据完整度规则分**：三信号计票——时间序可比（order=comparable）、错误签名匹配（与对象已知失败签名重合）、版本直证（body 哈希 / revision 精确命中）；按票数映射区间（三票 ≥0.9；两票 0.7–0.9；一票 0.5 上下；信号矛盾 <0.5）。
- 分数确定性、可单测：同证据同分，零模型调用、零额外成本。
- 归因引擎名维持 `rule-v1`，缓存键命名空间不变。

## 设计依据

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md)：「归因置信度不上模型」小节与三信号定义。
- Agent Note（adr）：逐 case 模型置信度被否的取舍记录。

## 实现内容

- 在归因写入路径提取三信号（数据已在 `potential.py` 锚点比较与版本身份中存在，按需透出）。
- 计票与区间映射函数 + 单测（含矛盾信号用例）。
- 可选「低置信不入簇」门槛设计为常量开关，默认关闭，不在本 issue 启用。

## 实施步骤

1. 信号提取与计票函数及单测。
2. 写入路径替换默认 0.8。
3. 既有归因测试回归（步骤4 行为变化为分数来源，字段与类型不变）。
4. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：无（与 provider 链完全独立，可并行）。
- 交付边界：只改归因写入路径的置信度产出与测试；不动表结构、缓存键与 API 字段。

## 独立验证

```sh
pnpm test:api -- tests/test_attribution_confidence.py
```

- 三信号组合矩阵（0–3 票 + 矛盾）全部命中间断言。

## 验收标准

- 固定 0.8 默认值被计票映射取代；矩阵测试钉住区间边界。
- 步骤4 API 行的 confidence 语义不变（0–1 float），前端零改动。
- 引擎名与缓存键不变，历史缓存不受影响。
- CI 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不做逐条模型置信度（预算开关位保留，不在本 issue 实现）。
- 不动簇级置信度（bugfix-19）。
- 不启用低置信不入簇门槛。
