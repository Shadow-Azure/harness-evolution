# Agent Note: 自进化运行列表的后端事实边界

Status: implemented

[English](2026-10-27-evolution-run-list.en.md) | 中文

## Problem

自进化首页需要同时呈现进行中与历史运行，并显示阶段、进度、轮次、接纳数、终评和错误摘要。如果浏览器重新分组、排序或根据游标计算百分比，数据库快照、API 与界面会对同一 run 得出不同结论；创建人又未出现在 API 设计的 RunCard 示例中，与 Issue 的展示要求形成冲突。

## Decision

`GET /api/evolution/runs` 在一个快照中批量读取 run、创建人、真实 cluster 数、已接纳轮次数和 final，并按 `created_at DESC, id DESC` 排序后返回 `running` 与 `history`。`preparing`、`running`、`blocked` 属于 running，三个终态属于 history。服务端生成 `progress.total`、`percent`、`stageLabel`、`doneRounds`、`accepted` 与规范化 stats；前端只映射显示，不重新计算。RunCard 在 API 设计字段之外增加可空 `createdBy`，前端将它放在原型右上时间槽内，避免新增视觉行。completed 但缺 final 的 run 显示“终评未知”，不能推断为无收益；错误阶段码留在内部，界面只在状态 badge 的 tooltip 与可访问名称中展示脱敏消息。

## Alternatives considered

让前端按状态数组重排会把原型顺序变成客户端实现细节；逐 run 查询 cluster、轮次和 final 会产生 N+1，并可能跨请求读到不一致快照；用 Python `round` 计算百分比会在 .5 上采用银行家舍入，不符合原型的四舍五入；忽略 Issue 的创建人要求会留下验收缺口。以上方案均否决。

## Consequences

运行列表依赖一个 repository 聚合读取和稳定 API 投影；列表查询必须同时覆盖 SQLite 与 MySQL。创建人显示名在用户删除后为空，但 run 快照仍可展示。后续 SSE 只失效运行列表 query，不能把推送 payload 当作持久事实源。
