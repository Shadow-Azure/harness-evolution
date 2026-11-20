# Agent Note: 自进化历史卡片补齐运行配置标签

Status: implemented

[English](2026-11-20-run-list-prototype-alignment.en.md) | 中文

## Problem

生产「自进化 → 历史记录」卡片只显示对象版本、时间窗和模型，缺少 V2 原型与设计文档 05 §3.5 都列出的工作空间、潜在策略、缓存三枚标签；右上还把创建人拼在时间前，原型只显示时间。运行配置在启动时已经写入 `evolution_runs.potential_policy` / `cache_enabled` / `workspace_id`，列表服务却没有把它们投影进 `EvolutionRunCard`，所以这是契约投影缺口，不是样式漏写。问题与证据见 GitHub #414。

## Decision

- `EvolutionRunCard` 增加 `policy: { preset: default | custom }` 与 `cacheEnabled`。`policy` 只暴露展示所需的 preset，不把完整策略 JSON（三条开关）带进列表；缺失或未知 preset 的旧 run 归一为 `default`，`cache_enabled` 缺失为 `false`。
- 工作空间名不进入卡片 DTO：列表始终按当前工作空间过滤，前端从 auth store 的当前路由空间取名字下传；卡片 DTO 不重复空间信息。
- 卡片右上只显示 `createdAt`，创建人不再渲染；`createdBy` 保留在 DTO（详情继承同一字段），供后续详情或审计使用。设计文档 05 / 08 与原型统一为“列表只显示时间”。
- 服务层 `_card()` 一次投影 `policy` 与 `cacheEnabled`，`EvolutionRunDetail` 通过继承自动获得快照，详情页与列表不出现两套策略口径。

## Alternatives considered

- **把 `workspace: { id, name }` 加进卡片 DTO**：能让卡片独立展示，但列表已经按空间过滤，DTO 会为每张卡重复同一空间，还要在 repository 查询里补 workspace name 的连接。拒绝。
- **保留创建人前缀，反向给原型补创建人**：设计文档 05 §3.5 曾要求显示创建人，但 #405 已把运行详情页头收敛为“标题 + 状态 + 空间 badge”，列表再保留创建人会出现两套口径；#414 也明确建议移除。选择移除列表显示、保留 DTO 字段。拒绝反向补原型。
- **前端直接从 `attribution` / `range` step 读取策略与缓存开关**：详情页确有这两个 step，但列表卡没有逐卡请求 step 的加载路径，会放大请求数与状态复杂度。运行配置已经持久化在 run 行上，直接在列表投影更小。拒绝。
- **把完整 `potential_policy` JSON 暴露给前端**：列表只需要 default / custom 文案，完整开关属于详情与算法内部契约，暴露会扩大前端可依赖面。拒绝。
- **移除卡片上的模型 chip 以完全贴合原型**：#414 的差异表没有把模型列为偏差，删除会丢失既有信息，超出本缺陷边界。保留。

## Consequences

- `GET …/evolution/runs` 的 `run` / `history` 卡片多两个字段，OpenAPI 与生成类型随 `pnpm contract:generate` 更新；旧客户端不受影响；新前端对旧服务端缺 `policy` 时用 `?.` 回落为默认策略、缺 `cacheEnabled` 时按 false 渲染，避免混版本标签页在发布回滚时抛错。
- 旧 run（`potential_policy` 为空、`cache_enabled` 默认 false）显示“默认潜在策略 / 不复用缓存”，与启动时默认策略一致；不会被改写成自定义策略。
- 创建人从列表消失但仍在 DTO；若后续产品要求列表展示创建人，应同时修改原型与设计文档，而不是只改前端。
- 原型补一个 failed 样例与失败徽标，后续对照不会把“失败无终评行”当成卡片样式缺失；列表页宽度仍受 `.evolution-page-frame` 的 1080px 限宽，属于独立页面框架问题，本 Note 不处理。
