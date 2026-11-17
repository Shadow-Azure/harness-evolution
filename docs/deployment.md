# 部署

[English](deployment.en.md) | 中文

生产是阿里云单实例 SaaS：nginx 托管前端并反代 `/api` 到本机 uvicorn（127.0.0.1:8787），MySQL 8 同机。发布由 GitHub Actions 完成：main 的 CI（`ci-ok`）全绿后，`Deploy` 构建前端、推送 release、迁移、切软链、重启，探活失败回滚。设计依据见 [plans/fullstack-design/01-architecture.md §6](../plans/fullstack-design/01-architecture.md)。

## 云资源

| 资源 | 配置 |
|---|---|
| ECS | 单实例，Ubuntu 22.04/24.04，2核4G（2核2G 需 swap），带宽 ≥3Mbps |
| MySQL 8 | 与服务同机（apt 安装），库 `harness_evolution`，账号 `harness@127.0.0.1` |
| 安全组 | 放行 22/80/443；8787 不公网开放 |
| 域名 | 可选；先用 IP + HTTP，绑域名后补 HTTPS 与 ICP 备案 |

## 服务器目录

| 路径 | 内容 |
|---|---|
| `/opt/harness/releases/<sha>/` | 单次发布（`api/` 源码 + `web/` 静态产物） |
| `/opt/harness/current` | 软链指向当前 release，nginx 与 systemd 的工作目录 |
| `/opt/harness/shared/.env` | 生产 `HE_*` 配置（模板：[deploy/env.production.example](../deploy/env.production.example)） |
| `/opt/harness/shared/venv/` | 共享 Python 虚拟环境 |
| `/opt/harness/shared/config/` | 流水线推送的部署配置（systemd/nginx/release.sh） |

## 首次初始化

初始化由 [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) 完成（基础包、Python 3.12、用户、MySQL、nginx、systemd），逐步操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。

## GitHub 配置

| 名称 | 类型 | 内容 |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS 公网 IP |
| `ALIYUN_USER` | Secret | SSH 用户（`deploy`） |
| `ALIYUN_SSH_KEY` | Secret | deploy 用户 ed25519 私钥 |
| `ALIYUN_SSH_PORT` | Variable | SSH 端口（默认 22） |
| `production` | Environment | 发布 job 的保护环境，可配人工审批 |

私钥只存 GitHub，公钥在服务器 `deploy` 的 `authorized_keys`；运行密钥只存 `/opt/harness/shared/.env`。

## 评测配置注入

评测平台密钥经 GitHub Secrets（`HE_EVAL_MODE`/`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY`）注入服务器 `.env`；`apiKeyRef` 只存环境变量名，未配置时注入步骤跳过。操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)，模板见 [deploy/env.production.example](../deploy/env.production.example)。

## 发布与回滚

- 触发：push main → CI 全绿 → `Deploy`；支持 `workflow_dispatch` 手动触发。
- 行为：[deploy/release.sh](../deploy/release.sh) 安装依赖 → `alembic upgrade head` → 切换 `current` 软链 → `systemctl restart harness-api` → 探活 `/api/health`（最长 60 秒）。
- 回滚：探活失败时软链退回上一 release 并重启；本地保留最近 5 个 release。
- 迁移幂等：连续发布对已应用的迁移零副作用。

## 上游健康与漂移日志

配置 `HE_UPSTREAM_BASE_URL` / `HE_UPSTREAM_TOKEN` 后，pull 输出结构化 `upstream.health` / `version_drift` / `contract_drift` 日志，只含枚举、计数与主版本号，不含正文、会话 id 或凭据。逐会话失败留在 `sync_runs.errors`；调度器只重放 payload，上游抓取失败需用 `POST /api/acquisition/pull` 带 `sessionIds` 重拉。

## 故障排查

- bad case 详情 409/503 表示轨迹未就绪，不是数据丢失；检查轨迹查询配置或补 `sessionSource`。

## 外部表只读权限与契约日志

读路径只需 `bad_cases`、`bad_case_analysis`、`probe_reports` 的 SELECT；上报、目录同步与归因写入还需要 INSERT/UPDATE（不删除外部行）。启动后默认每 5 分钟巡检列与类型契约（`HE_EXTERNAL_CONTRACT_CHECK_INTERVAL_SECONDS` 可调），输出 `external.contract_check`、`external.contract_drift`、`external.row_drift`。读失败返回稳定 503（`EXTERNAL_SCHEMA_DRIFT` / `EXTERNAL_READ_FORBIDDEN` / `EXTERNAL_READ_FAILED`）；`external.read_failed` 只含表名、方言、错误类、驱动码与稳定码，不含 SQL 与参数。
