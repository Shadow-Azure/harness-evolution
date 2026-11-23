# Agent Note: 归因 Skill 配置与运行快照界面

Status: implemented

[English](2026-11-17-attribution-skill-config-ui.en.md) | 中文

## Problem

平台已有 target、workspace 与 platform 三级归因 Skill 解析以及 Run 启动时的版本固化，但用户无法在对象配置中查看有效来源、切换或回退版本，也无法在启动和运行详情中确认实际使用的 Skill，配置结果因此不可验证。

## Decision

对象配置页为管理员提供 target 级绑定、旧版本回退和解除绑定，成员只读查看有效 Skill。可选项仅包含已发布、启用、Probe Report V2 兼容且当前可执行的版本；真实 `agent` executor 在内网引擎接入前不允许新绑定。启动向导展示解析后的来源、revision 与 executor，并说明 Run 会固化该版本；运行详情只展示 Run 自身保存的 Skill key、revision、content hash 与 engine，不重新解析当前配置。

## Alternatives considered

没有在浏览器中提供 Skill 正文编辑器，因为 Skill 仍由受控注册表发布，配置界面只负责选择版本。没有让运行详情查询最新有效绑定，因为那会把历史运行伪装成使用了后来修改的配置。没有允许选择尚不可执行的 `agent` 版本，因为公开环境无法兑现该运行语义。

## Consequences

管理员可以完成绑定、回退和恢复继承默认值，所有用户能在启动前和运行后核对归因引擎。前端依赖真实 Skill API 与共享契约，绑定变化通过查询失效立即刷新。后续接入内网 LLM Agent 时，只需开放可用 executor 并补充相应能力状态，不改变此交互模型。
