# Agent Note: bad_cases 增加短标题列

Status: proposed

[English](2026-10-29-bad-case-title.en.md) | 中文

## Problem

原型错误详情页按"短标题 + 描述正文"两级渲染问题，问题列表卡与执行流图问题卡也以短标题为主文本；而 `bad_cases`、`BadCase` 契约与 05 §9 原型字段映射表只承载 `reason` 一个长文本字段，实现只能把 `reason` 整段当标题渲染，未分析的问题列表卡没有任何题名可显示；真实数据接入后错误详情页的信息密度明显低于原型。

## Decision

`bad_cases` 增加 `title VARCHAR(255) NOT NULL` 短标题列，作为外部上报的必填字段；`reason` 语义收敛为描述正文；契约 `BadCase` / `SessionBadCase` 透出 `title`；前端标题行渲染 `title`、正文块渲染 `reason`，问题列表卡与图上问题卡主文本改用 `title`。短标题是核心展示字段，进正列、进正契约，由上游系统写入时提供。

## Alternatives considered

约定 `meta_data.title` 被否：`meta_data` 的定义就是"上报打点数据，结构不统一"，把核心展示字段藏进自由 JSON 会让渲染依赖不可靠的约定；前端截取 `reason` 首句被否：截断位置对中英混排不可靠，长首句仍会挤爆图上问题卡的 150–400px 宽度钳制，信息保真度也差。

## Consequences

上游问题上报系统必须同步提供 `title`，这是一次对外契约变更（06 §1 已约定问题侧表结构变更需与上游一起评审）；存量 `bad_cases` 行按 06 §1.2 由上游重灌，或按 `reason` 首句一次性回填；图上问题卡的宽度测算文本换成 `title` 后卡片更窄更稳定；`reason` 不再受标题布局约束，可承载完整描述。
