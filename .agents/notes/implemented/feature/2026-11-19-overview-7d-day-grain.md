# Agent Note: 总览近 7 天默认日粒度

Status: implemented

[English](2026-11-19-overview-7d-day-grain.en.md) | 中文

## Problem

工作空间总览的「bad case 趋势」默认 90 天/周粒度。用户切到近 7 天后，`range` 变成 7，但 `grain` 仍停在 week，于是 7 天窗口只产生两个周桶（如 11-09、11-16），当天（11-19）的数据被并入 11-16 桶，图上没有 11-19 的独立时间桶，容易被误判为当天数据未上报或统计失败。

对照 `plans/ui-prototype-v2/harness-evolution.html`，原型的「时间」和「粒度」也是两个独立控件，近 7 天不会自动切日；产品确认预期是近 7 天看逐日数据，因此先改原型，再让生产实现与原型一致。

## Decision

- 快捷时间范围联动默认粒度：近 7 天 → `day`，近 30/90 天 → `week`；自定义区间保持当前粒度。时间范围变化时才联动，用户之后手动点「日/周/月」不被后续数据刷新覆盖。
- URL 解析：`?range=7` 且未显式提供合法 `grain` 时规范化为 `day`；显式 `?range=7&grain=week` 仍尊重用户选择。`overviewQuery` 因此把 `grain=day` 写进规范 URL。
- 不改 API、数据库或统计口径：后端已支持 day/week/month，>92 天的 day 请求仍按既有规则降级为 week 并回传实际粒度。
- 原型同步：`plans/ui-prototype-v2/harness-evolution.html` 的点击和 `?range=7` 启动路径也默认 day；`design-v2.md` 与 `plans/fullstack-design/08` 补充约定。

## Alternatives considered

- **保持 7 天周粒度，只加 tooltip 显示周范围**：拒绝。它只解释数字，不恢复「近 7 天看逐日」的主路径；7 天只有两个桶，运营仍无法按天定位。
- **在指标条新增“今日新增”**：拒绝。能补一个数字，但不能替代趋势图的逐日分布；范围更窄，且会引入新的指标口径。
- **所有范围都默认日粒度**：拒绝。90 天日粒度会被服务端降级为周，前端还要处理降级提示；长窗口的默认周粒度是既有设计。

## Consequences

- 近 7 天 URL 从 `?range=7` 规范化为 `?range=7&grain=day`，图表从 2 个周桶变为 7 个日桶；显式带 `grain=week` 的旧链接保持不变。
- 近 30/90 天快捷按钮会把粒度重置为周；如果用户先手动选月再点 30/90，会被覆盖一次，这是“时间范围变化时联动”的预期行为。
- 测试覆盖 URL 解析、页面 range/grain 联动和 E2E 可见的 7 个日桶；原型与实现的默认行为保持一致。
