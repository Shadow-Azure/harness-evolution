# 修复 flow:sync 的 GitHub 状态 JSON 解析

[English](m11-flow-sync-gh-state-json.en.md) | 中文

```yaml flow
kind: issue
id: m11-08
milestone: m11
depends:
  - m7-01
priority: P1
status: backlog
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

- 正确解析 `gh` JSON 输出中的远端状态。
- 远端状态一致时不发送 PATCH，并让同步继续处理 Issue 正文。
- 用门禁测试锁定字符串 JSON 适配边界。

## 设计依据

- [10 §2 路线图与任务入口](../../../plans/fullstack-design/10-roadmap-draft.md)：流程规划与任务管理边界。

## 实现内容

- 导出只负责解析 GitHub 状态 JSON 的纯函数，对 malformed JSON 和缺失 state fail fast。
- milestone 与 issue 的 CLI adapter 共用解析函数，保持 `runSync` 注入接口不变。
- 增加 gates 自测试，覆盖 milestone 小写状态和 issue 大写状态。

## 实施步骤

1. 写失败测试复现 JSON 字符串被当对象读取。
2. 实现统一解析并接两个 read adapter。
3. 运行 gates、Flow 和一次真实 `flow:sync` 回归。

## 依赖与交付边界

- 依赖：m7-01。
- 交付边界：只修状态读取与无操作 PATCH；不改变 GitHub 权限、退休策略或 issue body 渲染。

## 独立验证

```sh
pnpm test:gates
pnpm verify:flow
pnpm flow:sync
```

- 已一致对象不产生状态 PATCH，Issue 创建/回填和正文同步可继续完成。

## 验收标准

- 远端 `{"state":"closed"}` 和 `{"state":"OPEN"}` 分别解析为原值。
- 非 JSON、缺失 state 或非字符串 state 抛出可诊断错误。
- 当前权限下同步不再因已关闭 Milestone 的无操作 PATCH 中断。

## 门禁与 CI

- gates、Flow 与在线同步验证。

## 非目标

- 不提升或绕过 GitHub 权限，不吞掉真实状态更新失败。
- 不修改本地 Flow 状态机或 `--retire-missing` 语义。
