# Agent Note: 进化对象配置页的返回入口指向 /evolution

Status: implemented

[English](2026-10-30-target-config-back-entry.en.md) | 中文

## Problem

从「启动自进化」向导或 `/evolution` 页头进入 `/evolution/targets` 配置页后，页面内没有任何返回自进化页的入口（#151）；用户只能靠顶栏导航绕回。ClusterPreview 与 RunDetail 都有返回路径，唯独配置页缺失。

## Decision

配置页内容最上方加 `RouterLink to="/evolution"` 的「← 返回自进化」链接，样式与 RunDetail 的 `.back` 一致（12px 灰字、hover/focus 变蓝），并用 `data-testid="target-config-back"` 固定测试钩子。显式 `to="/evolution"` 而不是 `router.back()`：直达、刷新、新标签打开时行为可预期，与既有返回路径同构。单测断言链接存在且 `href` 为 `/evolution`；E2E 在真实浏览器里点击后断言落在 `/evolution`。

## Alternatives considered

`router.back()` 被否：直接打开配置页时无历史可退，行为不可预期。放在 `page-head` 右侧被否：原型（harness-evolution.html 的 targets 页）把返回链接放在标题上方，RunDetail 同位置已有先例，保持一致减少认知负担。新增按钮组件被否：一个静态链接不值得抽象。

## Consequences

配置页在任意状态（有数据、空态、读取失败）都保留该链接，因为它在页面骨架上、不在数据分支里；键盘可达（原生 `<a>`）。以后若有页面也从别处进入配置页（如 Session 页），仍指向 `/evolution`——不随来源变化，保持「返回自进化页」的单一语义。
