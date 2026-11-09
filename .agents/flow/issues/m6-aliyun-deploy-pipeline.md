# GitHub Actions 自动部署前后端到阿里云 ECS

[English](m6-aliyun-deploy-pipeline.en.md) | 中文

```yaml flow
kind: issue
id: m6-22
milestone: m6
depends:
  - m6-09
priority: P1
status: backlog
scope:
  - .github/workflows/**
  - deploy/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 198
  url: https://github.com/Shadow-Azure/harness-evolution/issues/198
```

## 背景

服务目前只能在本机 `pnpm dev` 运行，CI 只有 PR 门禁与 main push 的质量 lane（`ci-ok`），没有任何交付通道；设计文档 §6 已定义"单实例 SaaS + uvicorn 8787 + MySQL 8 主库 + nginx 托管静态前端"的部署形态，但从未落地。要把演示与试用环境放到阿里云公网，需要一条 push main 全绿后自动发布的前后端流水线，且过程不再依赖人工 SSH。

## 目标

- push 到 main 且 `ci-ok` 全绿后，GitHub Actions 自动完成：构建 `apps/web` 产物 → rsync 推送到 ECS → 执行 Alembic 迁移 → 重启 systemd 服务 → 健康检查，失败自动回滚上一版本。
- 服务器侧配置模板入库（systemd unit、nginx 站点、远程部署脚本、`.env` 示例），任何一台新 ECS 按文档可复现初始化。
- 密钥只存两处：GitHub Actions Secrets（SSH 私钥）与服务器本地 `.env`（`HE_*`）；仓库不出现任何真实凭据。

## 设计依据

- [plans/fullstack-design/01-architecture.md §6 部署形态与扩展路径](../../../plans/fullstack-design/01-architecture.md)：单实例 SaaS、`uvicorn app.main:app --host 0.0.0.0 --port 8787`、静态前端由 nginx 托管、CORS 配正式域名——本 issue 的目标形态即该章节"现在"列，不启用任何"扩展路径"项。
- [plans/fullstack-design/04-backend-architecture.md](../../../plans/fullstack-design/04-backend-architecture.md)：MySQL 8 是生产主库、SQLite 仅测试；`HE_DB_DIALECT`/`HE_DB_URL` 是方言切换的环境面。
- 实现与上述章节冲突时，以链接章节为准；本 issue 只做交付通道，不改变任何应用行为。

## 实现内容

- `.github/workflows/deploy.yml`：`workflow_run` 监听 CI 成功（或复用 `ci-ok` 聚合判定）后触发；job 构建前端产物，经 SSH 密钥 rsync 推送 release 目录，远程执行部署脚本，全程使用 `environment: production` 保护。
- `deploy/harness-api.service`：uvicorn 常驻 systemd unit（`apps/api/.venv/bin/python -m app`，EnvironmentFile 指向 `/opt/harness/shared/.env`）。
- `deploy/nginx-harness.conf`：静态托管 `current` 软链指向的 dist，`/api` 反代 `127.0.0.1:8787`，SSE location 关闭缓冲。
- `deploy/release.sh`：服务器端脚本——安装/更新 API 依赖、`alembic -x sqlalchemy.url="$HE_DB_URL" upgrade head`、切换软链、重启服务、`curl /health` 探活、失败回滚。
- `deploy/env.production.example`：生产 `HE_*` 环境面清单（`HE_JWT_SECRET`、`HE_DB_URL`、`HE_CORS_ORIGINS`、`HE_ADMIN_USERNAME`/`HE_ADMIN_PASSWORD` 等），值留空。
- `docs/deployment.md`（+英文侧）：阿里云资源清单（ECS/RDS/安全组/域名备案/证书）、GitHub Secrets 配置、首次初始化与回滚操作手册。

## 实施步骤

1. 阿里云侧资源准备（ECS、RDS MySQL、安全组、域名与证书），按 `docs/deployment.md` 清单执行。
2. 服务器初始化：Python 3.12、nginx、`deploy` 用户与 SSH 公钥、`/opt/harness/{releases,shared,current}` 目录与 `.env`。
3. GitHub 仓库配置 Secrets（主机、用户、私钥、端口）与 `production` environment 审批。
4. 编写 `deploy.yml` 与 `deploy/` 模板、中英部署文档。
5. 手动触发首次发布验证全链路，演练一次失败回滚。

## 依赖与交付边界

- 依赖：m6-09（CI lane 拆分与 `ci-ok` 聚合 gate，deploy 挂在它之后）。
- 交付边界：只新增流水线、服务器配置模板与文档；不改 `apps/`、`packages/` 任何代码与契约。
- 非目标：见下方专节。

## 独立验证

```sh
pnpm verify:flow
pnpm verify:docs
```

- `verify:flow` 报全部 lane 通过；`verify:docs` 报文档门禁通过（新文档预算已登记）。
- 部署通道级验证（在阿里云资源就绪后）：push main → Actions 页 `deploy` workflow 全绿；服务器 `curl -sf http://127.0.0.1:8787/health` 返回 200 且含 `phase` 字段；浏览器访问 `https://<域名>` 能登录并浏览 Session。

## 验收标准

- push main 后从合并到新版本可访问，全程零人工 SSH。
- 健康检查失败时自动回滚到上一 release，接口不可用窗口小于一分钟。
- 公网仅暴露 80/443；8787 只监听本机回环访问路径（经 nginx 反代）。
- 迁移幂等：连续两次部署不产生重复变更或失败。
- 新 ECS 按文档从零复现初始化成功。

## 门禁与 CI

- `verify:flow --diff`：PR 与提交标题带 `(#N)`，diff 落在登记 scope 内。
- `verify:docs`：新增部署文档登记词数预算，双语成对。
- `deploy.yml` 不在 PR lane 内执行（仅 main push 后由 CI 成功触发）；其 yml 语法在实施时以本地 `node --check` 等价物与首次真实运行验证。

## 非目标

- 不做 Docker 镜像化与 ACR（镜像仓库是后续演进，§6 扩展路径之外）。
- 不做多实例水平扩展、CDN、Redis pub/sub SSE 总线。
- 不做 HTTPS 证书自动续期（首次手动部署阿里云免费证书，续期写入文档）。
- 不改应用代码、契约与门禁脚本。
