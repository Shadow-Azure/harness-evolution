# Agent Note: flow:sync 的 GitHub 状态 JSON 边界

Status: implemented

[English](2026-11-17-flow-sync-gh-state-json.en.md) | 中文

## Problem

`flow:sync` 的核心编排接收已解析状态，但生产 CLI adapter 返回 `gh` 的 JSON 字符串并直接取 `.state`，因此所有状态读取都变成 `undefined`。同步会对状态已经一致的历史对象发无操作 PATCH，使权限不足以编辑 Milestone、但足以维护 Issue 的账号无法完成 Issue 正文同步。

## Decision

GitHub CLI 的 JSON 解码属于 adapter 边界：增加一个严格纯函数解析字符串并验证 `state` 为非空字符串，milestone 和 issue 的 read adapter 都先解析再返回状态。`runSync` 保持只消费状态字符串，因此测试注入面与业务状态机不变；真实状态不一致时仍执行 PATCH 并传播权限错误。

## Alternatives considered

- 捕获 Milestone PATCH 的 404 并继续：会把真实权限或远端对象错误静默吞掉，拒绝。
- 要求所有开发者获得 Milestone 写权限：扩大权限仍不能修正错误的状态读取，拒绝。
- 在 `runSync` 内兼容字符串和对象：会把 CLI 传输格式泄漏进纯编排层，拒绝。

## Consequences

状态一致的远端对象不再收到 PATCH，低权限账号可继续完成其有权执行的 Issue 同步；malformed JSON 或缺失状态会在 adapter 处给出明确错误。状态确实需要改变时仍要求对应 GitHub 权限，不提供绕过路径。
