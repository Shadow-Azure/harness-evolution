# Agent Note: flow:sync 的 GitHub 状态 JSON 边界

Status: implemented

[English](2026-11-17-flow-sync-gh-state-json.en.md) | 中文

## Problem

`flow:sync` 的核心编排接收已解析状态，但生产 CLI adapter 返回 `gh` 的 JSON 字符串并直接取 `.state`，因此所有状态读取都变成 `undefined`。同步会对状态已经一致的历史对象发无操作 PATCH，使权限不足以编辑 Milestone、但足以维护 Issue 的账号无法完成 Issue 正文同步。

## Decision

CLI 适配器解码 GitHub JSON。里程碑读取状态，issue 读取状态与可为空的里程碑编号。`runSync` 在状态或归属有差异时用一次 PATCH 同时写入两个字段，正文独立同步。编号过滤在远端写入前校验，限定 issue 的同步跳过所有里程碑写入。

## Alternatives considered

- 捕获 Milestone PATCH 的 404 并继续：会把真实权限或远端对象错误静默吞掉，拒绝。
- 要求所有开发者获得 Milestone 写权限：扩大权限仍不能修正错误的状态读取，拒绝。
- 在 `runSync` 内兼容字符串和对象：会把 CLI 传输格式泄漏进纯编排层，拒绝。

## Consequences

已对齐的记录可跳过元数据写入。适配器报告格式错误或缺失字段。真实写操作仍由 GitHub 校验权限。
