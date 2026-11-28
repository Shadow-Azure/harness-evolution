# 生产 .env.example 逐行标注必填/选填并收敛单一模板

[English](bugfix-30-env-example-required-first.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-30
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - .env.example
  - .gitignore
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - deploy/**
  - plans/deploy-aliyun-playbook.md
  - plans/2026-11-23-pr530-review.md
  - .agents/**
adr:
  - ../../notes/implemented/process/2026-11-23-env-example-single-template.md
github:
  number: 529
  url: https://github.com/Shadow-Azure/harness-evolution/issues/529
```

## 背景

生产 `.env` 由 systemd 的 `EnvironmentFile=` 读取，缺少必填项会让服务启动失败，或让首次部署没有可登录的管理员。现有 `deploy/env.production.example` 按网络、数据、Git 等领域分组，必填与选填混排，操作者必须对照 `apps/api/app/config.py` 才能判断哪些不能留空。用户要求一份必填在前、逐行说明填写内容与作用的 `.env.example`。systemd 不支持变量行尾注释，所以说明必须独立成行，否则注释会成为值的一部分。

## 目标

- 在仓库根新增 `.env.example`，作为生产 `.env` 的唯一模板；必填字段在前，选填字段在后。
- 必填项保持为生效的赋值行；选填项默认在行首加 `#` 注释，按需取消注释。每个变量下一行用 `# 必填｜...` 或 `# 选填｜...` 说明填写内容、作用、默认值与约束。
- 移除 `deploy/env.production.example`，把部署文档、bootstrap 与 playbook 的指引收敛到新模板。
- `.gitignore` 放行根 `.env.example`，继续忽略真实 `.env`。

## 设计依据

- `apps/api/app/config.py`：`Settings` 字段、默认值、生产模式校验与启动校验。
- [deploy/harness-api.service](../../../deploy/harness-api.service)：生产进程通过 `EnvironmentFile=/opt/harness/shared/.env` 读取配置。
- [docs/deployment.md](../../../docs/deployment.md)：生产目录、配置注入与发布流程的现状说明。
- [plans/fullstack-design/01-architecture.md](../../../plans/fullstack-design/01-architecture.md)：单实例生产架构。

## 实现内容

- `.env.example`：必填段包含 `HE_PRODUCTION`、`HE_HOST`、`HE_DATA_DIR`、`HE_JWT_SECRET`、`HE_DB_URL`、`HE_ADMIN_USERNAME`、`HE_ADMIN_PASSWORD`；随后按鉴权、数据库调优、上游、Git、AI Agent、评测等分组列出选填项。必填项保持为赋值行，选填项默认注释；每个变量下一行是必填/选填说明。
- 删除 `deploy/env.production.example`，更新 `docs/deployment.md` / `.en.md`、`deploy/bootstrap-server.sh` 与 `plans/deploy-aliyun-playbook.md` 中的模板路径。
- `.gitignore` 增加 `!.env.example` 例外。
- 新增 Agent Note，记录单一模板与独立注释行的决定。

## 实施步骤

1. 从 `deploy/env.production.example` 迁移字段并按必填/选填重排，补全逐行说明。
2. 删除旧模板并更新文档、bootstrap 与 playbook 的路径。
3. 放行 `.gitignore` 中的根 `.env.example`。
4. 补 Agent Note，重录文档双语配对。
5. 跑文档、流程与门禁自测试。

## 依赖与交付边界

- 依赖：无。
- 交付边界：只改模板、文档与流程记录；不改 `Settings` 字段、默认值或部署注入逻辑；不写真实密钥；不新增环境变量。

## 独立验证

```sh
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
awk '/^[A-Z][A-Z0-9_]*=/{key=$0; getline; if ($0 !~ /^# (必填|选填)｜/) { print "missing annotation: " key; bad=1 }} END { exit bad }' .env.example
grep -c '^# [A-Z][A-Z0-9_]*=' .env.example
```

- 四个门禁全绿。
- `awk` 无输出，说明每个生效的必填赋值行后面都有一条必填说明；`grep` 输出 90，说明 90 个选填项默认被注释。
- `.env.example` 的必填段在选填段之前，且不存在 `KEY=value # 注释` 形式的行尾注释。

## 验收标准

- 仓库根存在 `.env.example`；必填字段全部在选填字段之前。
- 每个变量下一行标明 `必填` 或 `选填`，并说明要填什么、起什么作用；必填项保持生效，选填项默认以 `#` 注释、取消注释后才生效；必填项的空值会触发启动失败或首次部署无管理员。
- `deploy/env.production.example` 不再存在；`docs/deployment.md` / `.en.md`、bootstrap 与 playbook 的模板链接可达。
- 真实 `.env` 仍被 git 忽略，`.env.example` 可提交。
- CI 全绿。

## 门禁与 CI

- `pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`、`pnpm test:gates`。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不改 `Settings` 字段、默认值、启动校验或部署注入逻辑。
- 不提供本地开发用的 SQLite 模板，不写任何真实凭据。
- 不为历史 `plans/` 检视记录回填旧路径。
- 不新增环境变量或调整部署流水线。
