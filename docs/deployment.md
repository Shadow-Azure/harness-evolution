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
| `/var/lib/harness-evolution/` | 服务端数据目录，systemd `StateDirectory=` 创建并授权给 `harness`；`HE_DATA_DIR` 指向其下 |

## 首次初始化

初始化由 [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) 完成（基础包、Python 3.12、用户、MySQL、nginx、systemd），逐步操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。

## GitHub 配置

| 名称 | 类型 | 内容 |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS 公网 IP |
| `ALIYUN_USER` | Secret | SSH 用户（`deploy`） |
| `ALIYUN_SSH_KEY` | Secret | deploy 用户 ed25519 私钥 |
| `ALIYUN_SSH_PORT` | Variable | SSH 端口（默认 22） |
| `HE_DATA_DIR` | Variable | 数据目录绝对路径；留空用 `/var/lib/harness-evolution/data` |
| `XRAY_CONFIG` | Environment Secret | 可选：完整 Xray JSON（VLESS 出站 + 回环 mixed 入站），见 [Git 出网代理](git-proxy.md) |
| `production` | Environment | 发布 job 的保护环境，可配人工审批 |

私钥只存 GitHub，公钥在服务器 `deploy` 的 `authorized_keys`；运行密钥只存 `/opt/harness/shared/.env`，代理配置只存服务器 `0600` 文件。

## 配置注入

数据目录与评测配置经同一通道写入服务器 `.env`：`Deploy` 从 GitHub Environment `vars.HE_DATA_DIR` 取绝对路径（空值用默认），评测平台密钥经 GitHub Secrets（`HE_EVAL_MODE`/`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY`）注入；`apiKeyRef` 只存环境变量名，未配置时跳过。Git 推送凭据同通道注入：`HE_GIT_PUSH_PROVIDER` 总是写入，`HE_GIT_PUSH_TOKEN` 为空时移除旧键，`GIT_ASKPASS` 指向 `/opt/harness/shared/git-askpass.sh`。值经 base64 传输、`inject-config.py` 原子写入并保持 `.env` 0600，注入前备份 `.env.bak.<sha>`；解码失败告警跳过并保留旧值，写盘失败中止发布。操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)，模板见 [deploy/env.production.example](../deploy/env.production.example)。

### AI Agent 配置

模型审查与 patch 生成经 Secrets 注入 `AI_AGENT_PROVIDER`、`HE_AI_AGENT_FAILURE_POLICY`、`HE_PATCH_SOURCE_MODE`：非空写入 `.env`，缺失或空显式 `--unset`。`HE_AI_AGENT_FAILURE_POLICY` 留空按 provider 推导（`fake` → `degrade`，其余 → `strict`）；`strict` 下聚类 AI 失败让 run 在聚类阶段显式失败。值含换行/回车时注入前失败，其余解码失败告警跳过并保留旧值（默认值与合法值见[模板](../deploy/env.production.example)）。

API 以 `harness` 运行且无 home：Deploy 安装 Claude Code 时注入稳定 `current` 路径、共享 settings、`CLAUDE_CONFIG_DIR` 与 0600 `.env` 中的 `ANTHROPIC_API_KEY`（见下节），CLI/settings 不再放在 `deploy` home。`HE_AI_AGENT_CLAUDE_BIN` Secret 仅在安装步骤跳过时作手工覆盖；`agent-edit` 需已配置 provider。

## Claude Code

发布流水线在切换 `current` 前安装 Claude Code，并写服务级共享配置：版本目录 + 稳定 `current` 软链、0644 无密钥共享 `settings.json`、0600 `.env` 中的 `ANTHROPIC_API_KEY`。安装包在 runner 侧获取，服务器只解包，不访问 `claude.ai`，不需要 root 或 Node.js；切换前预检服务用户可执行/可读。Secret、MiniMax、验证与回滚见 [Claude Code 运维](claude-code.md)。

## 发布与回滚

- 触发：push main → CI 全绿 → `Deploy`；支持 `workflow_dispatch` 手动触发。
- 行为：[deploy/release.sh](../deploy/release.sh) 校验数据目录 → 安装依赖 → `alembic upgrade head` → 切换 `current` 软链 → `systemctl restart harness-api` → 探活 `/api/health`（最长 60 秒）。
- 回滚：探活失败时先恢复 `.env`，再将软链退回上一 release 并重启；本地保留最近 5 个 release 与 5 份 `.env` 备份。
- 重启排水：unit 用 `KillMode=mixed` + `TimeoutStopSec=45` 先发 SIGTERM；应用在 `HE_JOB_DRAIN_TIMEOUT_SECONDS`（默认 25 秒）内等在跑 job，超时释放租约并标 `interrupted`，下次启动续跑。
- 迁移幂等：连续发布对已应用的迁移零副作用。

## 数据目录与可写校验

生产 `HE_DATA_DIR` 必须是发布目录外的绝对路径，默认 `/var/lib/harness-evolution/data`；`deploy/harness-api.service` 的 `StateDirectory=harness-evolution` 让 systemd 在每次启动时创建并 chown 给 `harness`，bootstrap 也会补建。`release.sh` 在切换 `current` 前校验路径非空、绝对、无空白/换行/`..`、不在 `current` 或 `releases` 下，且目录属主为 `harness:harness` 或已被 unit 的 `StateDirectory=` 覆盖；失败立即退出，当前 release 继续服务。

API 启动时解析绝对路径、`mkdir` 并写探针；不可写时 `/api/health` 返回 503（`data.ok=false`），发布探活失败后回滚。路径变更等于数据迁移：`target-content`、`repos`、`workspaces` 不跟随，需先停服务、迁移目录再改 `vars.HE_DATA_DIR`。首次给已有环境启用 `StateDirectory=` 需以 root 重跑 bootstrap（或安装 unit 后 `daemon-reload`），属于每环境一次的环境初始化，不进日常发布。

## Git 出网代理

生产机访问 GitHub 不稳定时可启用只服务 git 子进程的本机 Xray/VLESS 代理；配置来自 Environment Secret `XRAY_CONFIG`，代理不可用时部署与运行时会自动回退直连。见 [Git 出网代理](git-proxy.md)。

## Git 工作区与推送

run 工作区按目标 ref 建缓存并克隆，推送目标由 provider 自动 fork，`HE_GIT_PUSH_URL` 作为无 token 兜底；缓存、单 ref 克隆、推送凭据策略与逐操作代理可观测性见 [Git 工作区与推送](git-workspace.md)。

## 上游健康与漂移日志

配置 `HE_UPSTREAM_BASE_URL` / `HE_UPSTREAM_TOKEN` 后，pull 输出结构化 `upstream.health` / `version_drift` / `contract_drift` 日志，只含枚举、计数与主版本号，不含正文、会话 id 或凭据。逐会话失败留在 `sync_runs.errors`；调度器只重放 payload，上游抓取失败需用 `POST /api/acquisition/pull` 带 `sessionIds` 重拉。

## 故障排查

- bad case 详情 409/503 表示轨迹未就绪，不是数据丢失；检查轨迹查询配置或补 `sessionSource`。

## 外部表只读权限与契约日志

读路径只需 `bad_cases`、`bad_case_analysis`、`probe_reports` 的 SELECT；上报、目录同步与归因写入还需要 INSERT/UPDATE（不删除外部行）。启动后默认每 5 分钟巡检列与类型契约（`HE_EXTERNAL_CONTRACT_CHECK_INTERVAL_SECONDS` 可调），输出 `external.contract_check`、`external.contract_drift`、`external.row_drift`。读失败返回稳定 503（`EXTERNAL_SCHEMA_DRIFT` / `EXTERNAL_READ_FORBIDDEN` / `EXTERNAL_READ_FAILED`）；`external.read_failed` 只含表名、方言、错误类、驱动码与稳定码，不含 SQL 与参数。
