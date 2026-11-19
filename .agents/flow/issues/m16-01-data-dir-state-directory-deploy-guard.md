# 生产数据目录 StateDirectory 与部署可写校验

[English](m16-01-data-dir-state-directory-deploy-guard.en.md) | 中文

```yaml flow
kind: issue
id: m16-01
milestone: m16
depends: []
priority: P1
status: done
scope:
  - deploy/**
  - .github/workflows/deploy.yml
  - apps/api/**
  - packages/contracts/**
  - docs/**
  - README.md
  - README.en.md
  - README.i18n.yaml
  - scripts/doc-budgets.manifest.json
  - .agents/**
  - plans/**
adr: []
github:
  number: 386
  url: https://github.com/Shadow-Azure/harness-evolution/issues/386
```

## 背景

生产「启动自进化」在读取 `SKILL.md` 前会创建 `data_dir/target-content` 缓存目录；`HE_DATA_DIR` 未配置时 `data_dir` 默认 `data`，相对 systemd 的 `WorkingDirectory=/opt/harness/current/api` 解析到发布目录，`harness` 服务用户不可写，`mkdir` 抛 `OSError` 后被统一映射为 `content_unavailable`。生产因此无法解析 skill 版本，启动向导卡在第一步。问题与完整证据见 [issue #385](https://github.com/Shadow-Azure/harness-evolution/issues/385)。

## 目标

- 生产数据目录由 systemd `StateDirectory=` 创建并授权给 `harness`，发布目录只读、可被整体替换。
- 发布流水线从 GitHub Environment `vars.HE_DATA_DIR` 注入绝对路径，空值回退到 `/var/lib/harness-evolution/data`。
- `release.sh` 在切换 `current` 之前做静态校验；失败不切换、不重启，并恢复注入前的 `.env`。
- API 启动时解析绝对路径、创建目录并写探针；`/api/health` 暴露 `data.ok`，不可写时返回 503 触发发布回滚。
- 本地开发继续默认 `./data`，行为不变。

## 设计依据

- [01 §6 部署形态与扩展路径](../../../plans/fullstack-design/01-architecture.md#6-部署形态与扩展路径)：单实例 SaaS 的进程、目录与发布边界。
- [04 §9 配置项清单](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单)：`HE_DATA_DIR` 的配置语义。
- [07 §9 横切实现](../../../plans/fullstack-design/07-backend-implementation.md#9-横切实现)：数据目录必须存在且可写，启动时创建。
- [issue #385](https://github.com/Shadow-Azure/harness-evolution/issues/385)：现象、根因与方案 A 的 Definition of Done。

## 实现内容

**部署单元与初始化**

- `deploy/harness-api.service` 增加 `StateDirectory=harness-evolution`；systemd 启动时创建 `/var/lib/harness-evolution` 并 chown 给 `harness`。
- `deploy/bootstrap-server.sh` 改为幂等安装/更新 unit（`install` + `daemon-reload` + `enable`），并以 root 补建 `/var/lib/harness-evolution`，首次初始化后即可由服务写入。

**配置注入**

- 将 `deploy/inject-eval-config.py` 泛化为 `deploy/inject-config.py`：接受任意 `KEY <base64>` 行，增加 `--backup <path>` 在原子重写前备份 `.env`。
- `deploy.yml` 取 `vars.HE_DATA_DIR`，空值使用绝对默认路径；与评测配置一起注入，注入前备份到 `/opt/harness/shared/.env.bak.<sha>`。

**部署前校验与回滚**

- `release.sh` 在切换 `current` 前校验：`HE_DATA_DIR` 非空、绝对路径、无空白/换行、不含 `..`、不在 `/opt/harness/current` 或 `/opt/harness/releases` 下、目录已存在且属主可写，或被 unit 的 `StateDirectory=` 覆盖。
- 校验失败输出路径与原因并退出，不切换 `current`；任何失败路径恢复注入前 `.env`。
- health 失败回滚上一 release 前先恢复 `.env` 再重启，避免坏值残留。

**API 与契约**

- `app/config.py`：production 下 `data_dir` 必须是绝对路径，否则配置校验失败。
- 新增数据目录探针：解析绝对路径、`mkdir(parents=True, exist_ok=True)`、创建并删除写探针，记录最终路径与失败原因（不暴露给 HTTP）。
- `/api/health` 增加 `data: {ok: bool}`；`data.ok` 或 `db.ok` 为 false 时返回 503；同步 `HealthResponse` 契约与生成类型。

**文档**

- `README.md` / `README.en.md` 增加「生产部署前置」；`docs/deployment.md` / `.en.md` 增加数据目录、StateDirectory、路径约束与迁移步骤；`deploy/env.production.example` 增加 `HE_DATA_DIR` 模板。

## 实施步骤

1. 更新 unit、bootstrap 与 deploy workflow，泛化配置注入器并接入 `vars.HE_DATA_DIR`。
2. 给 `release.sh` 增加路径校验、`.env` 备份恢复与回滚顺序。
3. 实现 API 数据目录解析、启动写探针、production 绝对路径校验与 health `data.ok`。
4. 重新生成 contracts，补单测与配置错误演练。
5. 更新双语文档、env 模板与 Agent Note，重录配对记录。
6. 跑聚焦测试与门禁，提交 PR，按 CI 结果修复。

## 依赖与交付边界

- 依赖：无。方案 A 的一次性 root 动作由更新后的 bootstrap 完成，日常发布不需要 root。
- 非目标：不引入 root helper 或扩大 deploy sudo；不把 unit 安装放进日常发布；不改 body-hash 与 target revision 解析；不提供数据迁移工具；不改前端 UI。

## 独立验证

```sh
pnpm test:api
pnpm contract:check
pnpm lint:docs
pnpm verify:flow
bash -n deploy/bootstrap-server.sh deploy/release.sh
```

- production + 相对 `HE_DATA_DIR` 在配置校验阶段失败，错误信息包含路径语义。
- 目录不可写时 `/api/health` 返回 503 且 `data.ok=false`；可写时 200。
- `HE_DATA_DIR` 为相对路径、发布目录内路径或未授权路径时，`release.sh` 在切换 `current` 前退出。
- 契约快照与生成类型包含 `data.ok`，`contract:check` 无漂移。

## 验收标准

- 错误配置在部署阶段失败，错误信息包含具体路径/原因，当前 release 不受影响。
- health 能反映 data 目录可写性；不可写时发布回滚且 `.env` 恢复。
- 合法配置下目录由 systemd/bootstrap 创建并授权，向导解析 `v7.0.2` 不再出现 `content_unavailable`。
- 本地开发默认 `./data` 行为不变；测试覆盖相对路径、发布目录路径与不可写目录。
- 文档与 env 模板同步，双语文档通过配对门禁。

## 门禁与 CI

- `pnpm test:api`、`pnpm contract:check`、`pnpm lint:docs`、`pnpm verify:flow`、`pnpm verify:flow-online`。
- 新增测试覆盖 production 路径校验、探针可写/不可写、health 503。
- PR 标题与提交标题引用本 issue 的 GitHub 编号。

## 非目标

- 不解决 #382 的版本选择 UI 问题。
- 不迁移已有 `target-content`/`repos`/`workspaces` 数据；路径变更按文档提示需要人工迁移。
- 不把路径写入 secrets，不暴露数据目录绝对路径与错误细节给未鉴权 HTTP 响应。
