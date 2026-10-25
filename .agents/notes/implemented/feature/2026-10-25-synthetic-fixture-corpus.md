# Agent Note: 合成 Fixture 语料

Status: implemented

[English](2026-10-25-synthetic-fixture-corpus.en.md) | 中文

## Problem

M2 的后续解析、查询和展示都需要一组可重复、足够小且不包含真实轨迹的开发数据。只在测试里构造内存对象会让运行时路径、数据库约束和演示数据分离，无法证明前端或 API 读取的是生产同构表。

## Decision

`fixtures/m2-synthetic/` 保存四棵确定性 Agent 会话树、逐 agent JSONL、问题/归因和目标配置。manifest 使用封闭 Pydantic schema；项目路径限定在合成的 `/workspace/` 根，仓库 URL 不接受凭据。payload 的文件路径必须留在 corpus 内，每个 JSON 对象拒绝重复键，每行 `sessionId` 必须与 manifest 会话一致，子 Agent 还必须声明匹配的 `agentId`。SHA-256 与行数由原始字节派生，单项和总量都有字节上限，并拒绝本地真实路径或密钥标记。

seed 在 demo 或测试环境通过 Alembic 创建基础领域表，然后在一个事务中按稳定键 upsert 轨迹 payload、处理索引、会话、agent、触发点、用户输入、问题、归因和进化目标。写入前完成整棵 corpus 校验；相同内容重复执行不写库，源字段变化时原位更新且不替换主键。已有 `source_records.received_at`、处理状态与 `last_sync_run_id`、已有进化目标的管理员归属属于运行态，重复 seed 不覆盖；`created_by` 只在插入目标时初始化。主 Agent 的问题锚点固定为 `null`，非空锚点只能引用同一会话的子 Agent。`fixtures:check` 提供无数据库的静态检查，CI 同时执行 check 与 seed。

## Alternatives considered

- 只在测试代码里构造对象：会绕过真实表、迁移和唯一约束，不能作为演示数据。
- 把 JSON 当运行时数据源：会引入设计已禁止的 stub provider，并让 API 与 fixture 漂移。
- 直接提交 SQL 或真实会话：难以审计，容易携带本机路径、凭据或过大的私有内容。
- 在 M2-01 创建全部自进化父表和派生簇表：超出本切片边界，先由后续 issue 在相同迁移树上扩展。

## Consequences

后续 M2 issue 必须复用 `app.db.models.domain` 与同一组表，不得建立第二套数据模型。fixtures 当前只描述结构化元数据和原始 JSONL，不包含消息/内容块明细；归一化仍需由后续同步任务从 payload 生成并验证统计。`0004` 在迁移内冻结本 revision 的表、索引与外键定义，未来表结构变更必须新增 Alembic revision，不能依赖修改旧迁移或可变模型 metadata。
