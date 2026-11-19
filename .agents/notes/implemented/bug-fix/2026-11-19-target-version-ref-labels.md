# Agent Note: 对象卡版本行显示 ref 与短 commit

Status: implemented

[English](2026-11-19-target-version-ref-labels.en.md) | 中文

## Problem

对象总览的版本发现把 `agent_events.object_version` 与 `object_revision` 各算一个版本，于是同一条触发记录里的 `main` 和 `digest:8e54…` 在「单个进化对象分析」里拆成两行，生产页只能看到内容 digest。用户无法把版本行对应回自己选择的 tag、分支或 commit，也无法用版本理解潜在 bad case 的分布。

匹配与归因的身份是内容 body hash，不是 ref；ref 还会移动。展示层需要的是“这条版本证据来自哪个 ref、当时解析到哪个 commit”，而不是重新定义身份。

## Decision

对象卡版本以**触发记录**为聚合单位：同一记录里的 ref 与 digest 是同一版本的两个身份，digest 继续作为筛选、匹配、覆盖版本数与统计的规范键，ref 只作为展示主标签。同一 digest 出现在多条记录时合并；ref 优先取最近一次 run 的 `target_version`，否则取 target 的 `defaultRef`，再否则按自然序取一个确定的 ref。

commit 只来自 `evolution_runs.base_commit`：按 `target_revision` 优先、`target_version` 兜底关联，取前 7 位。默认 ref 与 digest 只有 run 关联（事件只带 digest）时，也按 run 的 ref↔digest 关系合并，避免留下 0 行的默认 ref。只有 digest 证据且没有 run 关联的历史记录不反查 git ref，保留 digest 兜底；只有 ref 的旧记录保持 ref 版本。

API 在 `versions` 之外新增 `versionOptions: [{version, ref, commit}]`，详情行也带可空 `ref` / `commit`；前端用 `versionOptions` 渲染 ref + 浅色短 commit，复选框值、URL 与筛选参数仍用规范键。旧 URL 里用 ref 选版本的请求会按别名映射回规范键。

## Alternatives considered

- **用 ref 做规范键**：ref 会移动，同一分支的不同 commit 会被错误合并；匹配与缓存本来按 digest，改动会穿透到 Session 关联与归因语义。拒绝。
- **展示层解析 ref 的当前内容 hash**：能少一次缓存写入，但会把历史 digest 猜测成当前 ref，ref 移动后标签失真；只有 run/触发记录证据才可靠。拒绝。
- **把 digest 截断成短摘要**：能缩短文本，但用户仍无法把版本对应回 tag 或 commit；没有解决信息缺失。拒绝。
- **为所有 digest 反查 git ref**：需要额外的仓库访问和失败路径，且历史记录未必有对应 ref；当前需求接受 digest 兜底。拒绝。

## Consequences

- `versions` 列表与 URL 筛选值从“ref 或 digest”统一为规范 digest；旧链接通过别名兼容，但直接读 URL 的人会看到 digest。
- 对象卡、侧栏和潜在 bad case 列表的主版本标签改用 ref；没有 ref 证据时仍显示 digest。
- `evolution_runs` 查询是只读且有界；目标没有 run 记录时没有 commit，只有 ref 或 digest。
- 同一 digest 对应多个 ref 时只显示一个 ref（最新 run 优先），不会为同一版本生成多行；需要看全部 ref 的场景当前不支持。
