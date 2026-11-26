# Agent Note: 同仓多成员进化对象

Status: proposed

[English](2026-11-26-multi-member-evolution-target.en.md) | 中文

## Problem

「进化对象」今天是一条配置一个对象：唯一约束 `(workspace_id, object_type, object_name)`，作用域 `sub_dir`、验证集/测试集测试工程与绑定归因都挂在同一行。同一个代码仓里常有多个 skill 和 agent（如 `skills/deep-research` 与 `skills/code-review`），它们共享仓库、基线与评测工程，bad case 也常来自同一批 Session。按对象拆成多条配置会重复填仓库、测试工程与归因 Skill，把 bad case 归属分散到多条配置，并让一次 run 只能进化一个对象；patch 只能改一个目录、评测只能提交一个资产。

## Decision

一条 `evolution_targets` 依旧是一个进化对象，但对象身份下移到新的 `evolution_target_members`：配置行只保留共享字段（仓库、基线、验证集/测试集测试工程、主指标、归因 Skill、启用），成员行承载 `object_type / object_name / sub_dir` 与各自的定义快照。启动向导、run 快照、patch 范围、评测资产与七步展示都以这条配置为单位：run 新增 `evolution_run_targets` 记录成员快照，`MatchCondition` 改为成员列表，`allowed_paths` 返回成员目录的并集，评测一次提交全部成员资产。

成员必须同仓（一个 run 一个 `base_commit`），且一个成员只能属于一条配置（否则 bad case 与归因报告歧义）。兼容窗口内 `evolution_targets` 的旧列保留一版、写首个成员，历史 run 无成员行时按旧列读取；单成员配置的归因缓存键与改造前逐字相同。评测平台的 `asset_paths` 是多值列表、一次 launch 只认一个模板，因此测试工程与主指标必须共享，这与本决策一致。

## Alternatives considered

每个成员各一条配置、向导多选同仓对象：配置重复、bad case 归属分散，且被迫引入"主对象"概念，用户已否决该交互。只做批量填表、run 仍单对象：解决不了"一起进化"。把成员做成配置上的 JSON 列：无法对成员做唯一约束与按成员 join，绑定与总览都要拆 JSON。让同一成员属于多条配置：bad case 与归因报告会歧义，从 bad case 启动也无法确定配置。把测试工程下放到成员：平台一次 launch 只认一个模板，多成员无法在一次评测里评完。

## Consequences

配置、绑定、启动、patch、评测与展示都从"单对象"变成"配置 + 成员"两级，改动集中在配置服务、绑定 worker、潜在匹配、启动与准备、patch 范围、评测请求与 run 投影；迁移需要回填成员与 run 成员两张表。V1 读端点与历史 run 靠旧列过渡一版，下一版再收紧。同一成员不能同时用于两条配置，这条约束在保存时全局校验；跨仓成员不在本决策范围内。
