# Agent Note: 归因列表版本标识显示 ref / commit

Status: proposed

[English](2026-11-20-attribution-version-labels.en.md) | 中文

## Problem

Session 错误查看页左侧归因列表只渲染 `probe_reports.object_version`。当对象版本只有 `digest:<sha256>` 证据时，71 字符的版本号在窄侧栏里不可收缩、无截断，会把对象名挤成 0 宽并压住「缓存 / 可归因」标签。总览的版本行已经按 m17（[2026-11-19-target-version-ref-labels](../../implemented/bug-fix/2026-11-19-target-version-ref-labels.md)）显示 ref + 短 commit，但归因列表的契约没有 ref / commit，也没有长值查看和复制入口；V2 原型样例使用短 tag，默认状态没有暴露这个问题。

## Decision

归因列表项优先显示可读的 ref + 短 commit（与总览一致），只有 commit 时显示短 commit，只有 digest 证据时保留 digest 兜底。版本区可收缩并省略；悬停或聚焦时在版本上方显示完整值；旁边的复制按钮复制完整版本标识（commit 优先，digest 兜底）。生产 `AttributionItem` 增加可空 `objectRef` / `objectCommit`，从 run 的 `targetVersion` / `targetRevision` / `baseCommit` 回填；`digest` 仍是匹配与缓存规范键，只作为展示兜底。先更新 V2 原型，生产 API 与前端随后按同一 issue 落地。

## Alternatives considered

- 只把 digest 截断、不换 ref / commit：能消除重叠，但仍与服务端已持有的可读 ref 不一致，总览与归因列表继续两套口径。
- 为历史 digest 反查 git ref：需要逐个仓库遍历 ref 与内容 hash，成本和不确定性都高，且 m17 已明确不做。
- 版本换行到第二行：能容纳长值，但会让归因项从两行变三行，压缩侧栏信息密度，也改变列表节奏。
- 只用原生 `title`：实现最省事，但提示延迟、位置不可控，在滚动容器和缩放下不稳定，也无法承载复制动作。
- 把 ref / commit 拼进缓存键：会改变归因复用语义，超出展示层范围。

## Consequences

生产需要一次契约与读取路径变更（API 回填 ref / commit）和一次前端组件更新；只有 digest 的历史归因仍显示截断 digest，不丢数据也不反查。原型先固化交互（截断、上方浮层、复制）并补 Before / After；生产实现必须与原型同区域可比。归因匹配、缓存键、分页与统计不变。生产截图和用户 Session 内容不进入仓库。
