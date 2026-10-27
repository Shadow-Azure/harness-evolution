# 修正启动命中口径与向导校验

[English](m5-12-launch-hit-scope.en.md) | 中文

```yaml flow
kind: issue
id: m5-12
milestone: m5
depends:
  - m5-05
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 132
  url: https://github.com/Shadow-Azure/harness-evolution/issues/132
```

## 背景

m5-05 的启动向导把命中查询建在 `bad_cases.object_*`（上报对象）上，而设计把 `probe_reports.probe_object @ object_version` 定为自进化 target 的唯一来源；两者错位时会出现“选 deep-research 却跑 Explore 的根因聚类”。同批检视还发现：`probes/query` 未共享启动的 `defaultRef` 归一化（省略版本时 422，启动却 202）；202 之后的 `evolution_prepare` 因未注册 handler 每次必然留下已失败作业；Step2 图例固定渲染四项（与原型的数据驱动不一致）；自研弹层缺对话框语义；390px 下内容横向溢出。

## 目标

- 命中、统计与 items 全部由 `probe_reports` 按 `probe_object @ object_version` 反查 bad case 与 session；未分析与非问题不参与自进化命中。
- `probes/query`、`cluster-previews`、`runs` 共用同一条件归一化：`defaultRef` 缺省、窗口倒挂、target 未配置与 0 命中的错误语义一致。
- 202 之后不再产生“no handler registered”的必然失败作业；prepare 占位明确留待 m5-06。
- Step2 图例与分布条按非零项渲染；弹层具备 `role="dialog"`/`aria-modal`/Esc 关闭；390px 无横向溢出。
- 05/08/02 的设计口径与本实现一致。

## 设计依据

- [05 §3.4/§3.5/§4.9/§4.10/§4.12](../../../plans/fullstack-design/05-api-design.md)
- [07 §5.3](../../../plans/fullstack-design/07-backend-implementation.md)
- [08 §9](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 F11](../../../plans/fullstack-design/02-features.md)

## 实现内容

- `probe_query` 仓储改为 probe 起点的 join：`probe_reports → bad_case_analysis → bad_cases → session_families`，窗口按 probe 所属 session 启动时间，`models` 按该 session 树内任一 agent 的模型。
- 汇总口径：`sessions`=命中去重 session，`badCases`=probe 反查的去重问题数，`analyzed`=命中的已分析问题数，`probes`=`usedProbes`=命中 probe 数，`byAttributeType` 取 `probe_reports.attribute_type`；`unanalyzed` 与 `nonIssue` 恒 0 且保留字段。
- `ProbeQueryService` 接收 target 配置存储，preview 与 launch 都用配置的 `default_ref` 兜底；target 未配置给 409 `TARGET_NOT_CONFIGURED`。
- 注册 `evolution_prepare` 占位 handler：标记准备中并正常结束作业，不改变 run 的 `preparing` 意图。
- 前端：统计格保留「未分析」显示 0，移除“等待外部归因”提示；分布条与图例只渲染非零项；弹层补 `role="dialog"`/`aria-modal`/`aria-labelledby`/Esc 关闭/初始焦点；probe 表容器可横向滚动。
- 文档：05 §3.5/§4.9、08 §9.3、02 F11 改为 probe 口径并写明未分析/非问题不参与；07 §5.3 补预览同源校验说明。

## 实施步骤

1. 写 probe 口径与 preview 缺省版本、prepare 占位、图例非零、弹层语义的失败测试
2. 改仓储/服务/API 与占位 handler，同步 web 组件
3. 更新设计文档与 Agent Note，跑独立验证

## 依赖与交付边界

- 依赖：m5-05
- 非目标：六步 prepare 的真实编排（m5-06）、`ENGINE_INVALID` 引擎注册表（m5-06）、幂等与 run/job 原子性（设计未要求）、run 详情数据源（m5-07）

## 独立验证

```sh
pnpm test:api -- tests/m5-05-launch-wizard
pnpm test:db
pnpm test:web
pnpm test:e2e --pattern "m5 "
pnpm contract:check
pnpm verify:docs
```

- API 子集与数据库测试全绿；web 单测全绿；E2E 启动向导与运行列表通过；契约无漂移；文档门禁全绿。

## 验收标准

- 构造“上报对象 A、根因对象 B”的数据时，查询 B 命中、查询 A 不命中（或仅计 0 条未分析）。
- 省略 `targetVersion` 时 preview 与 launch 都按 `defaultRef` 解析成功。
- 启动后作业不再以 “no handler registered” 失败，run 保持 `preparing`。
- Step2 图例只出现实际命中的属性类型；390px 无横向滚动；Esc 可关闭向导。

## 门禁与 CI

- `contract:check`、`verify:web-style`、`verify:docs`、`verify:flow`、E2E 与覆盖率门禁

## 非目标

- 不做未分析报告的自动补归因（外部系统职责，V1 不提供触发分析端点）
- 不改 run 状态机与六步接口形态
