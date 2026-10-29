# Agent Note: bad_cases 增加短标题列

Status: implemented

[English](2026-10-29-bad-case-title.en.md) | 中文

## Problem

原型错误详情页按"短标题 + 描述正文"两级渲染问题，问题列表卡与执行流图问题卡也以短标题为主文本；而 `bad_cases` 只有 `reason` 一个长文本列，`BadCase` 契约与 05 §9 原型字段映射表同样只有 `reason`，实现只能把 `reason` 整段当标题渲染，未分析的问题列表卡没有任何题名可显示，真实数据接入后错误详情页的信息密度明显低于原型。列名也不统一：同表其余列都带 `bad_case_` 前缀（`bad_case_id` / `bad_case_session_id` / `bad_case_agent_id` / `bad_case_type`），`probe_reports` 的正文列同样带前缀（`probe_description` / `probe_analysis`），`reason` 是唯一的例外。

## Decision

`bad_cases` 增加 `title VARCHAR(255) NOT NULL` 短标题列，作为外部上报的必填字段，渲染为错误详情页标题行、问题列表卡与执行流图问题卡的主文本。`bad_cases.reason` 改名为 `bad_cases.bad_case_description`（`TEXT NOT NULL`），语义仍是描述正文，渲染在详情页正文块；改名的理由是表内列名统一带 `bad_case_` 前缀，与 `probe_reports.probe_description` / `probe_analysis` 的命名一致。改名只发生在存储层：公开 DTO 字段仍是 `BadCase` / `SessionBadCase` 的 `title` 与 `reason`，`reason` 由 `bad_case_description` 列映射而来，契约与前端不随列名变化。存量行一次性回填：`bad_case_description` 取原 `reason` 全文、`title` 取原 `reason` 前 255 字符；上游重灌（06 §1.2）仍是权威路径，回填只覆盖未重灌的存量库。读时仍缺 `title` 的行降级为派生标题（取描述首句）并标记 `degraded`。

## Alternatives considered

约定 `meta_data.title` 被否：`meta_data` 的定义就是"上报打点数据，结构不统一"，把核心展示字段藏进自由 JSON 会让渲染依赖不可靠的约定；只加 `title` 保留 `reason` 列名被否：同一张表会并存 `bad_case_*` 与裸 `reason`，读者得从两处推断哪列是描述正文，而改名的代价只是一次迁移加一层 DTO 映射，故按前缀统一；前端截取 `reason` 首句被否：截断位置对中英混排不可靠，长首句仍会挤爆图上问题卡的 150–400px 宽度钳制，信息保真度也差。

## Consequences

上游问题上报系统必须同步提供 `title`，这是一次对外契约变更（06 §1 已约定问题侧表结构变更需与上游一起评审）；列改名产生一次 alembic 迁移（SQLite 走 batch 模式），DTO 与前端字段名不变，映射只落在 repository 一处；存量 `bad_cases` 行按 06 §1.2 由上游重灌，或一次性回填（`title` 取原 `reason` 前 255 字符），读时缺 `title` 的行走 `degraded` 派生标题；图上问题卡的宽度测算文本换成 `title` 后卡片更窄更稳定；`reason` 不再受标题布局约束，可承载完整描述。
