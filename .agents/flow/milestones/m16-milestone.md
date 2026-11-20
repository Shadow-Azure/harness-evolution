# M16 生产数据目录与部署可写性

[English](m16-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m16
title: M16 生产数据目录与部署可写性
status: done
github:
  number: 24
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/24
```

## 目标

让生产数据目录由 systemd `StateDirectory=` 创建并授权，发布流水线注入绝对 `HE_DATA_DIR`，`release.sh` 在切换 `current` 前校验路径，API 启动做写探针并把结果暴露到 `/api/health`。日常发布不再需要登录服务器或手工 `mkdir`。

## 范围

`deploy/` 的 unit、bootstrap、release 脚本与配置注入器，`.github/workflows/deploy.yml`，API 的 `data_dir` 解析、启动写探针与 health 契约，`docs/deployment.*`、README 的生产前置说明，以及对应的 Agent Note 与流程文件。

## 验收

- unit 含 `StateDirectory=harness-evolution`，bootstrap 幂等安装或更新 unit 并 `daemon-reload`；`/var/lib/harness-evolution` 属主为 `harness`。
- GitHub Environment 的 `vars.HE_DATA_DIR` 为空时使用绝对默认路径；相对路径、发布目录内路径、未授权路径在部署前被拒绝，`current` 不变。
- API 启动解析绝对路径、创建目录并写探针；不可写时 `/api/health` 返回 503，发布探活失败回滚并恢复 `.env`。
- 本地开发默认 `./data` 行为不变；测试覆盖相对路径、发布目录路径与不可写目录。
- 双语部署文档、env 模板与 README 生产前置章节同步。

## 非目标

不引入 root helper 或扩大 deploy 的 sudo 权限，不把 unit 安装放进日常发布，不改 body-hash 与 target revision 解析，不提供数据迁移工具，不改前端 UI。
