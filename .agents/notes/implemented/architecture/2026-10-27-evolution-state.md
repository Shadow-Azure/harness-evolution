# Agent Note: 自进化状态与执行引擎边界

Status: implemented

[English](2026-10-27-evolution-state.en.md) | 中文

## Problem

自进化流程同时需要持久游标、确定性占位聚类和可替换执行器。若每个阶段各自推算六步状态、把占位算法散落在 API 与数据库之间，或在同一个引擎里用空方法伪装未支持阶段，历史 run 会因部署变化而无法复现，前后端也会对同一阶段给出不同结论。

## Decision

`db/crud/evolution.py` 独占 run、cluster、round 与 final 的持久化，条件更新以 `progress_unit` 的期望值为并发边界。`service/evolution/state.py` 是六步 `done/active/pending`、可读性与单步推进的唯一规则。`service/evolution/cluster.py` 独占固定类型顺序、分半规则、占位文案、`TYPE_IMPACT` 与 canonical hash。`EngineFactory` 只按 run 创建时固化的 `engine_key` 选择 `FullEvolutionEngine` 或 `ClusterOnlyEngine`；引擎以 `stages()` 声明能力，未声明阶段与未知引擎都快速失败，cluster-only 只实现 prepare。evaluation gateway 接收深冻结的 `eval_config` 快照，不读取运行期全局配置。

## Alternatives considered

在 job runner 或 API 内重复游标公式会让状态漂移；让数据库 repository 复制聚类策略会形成第二个事实源；在 cluster-only 中保留空的 advance/apply/finalize 方法会把“不支持”伪装成“可调用”；直接传可变配置对象会让创建后的全局设置改动污染历史 run。

## Consequences

后续 M5 切片通过同一个 repository、状态函数与引擎公开面添加目标 API、run API、真实阶段编排和 UI。M5-01 只拥有引擎能力、工厂与 gateway 契约；M5-05 补齐 cluster-only prepare 的具体编排，M5-09 补齐 full prepare 模板及迭代阶段。新增执行器只需注册新的 `engine_key` 并声明阶段；现有表、前端契约与历史 run 选择不变。未注册引擎或错误阶段在启动路径显式失败，而不是静默退化。
