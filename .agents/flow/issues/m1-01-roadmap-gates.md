# 重建可验证路线图与流程门禁

[English](m1-01-roadmap-gates.en.md) | 中文

```yaml flow
kind: issue
id: m1-01
milestone: m1
depends: []
priority: P0
status: done
scope:
  - .agents/flow/**
  - .agents/notes/**
  - scripts/**
  - .github/workflows/ci.yml
  - AGENTS.md
  - package.json
  - plans/**
adr:
  - ../../notes/proposed/process/2026-10-24-verifiable-roadmap.md
github:
  number: 24
  url: https://github.com/Shadow-Azure/harness-evolution/issues/24
```

## 背景

旧流程树混合了已废弃时间线和过窄依赖，无法保证每个 issue 独立验收；本次替换必须把设计基线、依赖、验证命令和门禁接线变成机械约束。

## 目标

- 建立 m1–m6 六阶段路线图和 41 个可独立验收 issue。
- 用稳定 id、依赖、完整章节和双语配对约束 issue 质量。
- 让 GitHub issue 正文与本地详细契约同步，并支持只关闭退休对象。

## 设计依据

- [README 决策表](../../../plans/fullstack-design/README.md)
- [09 高风险清单](../../../plans/fullstack-design/09-review-guide.md)
- [10 路线图草案](../../../plans/fullstack-design/10-roadmap-draft.md)

## 实现内容

- 扩展 flow schema 的 id/depends 字段，机械检查未知引用、跨阶段前向依赖和环。
- 要求 issue 包含背景、目标、设计依据、实现内容、实施步骤、边界、独立验证、验收、门禁与非目标。
- flow:sync 发布完整中文正文，并在显式 --retire-missing 时只关闭不在新树的开放远端对象。
- 新增 Agent Note 记录重规划、真实数据边界和远端不删除策略。

## 实施步骤

1. 先为 id/依赖/章节、正文渲染、正文同步和退休计划写失败测试。
2. 实现 schema 校验、生成器模板和 flow:sync 行为。
3. 删除旧流程树，生成新 roadmap、milestone、issue 和 Agent Note。
4. 重录双语配对，运行 verify:flow、test:gates、verify:docs。
5. 重新认证 gh 后执行 flow:sync -- --retire-missing，再做在线校验。

## 依赖与交付边界

- 依赖：无
- 交付边界：只改变流程、脚本和决策记录；不实现产品代码，不修改轨迹数据，不物理删除 GitHub 对象。

## 独立验证

```sh
pnpm test:gates
pnpm verify:flow
pnpm verify:docs
```

- 13 个门禁自测试通过；新增缺失章节、坏依赖、正文同步和非本树退休的用例全部失败可复现。
- `pnpm verify:flow` 输出 ok，且 41 个 id 无重复、无未知依赖、无环。
- `git check-ignore claude-code-sessions` 命中且 issue 正文无轨迹原文。

## 验收标准

- 本地与 GitHub 均为 6 个 milestone、41 个 issue。
- 每个 issue 有稳定 id、依赖、设计章节链接、实施步骤、验证命令、验收标准和门禁说明。
- 旧开放对象被关闭且仍可通过编号访问。
- CI 元门禁覆盖新 schema 与同步脚本。

## 门禁与 CI

- test:gates 覆盖 flow-lib、flow-sync、route-gates 和 CI 接线。
- verify:flow 拦截占位正文、坏依赖和跨阶段前向依赖。
- verify:docs 拦截双语结构漂移和死链。

## 非目标

- 不实现 FastAPI/Vue 产品代码。
- 不把 claude-code-sessions 或 data 提交仓库。
- 不删除 GitHub issue/milestone。
