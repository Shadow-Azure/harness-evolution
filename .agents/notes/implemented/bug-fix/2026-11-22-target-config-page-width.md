# Agent Note: 进化对象配置页的 V2 1720px 页宽

Status: implemented

[English](2026-11-22-target-config-page-width.en.md) | 中文

## Problem

工作区壳层的 `.workspace-main .evolution-page-frame` 把所有工作区页面统一限制为 1080px 内容列，但进化对象配置页按 [08 §9.5](../../../../plans/fullstack-design/08-frontend-implementation.md) 有 8 列，比 V2 原型的 6 列更宽。2026-11-22 在 1408×788 生产视口测得 8 列表格自然宽约 1071px，而内容列内的表格滚动容器 `clientWidth` 只有 996px，最右侧「操作」列被横向滚动容器裁切；1920 视口下内容列仍为 1080px，左右各空 420px。V2 原型的 [`.evo-app .wrap`](../../../../plans/ui-prototype-v2/harness-evolution.html) 是 `width: min(100%, 1720px)`，同视口下内容面板 1360px。现场测量与候选修复见 GitHub #498。

## Decision

- 把共享页宽表达为可覆盖的上限：`.workspace-main .evolution-page-frame { width: min(var(--evolution-page-max-width, 1080px), 100%); }`，并只在 `.target-config-page` 上设 `--evolution-page-max-width: 1720px`。默认 1080px 继续作用于自进化列表与空间管理页；≤640px 的 `width: 100%` 媒体规则仍按原优先级生效。
- 沿用既有 frame 的 24px 左右内边距与 `margin: 0 auto` 居中，不新增内容容器、页宽类或表格列改动；8 列、字段、排序与操作保持原样。
- E2E 在 1408×788、1920×1080、1024×768 断言页宽与内容宽（1408 / 1360、1720 / 1672、1024 / 976）、表格 `scrollWidth === clientWidth`、操作列右缘不超出滚动容器；1024 下要求表格保留横向滚动兜底。1408 与 1920 同时要求页面本身无横向溢出。

## Alternatives considered

- **直接把共享 `.workspace-main .evolution-page-frame` 改成 1720px**：会同时改变自进化列表与空间管理页的页宽，超出 #498 的页面范围；这两个页面是否也要 V2 页宽需要独立 issue 与产品确认。拒绝。
- **压缩仓库列或隐藏表格横向滚动条**：没有把被限制的页宽还给表格，操作列仍可能被裁切，且会改变信息可读性。拒绝。
- **给目标配置页新增 wrapper 或第二套页宽类**：现有 frame 已提供内边距与居中，单页选择器修饰即可，新增结构只会扩大改动面。拒绝。
- **改表格 `min-width` 让 8 列塞进 996px**：只能靠压缩列宽换取不溢出，违背原型与设计文档的列结构，也会牺牲长仓库地址与工程 ID 的可读性。拒绝。

## Consequences

- 1408×788 下内容面板 1360px，8 列与「编辑 / 停用 / 删除」完整显示，表格无横向滚动条；1920×1080 下内容列在 1720px 封顶居中；1024×768 及以下表格保留横向滚动，页面本身不横向溢出。
- 自进化列表与空间管理页仍是 1080px；把它们统一到 1720px 需要独立 issue。
- 单页规则依赖页面根类名 `.target-config-page`；若根类名调整，`main.css` 的选择器与 E2E 断言必须同步。
- 真实浏览器回归落在 `m5-target-config`，继续使用合成 fixture，不读取生产配置或 Session 内容。
