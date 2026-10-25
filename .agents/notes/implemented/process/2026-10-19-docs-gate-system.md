# Agent Note: 文档、检视与流程门禁体系

Status: implemented

[English](2026-10-19-docs-gate-system.en.md) | 中文

## Problem

仓库已有前后端脚手架，但文档、开发流程与检视仍靠对话记忆：阶段目标没有承诺面，改动没有任务边界，文档结构容易漂移，PR 检视也没有稳定的证据与分流规则。需要把 StudyWiki 已验证的文档工程、门禁工程与 PR 检视体系移植到本仓库，并适配 `apps/*`、`packages/*` 的 monorepo 结构。

## Decision

- 文档分层采用"一个事实一个 home"：现状进 `docs/`，决策理由进 `.agents/notes/`，开发流程进 `.agents/flow/`，事故叙事进 `docs/postmortem/`。
- 常驻文档采用中英三件套与 hash 配对记录；结构镜像、链接 locale 与切换行由 `verify-translation-pairing` 机械校验。
- 开发流程采用 roadmap → milestone → issue → ADR 四层；机读字段放 `yaml flow` 围栏；issue 编号耦合 GitHub 编号，`bootstrap: true` 只给流程自举的第一个 milestone。本次只安装机制，不预填任何 roadmap / milestone / issue 实例，流程树由维护者讨论后初始化。
- 门禁分两档：`doc-quick` 覆盖索引、预算、换行、配对、术语、type-equiv、导出注释与源码引用；`doc-sync` 追加 ts 围栏真实编译、死链与门禁自测试。
- 移植 `pr-review`、`pr-review-fix`、`computer-use`、`computer-use-smoke-reporting` 与 walkthrough 元数据技能；检视文档落 `plans/`，不进入 Agent Notes。
- 冒烟报告模板独占 `<table>` 边界，renderer 只输出 thead/tbody 片段；coverage 行按 schema 字段映射，并由门禁自测试用真实 renderer 输出锁定。
- 扫描面从 StudyWiki 的 `src/` 改为 `apps/*/src` 与 `packages/*/src`；去掉 Tauri、Rust、产物链接与讲解站专用门禁，保留与产品技术栈匹配的部分。

## Alternatives considered

- 只复制脚本不复制文档契约：门禁读不懂"为什么红"，维护者会把豁免当默认路径；否。
- 保留单语文档：参考工程的配对门禁与重录工具有完整价值，单语会让结构镜像与术语供给链失效；否。
- 预填一套示例 roadmap / milestone / issue：会把移植者的假设当成维护者的承诺，后续讨论反而要拆掉；否，机制先落地，实例由维护者讨论后创建。
- 移植全部 StudyWiki 门禁：Tauri 产物、Rust 命令目录与讲解站在本仓库没有对应对象，空跑只会制造噪音；否。

## Consequences

- 文档改动的最小操作变成"改两侧 + 重录"，首次建立成本较高，但后续漂移可机械发现。
- `flow:sync` 与 `verify:flow-online` 依赖 `gh` 登录；流程树当前未初始化（缺 `.agents/flow/roadmap.md`），`verify:flow` 报 skipped，GitHub 无 milestone / issue；初始化讨论后再由 `flow:sync` 创建。
- 门禁自测试使用 Node 内置 `node --test`，不新增依赖；后续新增门禁叶子须同步 `run-gates` 与自测试。
- 当前未移植讲解站与发布流水线；若后续需要，按本 Note 的分层与门禁模式增量接入。
- 冒烟报告模板或 schema 改动必须同时验证单层 table 结构与 coverage 实际内容，否则生成物可能合法渲染但丢失覆盖证据。
- 欠账：roadmap / milestone / issue 的内容与优先级待维护者讨论后设置；PR 检视文档模板尚未用真实 PR 验证。
