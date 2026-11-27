# Agent Note: 由被归因对象管理候选来源

Status: implemented

[English](2026-11-26-target-candidate-sources.en.md) | 中文

## Problem

上报 A 的 case 可以要求分析随后执行的 C。单靠 C 首次出现的位置会漏掉后续重复执行，向导和自动批次也可能选出不同的 case。

## Decision

将来源规则归属到被归因对象，创建时确认，之后在对象卡片独立维护。来源按类型和名称匹配，保存每条命中规则的上报锚点和目标执行证据。方向规则在同一根 Session 的各次目标执行中寻找严格早于或晚于锚点的证据。参见 [#625](https://github.com/Shadow-Azure/harness-evolution/issues/625)。

来源身份取自工作区关联的 bad case。用 workspace_bad_cases 的存在性判断圈定可见记录，同一上报被多次分配也只计一次。名称按大小写精确匹配。历史上报决定可选名称，所选时段决定 self 和 discovery 的数量。目录标签优先，直接上报可使用 metaData.label。缺少真实锚点的记录仍可查看。来源重复执行且无法定位具体上报时，只能满足同 Session 条件。

## Alternatives considered

要求来源先注册为进化对象会让单纯上报问题的 Skill 也承担仓库与版本配置。只使用首次执行作为时间证据会漏掉 C1、A1、C2 中的 C2。

## Consequences

总览、向导和自动归因共享候选匹配器。创建对象时在同一事务保存归因绑定和来源规则。已绑定对象修改规则时刷新绑定代次，沿用该代次的截止时间扫描历史。启动运行时保存规则快照，持久化每个候选的原始上报身份和命中坐标。规则收缩后仍可查询已生成的报告。
