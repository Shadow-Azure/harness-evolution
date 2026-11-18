# Agent Note: Session 问题列表卡以描述为主体

Status: implemented

[English](2026-11-18-problem-card-description.en.md) | 中文

## Problem

Session 错误查看页右下的「问题」列表卡曾把归因摘要当作第二行正文：`badCaseSummary` 对未分析 case 固定返回「尚未完成归因分析」，对已分析 case 返回归因 `summary` / `reason`。于是未分析 case 在会话页看不到任何问题现象，只能进入错误详情页才能读到描述；同一位置在 V2 原型 `FindingList` 里显示的是问题描述，并带类型/对象徽章、完整 case ID、facts、「关联：…」与「定位 ↗」。[#370](https://github.com/Shadow-Azure/harness-evolution/issues/370) 记录了这处信息层级偏差，并要求在「保留归因摘要」与「按原型显示描述」之间给出结论。

列表卡同时只显示 `badCaseId` 前 8 位，外部上报的 `bad_case_type`、`object_name` 与关联行都没有进入卡片，未分析 case 的卡片因此既没有现象也没有对象上下文。

## Decision

列表卡信息层级以 V2 原型为准：第二行显示 `problem.reason`（描述正文），按 `renderMarkdown(..., { images: false })` 安全渲染；头部依次是 `title`、`badCaseType`（`self` / `discovery`）徽章、`objectName` 徽章、完整 `badCaseId` 深链与轻量归因状态胶囊；正文下方是 key/value 双列 facts（与原型和错误详情页同构）与「关联：`objectType` · `objectName`」，行尾「定位 ↗」。`badCaseSummary` 随之删除，归因摘要不再进入列表卡。`BadCaseList` 非 compact 模板改用 compact 模板已有的覆盖按钮模式：正文 `pointer-events: none`、链接提升到按钮之上，整卡仍是定位按钮，描述里的 Markdown 链接不会被选中动作吞掉。V2 原型的 `FindingList` 同步改为 `renderMarkdown(f.detail)`，让原型与实现共用同一 Markdown 约定。

类型徽章沿用错误详情页的 token 映射（`self` 紫、`discovery` 蓝），不跟随原型样式表里相反的映射，因为同一 case 在两页显示不同颜色更难理解；原型自身的不一致留待单独收敛。

## Alternatives considered

保留归因摘要并同步更新原型与设计文档被否：原型在 `FindingList` 与 `FindingDescription` 里都以描述为主体，`#370` 的诉求正是未分析 case 也能在会话页读到现象；把摘要留在列表卡仍需要用户为未分析 case 打开详情页。继续只显示前 8 位 ID 被否：完整 ID 是复制与排查的入口，8 位前缀在真实 UUID 上不可区分，原型的 `fi-id` 也是完整 ID。把 Markdown 描述直接塞进原按钮被否：`renderMarkdown` 会产出 `<a>`，`<a>` 嵌在 `<button>` 里既不合规，点击链接还会同时触发选中；覆盖按钮把链接抬到按钮上层，保住整卡点击。给描述加行数截断被否：截断位置对 F2P/P2P 清单不可靠，会隐藏用户最需要看的用例名；原型也展示完整描述。把描述退化成纯文本被否：#363 已把同一字段定为 Markdown，列表与详情应同一渲染，否则列表会显示原始 `**` 与反引号。

## Consequences

长描述会让卡片变高，会话页问题列表不再等高；这是显示完整问题的直接代价，原型同样如此。描述正文与卡片一起被按钮覆盖，文本不可框选，与 compact 卡片和原型一致；需要复制的长清单仍可进入错误详情页。`badCaseSummary` 删除后没有归因摘要在列表中的入口，归因结论只在错误详情页与错误详情的问题卡出现。V2 原型 `FindingList` 改渲染 Markdown 后，原型与生产共用同一套描述排版，后续原型截图可直接作为验收基线。类型徽章配色在列表与错误详情页一致，但仍与原型样式表相反，属于已知未收敛差异。
