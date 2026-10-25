# Agent Note: 身份后端与一次性事件票据

Status: implemented

[English](2026-10-25-identity-backend.en.md) | 中文

## Problem

M1 业务路由需要一个可验证账号接缝：登录、轮换刷新、强制首登改密、管理员建用户和 SSE 预授权都必须在没有任何用户界面下发凭据的情况下自动可测，同时错误响应不能暴露账号是否存在或密码材料。

## Decision

- `users` 使用一棵双方言 Alembic 迁移；密码用 argon2id，初始管理员只在空库读取 `HE_ADMIN_USERNAME` 与 `HE_ADMIN_PASSWORD` 时播种，并强制改密。
- 访问令牌是 `HE_JWT_SECRET` 签名的 30 分钟 JWT；刷新令牌是 14 天 JWT，写在 `httpOnly`、`SameSite=Strict`、路径限定 `/api/auth` 的 cookie 中，生产环境加 `Secure`。
- 中央鉴权中间件只公开健康、登录和刷新；登录按 IP 限制为每分钟 10 次。强制改密账号只能改密、登出或读当前用户；用户目录要求 admin。刷新每次轮换，并以原子进程内索引单次消费旧 `jti`，记录随令牌到期清理；停用用户登录和刷新返回 `403 FORBIDDEN`。
- 事件票据只在内存保存 60 秒，绑定签发用户、`run:{rid}` topics 与回放游标，消费即删除并按需清理过期未用项；清理后短期保留有界 tombstone，使过期延续 `TICKET_EXPIRED`，而无效 topics 和重放继续使用独立稳定错误码。
- users 表与 CRUD 位于 `db/models/` 和 `db/crud/`，service 只编排认证规则；应用写入的时间戳统一使用 Asia/Shanghai，DDL 不设时间默认值。
- OpenAPI 声明 `BearerAuth` HTTP security scheme，只在登出、改密、当前用户、用户目录和票据签发操作标记 bearer 鉴权。

## Alternatives considered

- 每个路由自行声明鉴权依赖：容易漏保护业务端点，也让强制改密规则分散；否。
- 持久化 refresh 撤销表：单实例 M1 会引入额外迁移和清理任务，当前进程内撤销满足轮换验收；暂不采用。
- 用数据库 session 替代 JWT：强制改密声明会变成每次请求读库，短命 JWT 与前端刷新接缝也不一致；否。

## Consequences

- 进程重启会清空 refresh 撤销索引、登录限流窗口、事件票据和过期 tombstone，这是单实例 M1 的已知边界；多实例化前必须替换为共享存储。
- 用户停用目前只在存储层和登录/刷新行为中验证，尚无管理端点；用户目录首版只提供创建与列出。
- 登录失败通过 argon2id dummy 校验抹平未知用户耗时，但停用账号按设计返回 `FORBIDDEN`，不参与同一耗时伪装。
