# 部署流水线 provisioning 闭环：bubblewrap 与独立 Provision 入口

[English](bugfix-provision-bubblewrap.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-33
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - deploy/**
  - .github/workflows/provision.yml
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 553
  url: https://github.com/Shadow-Azure/harness-evolution/issues/553
```

## 背景

- 归因本地 Agent（`local-agent-skill-v1`）在 Linux 上用 bubblewrap（`bwrap`）给每次 Claude Skill 执行建立文件系统沙箱：只读系统路径 + 唯一可写 attempt 目录，保护宿主机 `.env`、数据库凭据和其他 case/workspace。实现见 `apps/api/app/third_party_api/ai_agent/claude_skill.py`。
- PR #421 引入归因 Skill 执行与 bwrap 沙箱，并把 `bubblewrap` 加入 `deploy/bootstrap-server.sh` 的基础包列表；PR #543 增加 `attribution.preflight`，缺 bwrap 时返回 `ATTRIBUTION_BWRAP_MISSING`，发布在切换 `current` 前失败并恢复 `.env`。
- 存量生产机在 bootstrap 增加 `bubblewrap` 之前初始化，没有安装这个包；最近的 Deploy 因此被 preflight 拦下，旧 release 继续服务。新机器通过 bootstrap 会带上，但存量机仍需要一次性 root 安装。
- 当前 Deploy 以 `deploy` 用户运行，sudoers 只允许 `systemctl restart/start harness-api` 与 `harness-proxy`；不能在 app deploy 中执行 `apt-get`。给 deploy 加 apt 权限接近 root（apt 维护者脚本/hook 以 root 执行），不可接受。
- 需要把 OS 包 provisioning 做成受控、可审计、可重复的流水线能力；日常 deploy 保持无特权，preflight 保留为门禁。

## 目标

- 存量机：提供独立 Provision 入口，幂等安装并验证 `bubblewrap`；不需要人工 SSH 装包。
- 新机：cloud-init 或 Ansible 在机器创建时安装；`bootstrap-server.sh` 继续作为包列表的 source of truth。
- 发布：`attribution.preflight` 保留；缺 bwrap 仍 fail-closed；不把 apt 权限给 deploy。
- 可观测：Provision 日志、preflight 错误码、失败跳转/runbook；能区分 `ATTRIBUTION_BWRAP_MISSING` 与 `ATTRIBUTION_BWRAP_UNUSABLE`。
- 安全：专用特权账号/云 API + production environment 审批；root-owned wrapper；密钥不进仓库/日志；可轮换、可审计。
- 可选：一条 Deploy workflow 通过 `provision` job + `needs` 闭环；默认推荐独立 Provision 入口，避免每次发布携带 root。

## 设计依据

- [01 §6 部署形态与扩展路径](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md)：单 ECS、release/软链/回滚与部署边界。
- [docs/deployment.md](../../../docs/deployment.md)：单实例、deploy 用户、发布与回滚、bootstrap 路径。
- [PR #421](https://github.com/Shadow-Azure/harness-evolution/pull/421)：归因 Skill 执行与 bwrap 沙箱，`bubblewrap` 进入 bootstrap。
- [PR #543](https://github.com/Shadow-Azure/harness-evolution/pull/543)：`attribution.preflight`、稳定错误码与发布前检查。
- [归因 Agent 执行器 Note](../../../.agents/notes/implemented/architecture/2026-11-17-attribution-agent-executor.md)：逐次文件系统沙箱、信任边界与出站限制。
- [归因运行时问题记录](../../../.agents/flow/issues/bugfix-attribution-runtime-silent-hang.md)：存量机缺 bwrap、绑定保留与恢复。

## 实现内容

- **Provision 脚本**：新增 `deploy/provision-bubblewrap.sh`（root 执行，幂等）。先 `command -v bwrap`；已存在则跑 `bwrap --version` 和 namespace probe；缺失才 `apt-get update && apt-get install -y bubblewrap`；最后以 `harness` 身份跑 `bwrap --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true`；支持 `--check` / `--dry-run`；日志不含凭据。
- **Provision workflow**：新增 `.github/workflows/provision.yml`，`workflow_dispatch`，`environment: production`（人工审批），使用专用特权账号（root SSH key 或 `provision` 用户 + root-owned wrapper）或阿里云 Cloud Assistant/OOS + RAM 角色；SSH 执行脚本；输出摘要；失败非零退出。
- **新机 provisioning**：新增 `deploy/cloud-init.yaml`（`packages: [bubblewrap]`）或 Ansible base role；文档说明新机创建路径；bootstrap 保持包列表一致。
- **Deploy 接线**：保留 `release.sh` 的 preflight；提供可选 `provision` job + `deploy needs: provision` 的示例（不默认启用），或文档规定 Deploy 前先跑 Provision；不修改 deploy 的 sudoers。
- **错误 UX**：把 `ATTRIBUTION_BWRAP_MISSING` / `UNUSABLE` 映射到 Provision workflow/runbook；Deploy summary 给出下一步链接。
- **测试**：脚本 `bash -n` / shellcheck；workflow 语法/actionlint；在临时 Ubuntu 22.04/24.04 上测试缺包安装、已装 no-op、probe 失败；Deploy preflight 回归。
- **文档**：`docs/deployment.md` / `.en.md` 增加“Provision 入口 / 新机 cloud-init / bubblewrap 前置”；更新 runbook；中英成对。

## 实施步骤

1. 新增 `deploy/provision-bubblewrap.sh` 与本地 dry-run/单测；确认 `--check` 在缺包时返回稳定错误码。
2. 新增 `provision.yml`，接 `production` 审批和专用特权凭据；在临时环境演练 install/no-op/probe 失败三条路径。
3. 增加新机 cloud-init（或 Ansible base role），并让 `bootstrap-server.sh` 的包列表与之一致。
4. 更新 `docs/deployment.*`、runbook 和 Deploy 失败提示；补可选的 `provision` + `needs` 示例。
5. 生产先在存量机跑一次 Provision，确认 `attribution.preflight` 通过，再走正常 Deploy；不重试已失败的旧 release。
6. 跑门禁并更新流程文档。

## 依赖与交付边界

- 依赖：无；建立在 PR #421/#543 的现有 preflight 与 bootstrap 包列表之上。
- 交付范围：Provision 脚本/workflow、cloud-init/Ansible 新机路径、Deploy 文档/可选接线、相关测试与流程文件。
- 非目标：不做黄金镜像/Packer、不迁移 MySQL 到 RDS、不做容器/K8s、不改 app 代码、不改归因 sandbox 实现、不给 deploy apt 权限、不从 API 自动安装系统包、不写生产凭据或 Session 内容。

## 独立验证

```sh
bash -n deploy/provision-bubblewrap.sh
shellcheck deploy/provision-bubblewrap.sh
pnpm verify:flow
pnpm test:gates
pnpm lint:docs
pnpm verify:docs
```

- 缺 bwrap 的临时环境：`--check` 非零退出并输出 `ATTRIBUTION_BWRAP_MISSING`；安装后 probe 退出 0。
- 已装环境：脚本 no-op，不重复 `apt-get update`；`bwrap --version` 与 probe 均成功。
- 命名空间不可用：probe 非零，输出 `ATTRIBUTION_BWRAP_UNUSABLE`，不继续切换 release。
- 在临时 Ubuntu 22.04/24.04 上以 root 跑脚本，再以 `harness` 跑同一条 probe，预期退出 0；随后 Deploy preflight 通过。

## 验收标准

- 存量机：带审批的 Provision workflow 成功安装/验证 bwrap；随后 Deploy 的 `attribution.preflight` 通过；全程不需要人工 SSH 装包。
- 新机：cloud-init 或 Ansible 创建后 `command -v bwrap` 与 probe 通过；Deploy preflight 通过。
- 门禁仍有效：手动移除 bwrap 后 Deploy 仍在切换 `current` 前失败，旧 release 继续服务。
- deploy 的 sudoers 不变，仍然没有 apt/dpkg 权限；Provision 使用独立特权路径。
- `ATTRIBUTION_BWRAP_MISSING` / `UNUSABLE` 在日志和 runbook 中可区分；Provision 日志可审计且不含凭据。
- 文档、workflow、脚本和流程门禁全绿；中英文档配对一致。

## 门禁与 CI

- `pnpm verify:flow`、`pnpm test:gates`：流程/依赖/正文/状态机。
- `pnpm lint:docs`、`pnpm verify:docs`：部署文档与中英配对。
- `bash -n`、shellcheck、actionlint（若可用）：脚本与 workflow 静态检查。
- 在临时 Ubuntu 环境执行 provision 的 install/no-op/probe 失败三条路径；Deploy preflight 回归。

## 非目标

- 不做完整不可变基础设施/黄金镜像，不做 MySQL 拆分或容器化；这些在多机/合规需求出现时另开 issue。
- 不把 `apt-get` 放进 `release.sh` 或 app deploy 的 sudoers；不把 root SSH key 用于日常 Deploy。
- 不修改归因 sandbox 的挂载/隔离语义，不改 `ATTRIBUTION_BWRAP_*` 错误码含义。
- 不写入生产凭据、Session 内容、Feishu 私密内容或主机地址。
