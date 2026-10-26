# Agent Note: 进化对象配置页的权威错误与视图边界

Status: implemented

[English](2026-10-27-target-config-ui.en.md) | 中文

## Problem

自进化启动前需要管理可修改的 skill 与 agent，但配置页同时面对远端 git 校验、admin 写权限、停用但仍需编辑的配置，以及向导只能选择启用项这几种不同事实。若页面自行判断仓库可达性、把停用项从配置列表隐藏，或把 422/409 只做成瞬时提示，用户会丢失输入、无法重新启用配置，且前端与后端可能给出不一致的结论。`plans/14-15-ui-prototype/harness-evolution.html` 没有该新增配置页的截图，但它是现有视觉结构的唯一基准。

## Decision

`/evolution/targets` 使用原型导出的浅色 token、紧凑排版、卡片与状态色，不引入第二套视觉语言；新增表单沿用原型表单的留白、边框与主操作层级。配置列表返回启用和停用项，向导 catalog 只返回启用项。页面按当前用户角色隐藏写操作：成员可读，admin 可新增、编辑、启停和删除。后端的 target service 校验 repo/ref/subDir 的语法与路径规则，`GitRemote` 校验远端可达性与 ref 可用性；`REPO_INVALID` 保留在打开的表单内并保留输入，`TARGET_IN_USE` 保留在列表上下文中。每次写入成功统一失效 `["evolution","targets"]` 与 `["catalogs"]`，让配置页和后续向导共享同一刷新边界。`/evolution` 页头的齿轮入口用于本 Issue 的可发现性；M5-05 接入向导后，最终入口位于名称选择器右侧。

## Alternatives considered

在浏览器中探测仓库或复制 URL/path/ref 规则会让前端成为第二套安全校验源，并暴露无谓的远端请求；在配置列表过滤停用项会使用户无法重新启用；只用短暂 toast 展示 422/409 会让复杂表单输入丢失、运行占用原因也无法持续复核；为新增页面另造一套暗色或演示式视觉会直接偏离原型。以上方案均否决。

## Consequences

配置页的远端反馈受后端超时约束，浏览器不会预判仓库是否可达。成员只能看到配置事实，无法尝试写操作。未来向导必须继续消费 enabled-only catalog，而不是配置列表；若视觉系统调整，应先更新原型和共享 token，再让配置页跟随，避免局部自创样式。
