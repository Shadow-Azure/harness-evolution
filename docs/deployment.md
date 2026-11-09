# 部署

[English](deployment.en.md) | 中文

生产环境是阿里云单实例 SaaS：nginx 托管前端静态产物并把 `/api` 反代到本机 uvicorn（127.0.0.1:8787，systemd 常驻），MySQL 8 与服务同机。发布由 GitHub Actions 完成：push 到 main 且 CI（`ci-ok`）全绿后，`Deploy` workflow 构建前端、rsync 推送 release 到 ECS、执行迁移、原子切换软链并重启服务，探活失败自动回滚。设计依据见 [plans/fullstack-design/01-architecture.md §6](../plans/fullstack-design/01-architecture.md)。

## 云资源

| 资源 | 配置 |
|---|---|
| ECS | 单实例，Ubuntu 22.04/24.04，2核4G（2核2G 需 swap），带宽 ≥3Mbps |
| MySQL 8 | 与服务同机（apt 安装），库 `harness_evolution`，账号 `harness@127.0.0.1` |
| 安全组 | 放行 22/80/443；8787 不对公网开放 |
| 域名 | 可选；未绑域名前用 IP + HTTP 访问，绑域名后补 HTTPS 与 ICP 备案 |

## 服务器目录

| 路径 | 内容 |
|---|---|
| `/opt/harness/releases/<sha>/` | 单次发布（`api/` 源码 + `web/` 静态产物） |
| `/opt/harness/current` | 软链指向当前 release，nginx 与 systemd 的工作目录 |
| `/opt/harness/shared/.env` | 生产 `HE_*` 配置（模板：[deploy/env.production.example](../deploy/env.production.example)） |
| `/opt/harness/shared/venv/` | 共享 Python 虚拟环境 |
| `/opt/harness/shared/config/` | 流水线推送的部署配置（systemd/nginx/release.sh） |

## 首次初始化

初始化由 [deploy/bootstrap-server.sh](../deploy/bootstrap-server.sh) 完成（基础包、Python 3.12、用户、MySQL 建库建号、nginx 与 systemd），逐步操作见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。

## GitHub 配置

| 名称 | 类型 | 内容 |
|---|---|---|
| `ALIYUN_HOST` | Secret | ECS 公网 IP |
| `ALIYUN_USER` | Secret | SSH 用户（`deploy`） |
| `ALIYUN_SSH_KEY` | Secret | deploy 用户 ed25519 私钥 |
| `ALIYUN_SSH_PORT` | Variable | SSH 端口（默认 22） |
| `production` | Environment | 发布 job 的保护环境，可配人工审批 |

私钥只存 GitHub，公钥在服务器 `deploy` 用户 `authorized_keys`；运行密钥只存 `/opt/harness/shared/.env`。

## 发布与回滚

- 触发：push main → CI 全绿 → `Deploy`；支持 `workflow_dispatch` 手动触发。
- 行为：[deploy/release.sh](../deploy/release.sh) 安装依赖 → `alembic upgrade head` → 切换 `current` 软链 → `systemctl restart harness-api` → 探活 `/api/health`（最长 60 秒）。
- 回滚：探活失败时软链退回上一 release 并重启；本地保留最近 5 个 release。
- 迁移幂等：连续发布对已应用的迁移零副作用。
