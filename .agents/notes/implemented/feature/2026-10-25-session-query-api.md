# Agent Note: 会话查询 API

Status: implemented

[English](2026-10-25-session-query-api.en.md) | 中文

## Problem

归一化后的会话、Agent 事件和外部问题数据需要以稳定读模型供浏览器分诊与执行流图消费；如果前端自行聚合，列表统计、排序、锚点和数据库真值会漂移。

## Decision

会话列表、概览和树查询由只读 `sessions` 模块统一提供。列表直接读取 `session_families` 的整树聚合列，并在当前页按 `bad_cases` 一次分组计数；概览复用同一契约。树返回扁平 `agents[]`，后端计算 label、事件偏移和问题锚点。搜索与排序在 SQL 中执行，并使用 session id 稳定破平。

## Alternatives considered

- 前端遍历树自行求和：会重复实现口径，且列表页需要加载所有树。
- 将问题数物化进会话表：外部问题可随时变化，本服务没有失效通知路径。
- 恢复时间线读接口：时间线页面已裁撤，用户输入锚点已足够。

## Consequences

列表和概览共享一个 Pydantic 契约，树字段直接对应原型执行流图。问题计数始终反映查询时的只读外部表。时间线消息和内容块仍不落库、不暴露；缺失会话统一返回 `SESSION_NOT_FOUND`，SQLite 与 MySQL 查询由双库测试约束。
