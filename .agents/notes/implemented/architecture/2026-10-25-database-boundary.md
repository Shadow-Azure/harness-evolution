# Agent Note: SQLite/MySQL 双方言数据库边界

Status: implemented

[English](2026-10-25-database-boundary.en.md) | 中文

## Problem

鉴权、轨迹归一化和自进化都需要持久化，但两种调用环境不同：生产使用 MySQL 8，测试与本地快跑需要 SQLite。如果业务代码直接创建 engine 或写方言 SQL，本地通过与生产失败会混在一起；如果迁移按方言分叉，又会让表结构无法对账。

## Decision

- `Database` 协议统一提供连接生命周期、只读 session、写事务和 health；`create_database()` 是 `HE_DB_DIALECT` 的唯一分派点。
- SQLite 连接启用 WAL、foreign keys、busy timeout 与 NORMAL synchronous；MySQL 使用连接池、pre-ping、回收与 `+08:00` 会话时区。
- Alembic 使用一棵迁移树和 async URL，SQLite 以 batch 模式处理表变更；领域表由后续 issue 添加，本阶段只建立空基线。
- `/api/health` 同时报告 API 与数据库状态；连接失败不阻止进程启动，而是返回 HTTP 503 与脱敏数据库摘要。服务端日志只记录阶段、方言与异常类型，不记录原始驱动文本、URL、主机或路径。
- `-m mysql` 的 repository contract 与 SQLite 共用同一套 SQLAlchemy 表达式；CI 的 MySQL 8 service 必须执行该套测试。

## Alternatives considered

- 为 SQLite 与 MySQL 各写一套 repository：会复制业务查询并很快漂移；否。
- 启动时连接失败就终止 FastAPI：运维只能看到进程退出，无法通过健康检查区分 API 与数据库故障；否。
- 每个方言各维护一棵 Alembic 迁移树：表结构对账与切换成本更高；否。
- 只在 SQLite 上跑完整测试：无法发现 MySQL 索引、方言或连接参数问题；否。

## Consequences

- CI 同时承担 SQLite 快测和 MySQL service lane，耗时与基础设施依赖增加，但跨方言回归在合并前可见。
- 后续业务只能依赖 `Database` 与 repository 接口；新增方言或连接策略的改动收敛在 `apps/api/app/db/`。
- health 契约包含 `version` 与 `db`，前端可以区分 API 不可达和 API 可达但数据库异常。
- 空迁移不创建领域表，后续表结构必须通过新 revision 演进，不能修改已发布基线。
