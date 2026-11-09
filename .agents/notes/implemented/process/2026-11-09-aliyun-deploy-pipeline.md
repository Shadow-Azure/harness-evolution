# Agent Note: 阿里云单机直部署交付通道

Status: implemented

[English](2026-11-09-aliyun-deploy-pipeline.en.md) | 中文

## Problem

服务长期只有本地 `pnpm dev` 入口，CI 只有质量门禁没有交付通道；演示与试用环境需要落到阿里云公网。约束条件：单人维护、国内 ECS 直连 GitHub 不稳定、预算敏感、设计文档 §6 已锁定单实例 SaaS 形态（uvicorn 8787、MySQL 8 主库、nginx 托管静态、自建账号 JWT）。

## Decision

交付通道采用 CI 构建 + rsync 直推的裸机部署：GitHub Actions 在 CI（`ci-ok`）全绿后经 SSH 密钥把前端产物与 API 源码推到 ECS release 目录，服务器端 `deploy/release.sh` 完成依赖安装、Alembic 迁移（发布时向 `alembic.ini` 副本注入 `HE_DB_URL`，仓库内 ini 保持空值）、`current` 软链原子切换、systemd 重启与 `/api/health` 探活，探活失败自动回滚上一 release。MySQL 自建于同一 ECS（bootstrap 脚本建库建号），认证用 GitHub Actions Secrets 存 deploy 用户 ed25519 私钥，deploy 用户 sudoers 收敛到 `systemctl restart/start harness-api`。服务以 `harness` 系统用户运行，uvicorn 只绑 127.0.0.1，公网入口仅 nginx 80/443。

## Alternatives considered

- Docker 镜像 + ACR：可复现性最好，但引入镜像仓库、Dockerfile 与镜像版管理，起步阶段维护成本高于收益，留作扩展路径。
- 服务器 git pull：国内 ECS 连 GitHub 慢且不稳，且把构建环节暴露在服务器上；改为 CI 构建产物直推。
- OSS 中转产物：多一跳配置与凭证，单机场景 rsync over SSH 更简单直接。
- RDS MySQL：免运维但月费固定；单人演示期自建同机 MySQL，迁移成本低（`HE_DB_URL` 一处切换）。

## Consequences

- 回滚语义是软链退回 + 重启，接口不可用窗口 <1 分钟；迁移前滚不自动处理（Alembic downgrade 不在自动流程内）。
- 单机无水平扩展：SSE 内存总线、进程内 worker 都依赖单实例，扩容需按 §6 扩展路径另行立项。
- HTTPS 证书手动安装与续期（未绑域名前无 TLS）；备案后补证书再收窄到 443。
- deploy 用户私钥泄露即等于生产权限，Secrets 轮换与 `production` 环境审批是唯一额外护栏。
