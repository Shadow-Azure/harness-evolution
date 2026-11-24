# CI 合入门禁：部署 provisioning 契约进入 PR 检查

[English](bugfix-deploy-contract-ci.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-45
milestone: bugfix
depends: [bugfix-33]
priority: P2
status: done
scope:
  - deploy/**
  - apps/api/tests/deploy/**
  - .github/workflows/ci.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 552
  url: https://github.com/Shadow-Azure/harness-evolution/issues/552
```

## 背景

- PR #543 给归因运行时增加 `attribution.preflight`：Linux 上缺 `bubblewrap` 时返回 `ATTRIBUTION_BWRAP_MISSING`，发布在切换 `current` 前失败。该 PR 的 CI 全绿并合入，但下一次 Deploy 在生产机 preflight 阶段失败，旧 release 继续服务。
- 原因是 PR 阶段的 CI 只验证代码行为，没有验证部署 provisioning 契约；Deploy 由 `workflow_run` 在合并后触发，第一次真实环境检查发生在合并之后。#553 已提供幂等的 `deploy/provision-bubblewrap.sh` 与 Provision 入口，但没有把这套契约接进 PR 必过检查。
- 本 issue 只补 CI 门禁：让"新增部署运行时前置、但主机没有可执行 provisioning 路径"的 PR 在合并前失败，而不是等生产 Deploy。

## 目标

- 在干净的 Ubuntu 容器里执行 `deploy-contract`：先验证缺 `bwrap` 的负例，再执行真实的 provision 脚本，最后在服务账号下跑 `bwrap` 命名空间探针与 `attribution.preflight`。
- 让 provisioning 包清单只有一个 source of truth：`deploy/attribution-runtime-prerequisites.list`；bootstrap 读取它，cloud-init 与 Provision 路径与它保持一致，CI 静态断言不一致就失败。
- 静态断言 `deploy/release.sh` 在切换 `current` 前调用 preflight，防止顺序被后续改动挪走。
- 把 `deploy-contract` 纳入 `ci-ok.needs`；分支保护把 `ci-ok` 作为 required check。
- 保持 deploy 无特权：不自动装包、不重试、不跳过或弱化 preflight。

## 设计依据

- [01 §6 部署形态与扩展路径](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md)：单 ECS、release/回滚与部署边界。
- [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)：PR 触发与 `ci-ok` 聚合。
- [`.github/workflows/deploy.yml`](../../../.github/workflows/deploy.yml)：`workflow_run` 合并后发布。
- [`deploy/release.sh`](../../../deploy/release.sh)：preflight 在切换 `current` 前执行。
- [`deploy/provision-bubblewrap.sh`](../../../deploy/provision-bubblewrap.sh)：Provision 与 CI 共用的安装/验证脚本。
- [#552](https://github.com/Shadow-Azure/harness-evolution/issues/552)：缺失门禁的根因分析。

## 实现内容

- `deploy/attribution-runtime-prerequisites.list`：归因运行时 OS 前置清单（当前为 `bubblewrap`），作为 bootstrap 与 cloud-init 的共同来源。
- `deploy/bootstrap-server.sh`：基础包安装改为读取上述清单；缺清单直接失败，不静默跳过。
- `deploy/cloud-init.yaml`：保留创建阶段的包安装；`deploy-contract` 断言清单中的每个包都出现在 cloud-init 的 `packages` 中。
- `apps/api/tests/deploy/test_provisioning_contract.py`：静态契约测试，校验包清单、bootstrap/cloud-init/Provision 一致、`release.sh` preflight 顺序、CI job 接线与 `ci-ok.needs`。
- `apps/api/tests/deploy/verify_provisioning_contract.sh`：干净主机运行时契约：缺 `bwrap` 时 `--check` 以 10 退出并输出 `ATTRIBUTION_BWRAP_MISSING`；创建 `harness` 账号后跑 `--install`，断言 `state=ready`、`bwrap --version`、服务账号命名空间探针退出 0；最后以服务账号执行真实 preflight 并断言 `ready=True`。
- `.github/workflows/ci.yml`：新增 `deploy-contract` job（`ubuntu:24.04` 容器，最小依赖，跑静态测试与干净主机契约），加入 `ci-ok.needs`。
- 文档：部署文档补充 required check、provisioning 契约与新增部署前置的操作顺序；部署手册补充门禁排障。

## 实施步骤

1. 新增运行时前置清单并让 bootstrap 读取；cloud-init 镜像同一清单。
2. 写静态契约测试，先在本机复现"删掉 provisioning 路径即红"。
3. 写干净主机运行时契约脚本，在 Ubuntu 24.04 上实测缺包/安装/probe/preflight 全链路。
4. 在 `ci.yml` 增加 `deploy-contract` job 并纳入 `ci-ok`。
5. 更新部署文档中英两侧与部署手册。
6. 推 PR 验证 CI；故意删除 cloud-init 或 Provision 路径时 `deploy-contract` 失败，恢复后通过。

## 依赖与交付边界

- 依赖：bugfix-33（`deploy/provision-bubblewrap.sh` 与 Provision 入口）；本 issue 不重复实现安装器。
- 交付范围：PR CI job、静态/运行时契约测试、包清单收敛、release 顺序断言、文档与流程。
- 非目标：不自动安装/重试/跳过 preflight；不改 app 代码与归因 sandbox；不给 deploy apt 权限；不改 Deploy 的触发方式。

## 独立验证

```sh
apps/api/.venv/bin/python -m pytest apps/api/tests/deploy/test_provisioning_contract.py -q
sudo bash apps/api/tests/deploy/verify_provisioning_contract.sh
pnpm verify:flow
pnpm test:gates
pnpm lint:docs
pnpm verify:docs
bash -n deploy/provision-bubblewrap.sh deploy/bootstrap-server.sh apps/api/tests/deploy/verify_provisioning_contract.sh
```

- 干净容器中没有 `bwrap` 时，负例退出 10 且输出 `ATTRIBUTION_BWRAP_MISSING`。
- 安装后 `bwrap --version`、服务账号探针与 `python -m app.third_party_api.ai_agent.preflight` 均成功，preflight 输出 `ready=True`。
- 故意从 cloud-init 或 bootstrap 移除 `bubblewrap` 时静态契约测试失败；恢复后通过。

## 验收标准

- PR 新增/修改部署运行时前置但没有可执行 provisioning 路径时，`deploy-contract` 必过检查失败。
- `deploy-contract` 在干净容器中真实执行负例、provision 正例和服务账号 preflight，不使用 mock `bwrap`。
- `ci-ok` 包含 `deploy-contract`；分支保护仍以 `ci-ok` 为 required check。
- 包清单单一来源；bootstrap、cloud-init、Provision 脚本一致。
- deploy 仍无特权，没有自动安装、重试或跳过 preflight 的兜底。
- 文档、流程与门禁全绿。

## 门禁与 CI

- `deploy-contract`：干净 `ubuntu:24.04` 容器执行运行时契约与静态契约测试，纳入 `ci-ok.needs`。
- `pnpm verify:flow`、`pnpm test:gates`、`pnpm verify:flow-online`：流程与 PR 关联。
- `pnpm lint:docs`、`pnpm verify:docs`：部署文档与中英配对。
- `bash -n` 与 shellcheck（若可用）：部署脚本语法。

## 非目标

- 不做黄金镜像/Packer、MySQL 拆分或容器化部署。
- 不改 `ATTRIBUTION_BWRAP_*` 错误码语义，不改归因 sandbox。
- 不把 apt 权限交给 deploy 用户，不在 `release.sh` 里安装系统包。
- 不写入生产凭据、Session 内容或主机地址。
