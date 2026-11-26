# Agent Note: 同仓多成员作为一个进化对象

Status: implemented

[English](2026-11-26-multi-member-target.en.md) | 中文

## Problem

同一个代码仓常同时提供多个 skill / agent，它们共享仓库、基线、测试工程与归因 Skill，bad case 也来自同一批 Session。改造前 `evolution_targets` 一行承载一个对象，唯一约束是 `(workspace_id, object_type, object_name)`，作用域、测试工程和绑定归因都挂在行上。要把一组对象一起配置和进化，只能建 N 条配置：共享字段重复填写，bad case 归属分散，一次 run 只能针对一个对象，patch 与评测也只覆盖一个目录。最简单的替代——把成员塞进 JSON 列——又无法对成员做唯一约束和按成员 join。

## Decision

- 新增 `evolution_target_members`（`target_id`、`seq`、对象身份、`sub_dir`、冻结定义）与 `evolution_run_targets`（run 的成员快照）；`evolution_run_candidates` 增加 `object_type/object_name/object_revision`。共享字段留在 `evolution_targets`，旧对象列保留一版写首个成员。
- 服务层保存时逐成员校验名称与子目录、拒绝配置内重复；成员表上的 `(workspace_id, object_type, object_name)` 唯一索引保证同一成员只属于一条配置，冲突返回 `409 MEMBER_ALREADY_CONFIGURED` 并定位到 `members[i].objectName`。
- 保存配置只做一次 `git ls-remote`，逐成员冻结 `{sub_dir}/SKILL.md` 或 `AGENT.md`。绑定快照存 `members[]`，匹配条件带 `targets[]`：任一成员出现的 Session 都关联，每个 case 用自身对象的入口点比较，并按自身对象或其所属成员写归因报告；单成员配置的缓存键保持逐字不变。
- 启动向导改选配置并发送 `targetId`。run 创建时同事务写 `run_targets`；prepare 逐成员 `git cat-file` 校验目录，任一缺失以 `stage="subdirectory"` 失败；patch 的 `allowed_paths` 与评测 `asset_paths` 覆盖全部成员，提交主题和提示词列出成员。
- 投影按“配置 + 成员”两级：catalog 增加 `targets[]`，run card/detail 增加 `targets[]` 与 `workspace.subDirs`，第 1/2/3 步显示成员，总览一条配置一行并合并成员行，case 表用 `object_name` 标注命中成员。

## Alternatives considered

- **每个成员一条配置 + 向导多选**：用户已否决；配置重复、bad case 归属分散，并被迫引入“主对象”。
- **只做批量填表、run 仍单对象**：解决不了“一起进化”的核心诉求。
- **把成员做成 JSON 列**：无法对成员做唯一约束与按成员 join，绑定和总览都要拆 JSON。
- **跨仓库成员**：一个 run 只有一个 `base_commit`；跨仓需要多仓 run 模型，超出本 issue。
- **每成员独立测试工程或独立评测**：评测平台一次 launch 只认一个模板与一个指标；多资产是同一模板下的路径覆盖。

## Consequences

- 旧列继续写首个成员供 V1 读端点和历史 run 兜底；历史配置由 0035 回填为单成员配置，历史 run 回填 `run_targets`。
- 成员定义逐成员冻结，配置改动会重置绑定 generation；单成员行为与缓存键不变。
- 总览把同一 case 的同一版次跨成员去重，成员作为 chip 与 case 表列展示。
- 后台绑定失败仍整批记录并按 generation 重试；完成 case 不重复。
- 旧列收紧或删除、跨仓成员、每成员独立评测工程留到后续版本。
