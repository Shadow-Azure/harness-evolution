# Agent Note: 用独立 Provision 流水线安装系统前置

Status: implemented

[English](2026-11-23-provision-bubblewrap-pipeline.en.md) | 中文

## Problem

归因 Skill 在 Linux 上依赖 `bubblewrap`，但它是 OS 包，不在 Python 依赖里。生产机在 bootstrap 加入该包之前初始化，最近的 Deploy 被 `attribution.preflight` 拦下；旧 release 继续服务，但新版本无法上线。日常 Deploy 以 `deploy` 用户运行，sudoers 只覆盖 `systemctl`，没有 apt/dpkg 权限。若把 apt 交给 deploy，等于把 root 交给流水线；若继续人工 SSH 装包，则不可重复、不可审计，也无法覆盖新机。

## Decision

系统包 provisioning 走独立的 `Provision` workflow，与发布解耦：

- `.github/workflows/provision.yml` 只由 `workflow_dispatch` 触发，绑定 `production` 环境，只允许从 `main` 运行；使用 `production` 环境的专用 root 凭据 `PROVISION_SSH_KEY` / `PROVISION_SSH_USER`，复用 `ALIYUN_HOST`、`ALIYUN_SSH_PORT`。
- `deploy/provision-bubblewrap.sh` 以 root 幂等执行：先检测，已安装时只验证，缺失时才 `apt-get update` + 安装；最后以 `harness` 身份运行最小命名空间探针。Ubuntu 24.04 的 AppArmor 默认限制 unprivileged userns，探针失败时脚本安装只放行 bwrap 可执行路径的 `/etc/apparmor.d/bwrap-userns-restrict` 并重试，不改主机级 `kernel.apparmor_restrict_unprivileged_userns`。`--check` 只读，`--dry-run` 只打印计划；错误码与 `attribution.preflight` 的 `ATTRIBUTION_BWRAP_MISSING` / `ATTRIBUTION_BWRAP_UNUSABLE` 对齐。
- 新机由 `deploy/cloud-init.yaml` 在创建阶段安装 `bubblewrap`；Ubuntu 24.04 仍需在创建后跑一次 Provision `install` 应用 AppArmor profile。`bootstrap-server.sh` 仍是基础包清单的 source of truth。
- `release.sh` 的 preflight 保留为门禁；Deploy 失败摘要把错误码映射到 Provision 入口与 runbook。deploy 的 sudoers 不变。

## Alternatives considered

- **给 deploy 加 apt 权限**：apt 维护者脚本和 hook 以 root 执行，等价于给流水线 root；且日常发布不需要装包。拒绝。
- **在 `release.sh` 里按需安装**：每次发布都可能触发 root 操作，削弱 fail-closed 预检，还要求 Deploy 携带 root 凭据。拒绝。
- **每次让管理员重跑 `bootstrap-server.sh`**：脚本会处理用户、MySQL、nginx、systemd 等大范围状态，作为单包补救过重且需要人工。拒绝。
- **阿里云 Cloud Assistant/OOS + RAM 角色**：省掉主机 SSH 密钥，但需要额外的云 API 凭据、角色与调用链；本期先用专用 root SSH 密钥，后续可在同一入口替换实现。暂缓。
- **在 Deploy workflow 里加 `provision` job + `needs`**：会让每次发布携带 root，扩大爆炸半径；保留为可选接线，默认使用独立入口。拒绝默认启用。

## Consequences

- 存量机需要一次性 root 授权：把专用公钥加入 `authorized_keys` 并写入 `production` 环境的 `PROVISION_SSH_KEY`；之后由 workflow 执行，密钥可轮换，日志不含凭据。
- `production` 环境目前没有 required reviewers，且 GitHub 的环境 Secret 对同一环境的所有 job 可见；Deploy 也声明该环境，只是代码不引用这个 root key。要按 workflow 收窄，需要单独的 environment 或 required reviewers；当前账号没有创建 environment 的 admin 权限，这是已知限制。
- `--check` 在缺包时会非零退出并给出 `ATTRIBUTION_BWRAP_MISSING`，因此“检查”本身可能让 workflow 变红；这是有意的可观测信号，安装后同一条命令应变绿。AppArmor profile 随 Provision 安装并持久化在 `/etc/apparmor.d`，重启后由 apparmor.service 重新加载。
- 新增系统前置时沿用同一模式：脚本提供只读检查与幂等安装，CI 负责在干净主机上验证契约（见 #552），Deploy 继续 fail-closed。
- 本期不引入云 API、Packer 或 Ansible；多机/合规需求出现时再演进。
