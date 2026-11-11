# Agent Note: V2 设计文档：多工作空间、总览与归因进自进化

Status: proposed

[English](2026-11-11-v2-design-docs.en.md) | 中文

## Problem

V2 原型（`plans/ui-prototype-v2/`）确立了四类新能力：多用户登录与鉴权接入预留、多工作空间与 bad case 上报额度、工作空间总览、归因移入自进化流程。但 fullstack-design 设计文档仍停留在 V1 目标态：D10 声明单组织共享不做行级隔离，自进化输入以外部 `probe_reports` 为唯一来源，错误详情一个 bad case 只有一条归因，也没有任何总览/空间/上报接口的定义。直接按原型开工会让「实现依据」与文档冲突——issue 正文契约要求设计依据必须链接 `plans/fullstack-design` 的具体章节，冲突时以链接章节为准。

另一个必须先裁决的问题：当前实现已与 V1 设计高度一致（端点、20 张表逐项核对），V2 修改如果直接改写 V1 文档正文，会把「已实现并冻结的 V1 行为」与「尚未实现的 V2 目标」混在同一份陈述里，读者无法判断哪一段是现状。

## Decision

采用「补篇 + 指针」而非全文改写：新增 [15-v2-workspaces.md](../../../../plans/fullstack-design/15-v2-workspaces.md)（鉴权接入接缝、空间/成员/额度/凭据、上报接口、空间化迁移与权限矩阵）、[16-v2-overview.md](../../../../plans/fullstack-design/16-v2-overview.md)（总览双视角口径与聚合接口、Session 最新 10 条 + 回车查询）、[17-v2-attribution.md](../../../../plans/fullstack-design/17-v2-attribution.md)（七步流程、触发点坐标、潜在策略、归因缓存、多归因错误详情、probe 链路退役）三篇，沿续 11–14 号补篇的体例；README 决策表追加 D21–D23，02/05/06/01/07/08 只做增补块与指针注记，明确标注 V1 行为为冻结实现。

关键设计取舍：空间 Session 集合定义为空间 bad case 的根会话投影，轨迹表不加空间列；鉴权接入收敛为 AuthProvider 协议 + 会话桥 + callback 占位，身份栈本身不变；归因落 `bad_case_attributions` 每缓存键一行（workspace+bad case+对象身份+版本+策略版本+归因引擎），复用计数而非按 run 追加行；触发点比较用 `agent_events.triggered_at` 优先、`(agents.tree_index, event_index)` 字典序兜底；候选表全量落库（含被策略排除的行）以保证运行详情可解释；`bad_case_analysis`/`probe_reports`/`probe_cluster_probes` 冻结只读，`analyzed_nonissue` 不迁移（与「非该对象问题」是不同谓词）。

## Alternatives considered

- 全文改写 01–08 为 V2 目标态：会把已实现的 V1 行为与未实现的 V2 目标混排，且改动量覆盖六篇大文档，评审成本高；补篇 + 冻结标注让两代行为都可追溯。
- 在 `plans/ui-prototype-v2/design-v2.md` 上直接扩展成实现设计：该文件是原型验收说明，没有数据库/API/实现层，且不在 fullstack-design 的引用体系里，issue 无法按正文契约链接。
- 轨迹侧也加 `workspace_id`（session_families/agents）：轨迹归一化是全局管线，Session 天然可被多空间上报 bad case，加列要求上报前先定归属，投影口径零迁移即可表达。
- 归因按 run 追加行、查询取最新：错误详情分页与「复用最近一次」都要做二次去重排序；单行真相 + 复用计数让缓存语义和分页查询都更直接。
- `analyzed_nonissue` 迁移为 `non_target`：两者谓词不同（前者否定 bad case 本身，后者只否定对象归属），迁移会篡改历史结论。
- 保留 `POST /api/evolution/probes/query` 做兼容期：生产环境无数据无消费者，直接移除并重出 contracts 更干净。

## Consequences

V2 实现阶段的 issue 可以按 15/16/17 的「代码改动地图」直接切片（空间表与权限 → 上报 → 总览 → 触发点列 → 向导/管线 → 错误详情），每片都有明确设计依据链接。前端需要双轨渲染新旧 run 的 steps（`steps_schema` 判定），旧组件冻结维护直至历史 run 出保留期。`agents.tree_index`/`agent_events.triggered_at` 依赖 parser_version 递增重放才对存量数据生效，实施顺序上必须先于潜在匹配切片。总览「潜在」口径与向导/run 共用 PotentialMatcher 加 60s 缓存，三处数字一致性有回归用例保护。仍欠账：对象在 Session 中「出现」按对象名判定而非版本（agent_events 不记录版本），待上游轨迹带版本信息后再收紧；`/api/probes/*` 与 `/analysis` 端点进入 deprecated 保留期，下个大版本删除。
