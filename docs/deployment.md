# 部署

[English](deployment.en.md) | 中文

阿里云单机部署 nginx、uvicorn（127.0.0.1:8787）和 MySQL 8。nginx 托管前端并反代 `/api`。设计依据见 [plans/fullstack-design/01-architecture.md §6](../plans/fullstack-design/01-architecture.md)。

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
| `/opt/harness/shared/.env` | 生产 `HE_*` 配置（模板：[.env.example](../.env.example)） |
| `/opt/harness/shared/venv/` | 共享 Python 虚拟环境 |
| `/opt/harness/shared/config/` | 流水线推送的部署配置（systemd/nginx/release.sh） |
| `/var/lib/harness-evolution/` | 服务端数据目录，systemd `StateDirectory=` 创建并授权给 `harness`；`HE_DATA_DIR` 指向其下 |

## 首次初始化

初始化由 [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) 完成（基础包、Python 3.12、用户、MySQL、nginx、systemd），逐步操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。

## Provision 入口

使用默认 Linux 归因沙箱的主机可在 `main` 手动运行 [Provision workflow](../.github/workflows/provision.yml) 的 `check`、`install` 或 `dry-run`。它使用 `production` 环境的专用 `PROVISION_SSH_KEY` 和可选用户 `PROVISION_SSH_USER`（默认 `root`）。[安装脚本](../deploy/provision-bubblewrap.sh) 按需装包并以 `harness` 运行命名空间探针。Ubuntu 24.04 的 AppArmor profile `/etc/apparmor.d/bwrap-userns-restrict` 只放行 bwrap。日常发布使用 `deploy` 账号。凭据轮换见[部署手册](../plans/deploy-aliyun-playbook.md#4-github-仓库配置网页粘贴)。

## 新机 cloud-init

新建 ECS 时用 [deploy/cloud-init.yaml](../deploy/cloud-init.yaml) 在创建阶段安装运行时前置；Ubuntu 24.04 仍需在创建后跑一次 Provision `install` 应用 profile。运行时前置以 [attribution-runtime-prerequisites.list](../deploy/attribution-runtime-prerequisites.list) 为准，bootstrap 读取它安装，cloud-init 镜像同一清单。

## CI 门禁：部署 provisioning 契约

`deploy-contract` 在干净的 Ubuntu 24.04 上执行[部署验收脚本](../apps/api/tests/deploy/verify_provisioning_contract.sh)。缺少 bwrap 时，未配置和显式开启均返回 `ATTRIBUTION_BWRAP_MISSING`，显式关闭后预检通过。Provision 安装后，`harness` 的命名空间探针和沙箱预检均须通过。[API 测试](../apps/api/tests/deploy/test_provisioning_contract.py)核对 bootstrap 和 cloud-init 的包清单、Provision 安装步骤及发布预检顺序。分支保护通过 `ci-ok` 汇总此门禁。扩展清单和排障见[部署手册](../plans/deploy-aliyun-playbook.md#6-常见问题)。

## GitHub 配置

| 名称 | 类型 | 内容 |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS 公网 IP |
| `ALIYUN_USER` | Secret | SSH 用户（`deploy`） |
| `ALIYUN_SSH_KEY` | Secret | deploy 用户 ed25519 私钥 |
| `ALIYUN_SSH_PORT` | Variable | SSH 端口（默认 22） |
| `PROVISION_SSH_KEY` | Environment Secret | `production` 环境专用 root 私钥；读取面见部署手册 |
| `PROVISION_SSH_USER` | Variable | 可选，Provision 的 SSH 用户（默认 `root`，必须是 root） |
| `HE_DATA_DIR` | Variable | 数据目录绝对路径；留空用 `/var/lib/harness-evolution/data` |
| `XRAY_CONFIG` | Environment Secret | 可选：完整 Xray JSON（VLESS 出站 + 回环 mixed 入站），见 [Git 出网代理](git-proxy.md) |
| `production` | Environment | 发布 job 的保护环境，可配人工审批 |

私钥只存 GitHub，公钥在服务器 `deploy` 的 `authorized_keys`；运行密钥只存 `/opt/harness/shared/.env`，代理配置只存服务器 `0600` 文件。

## 配置注入

Deploy 将 `vars.HE_DATA_DIR` 和评测 Secrets（`HE_EVAL_MODE`/`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY`）注入 `.env`；三个评测键存在且非空时写入，缺失时显式移除旧值；`apiKeyRef` 只存变量名。`HE_GIT_PUSH_PROVIDER` 总是写入，`HE_GIT_PUSH_TOKEN` 为空时移除旧键，`GIT_ASKPASS` 指向 `/opt/harness/shared/git-askpass.sh`。值经 base64 传输、`inject-config.py` 原子写入并保持 `.env` 0600，注入前备份 `.env.bak.<sha>`；解码失败告警跳过并保留旧值，写盘失败中止发布。操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)，模板见 [.env.example](../.env.example)。

### AI Agent 配置

模型审查与 patch 生成经 Secrets 注入 `AI_AGENT_PROVIDER`、`HE_AI_AGENT_FAILURE_POLICY`、`HE_PATCH_SOURCE_MODE`：非空写入 `.env`，缺失或空显式 `--unset`。`HE_AI_AGENT_FAILURE_POLICY` 留空按 provider 推导（`fake` → `degrade`，其余 → `strict`）；`strict` 下聚类 AI 失败让 run 在聚类阶段显式失败。值含换行/回车时注入前失败，其余解码失败告警跳过并保留旧值（默认值与合法值见[模板](../.env.example)）。

`agent-edit` 需配置 Provider。API 以无 home 的 `harness` 读取共享 settings 和 `CLAUDE_CONFIG_DIR`。自带 CLI 可用 `HE_AI_AGENT_CLAUDE_BIN` 指定。

### 归因运行时

绑定归因与向导重算共用 Provider 和模型。Linux 默认在 [bubblewrap 沙箱](deployment.md#provision-入口)执行 Skill，缺包或探针失败时保留待领取批次。仅在 `/opt/harness/shared/.env` 显式设置 `HE_ATTRIBUTION_BWRAP_ENABLED=false` 时，改用本条证据工具和平台报告脚本。发布在迁移前预检，API 启动复检。修改配置后重启 API，原绑定自动续跑。可用 `journalctl -u harness-api -g attribution.preflight` 核对 `bwrap_enabled` 和 `ready`。见[归因验收](../plans/deploy-aliyun-playbook.md#验证-skill-归因)。

## Claude Code

发布流水线在切换 `current` 前安装 Claude Code，并写服务级共享配置：版本目录 + 稳定 `current` 软链、0644 无密钥共享 `settings.json`、0600 `.env` 中的 `ANTHROPIC_API_KEY`。安装包在 runner 侧获取，服务器只解包，不访问 `claude.ai`，不需要 root 或 Node.js；切换前预检服务用户可执行/可读。Secret、MiniMax、验证与回滚见 [Claude Code 运维](claude-code.md)。

## 发布与回滚

- 触发：push main → CI 全绿 → `Deploy`；支持 `workflow_dispatch` 手动触发。
- 行为：[deploy/release.sh](../deploy/release.sh) 校验数据目录 → 安装依赖 → 归因预检 → `alembic upgrade head` → 切换 `current` 软链 → `systemctl restart harness-api` → 探活 `/api/health`（最长 60 秒）。
- 回滚：探活失败时先恢复 `.env`，再将软链退回上一 release 并重启；本地保留最近 5 个 release 与 5 份 `.env` 备份。
- 重启排水：unit 用 `KillMode=mixed` + `TimeoutStopSec=45` 先发 SIGTERM；应用在 `HE_JOB_DRAIN_TIMEOUT_SECONDS`（默认 25 秒）内等在跑 job，超时释放租约并标 `interrupted`。下次启动重新入队 evolution job 并写 `job_recovered`，attribution batch 原地回队列，两者从检查点继续；崩溃遗留的 `running` 行也先标 `interrupted` 再走同一恢复。
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
