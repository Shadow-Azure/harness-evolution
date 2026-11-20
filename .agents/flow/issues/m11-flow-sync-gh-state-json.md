# 修复 flow:sync 的 GitHub 状态 JSON 解析

[English](m11-flow-sync-gh-state-json.en.md) | 中文

```yaml flow
kind: issue
id: m11-08
milestone: m11
depends:
  - m7-01
priority: P1
status: done
scope:
  - scripts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 322
  url: https://github.com/Shadow-Azure/harness-evolution/issues/322
```

## 背景

`flow:sync` 的命令适配器把 `gh ... --json state` 与 milestone API 返回的 JSON 字符串直接读取 `.state`，结果恒为 `undefined`。即使远端状态已经一致，同步仍会对所有历史 Milestone 和 Issue 发 PATCH；权限仅够维护 Issue 的账号会在第一个 Milestone PATCH 上收到 404，使新 Issue 已创建但正文和既有规划更新无法继续。

## 目标

读取状态和 issue 所属里程碑，按差异同步元数据与正文，支持按编号限定写入范围。

## 设计依据

- [10 §2 路线图与任务入口](../../../plans/fullstack-design/10-roadmap-draft.md)：流程规划与任务管理边界。

## 实现内容

里程碑适配器解析 state。issue 适配器读取 state 与可为空的 milestone 编号，两个字段有差异时一起 PATCH。正文独立比较和更新。

## 实施步骤

用命令适配器测试验证读取、写入和失败路径，并覆盖限定编号和排他参数的命令行校验。

## 依赖与交付边界

依赖 m7-01。覆盖已有对象的元数据和限定范围同步。

## 独立验证

```sh
pnpm test:gates
pnpm verify:flow
pnpm flow:sync
```

- 元数据已一致的对象不产生状态 PATCH，Issue 创建/回填和正文同步可继续完成。

## 验收标准

元数据一致时跳过状态和归属写入；相同状态、不同里程碑需要更新。格式错误、缺失字段和无效编号范围均报错。

## 门禁与 CI

- gates、Flow 与在线同步验证。

## 非目标

- 不提升或绕过 GitHub 权限，不吞掉真实状态更新失败。
- 不修改本地 Flow 状态机或 `--retire-missing` 语义。
