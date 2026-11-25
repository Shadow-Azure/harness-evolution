# Agent Note: 用 PR 门禁验证部署 provisioning 契约

Status: implemented

[English](2026-11-24-ci-deploy-contract-gate.en.md) | 中文

## Problem

PR #543 给归因运行时加了 `attribution.preflight`：Linux 上缺 `bubblewrap` 时在发布切换 `current` 前失败。该 PR 的 CI 全绿并合入，下一次 Deploy 才在生产机暴露缺包，旧 release 继续服务。CI 的 PR 门禁只验证代码行为，没有执行"缺前置 → provisioning → 服务账号可用"的真实链路；Deploy 又是 `workflow_run` 的合并后流程，所以第一次真实环境检查发生在合并之后。单测可以 mock `bwrap`，但 mock 恰好掩盖了这次事故的根因。

## Decision

把部署 provisioning 契约前移到 PR 必过检查，分两层：

- **静态契约**（`apps/api/tests/deploy/test_provisioning_contract.py`，随普通 API 套件运行）：`deploy/attribution-runtime-prerequisites.list` 是归因运行时 OS 前置的唯一清单；bootstrap 读取它，cloud-init 镜像它，Provision 脚本安装同一包；`release.sh` 的 preflight 必须在 `ln -sfn current` 之前；`ci.yml` 的 `deploy-contract` 必须在 `ci-ok.needs` 里。任何一条漂移都在 PR 阶段失败。
- `deploy-contract` 在干净 Ubuntu 容器中运行 `apps/api/tests/deploy/verify_provisioning_contract.sh`。移除 bwrap 后，Provision `--check` 须以退出码 10 报缺包，`harness` 在未配置和显式开启时的预检均须返回 `ATTRIBUTION_BWRAP_MISSING`，显式关闭时须就绪。门禁随后运行与 Provision workflow 共用的安装脚本，验证 `state=ready`、`bwrap --version`、服务账号的命名空间探针和启用沙箱的预检。
- `deploy-contract` 加入 `ci-ok.needs`；分支保护仍只需要 `ci-ok` 一个 required check，增删 lane 不改变仓库设置。

## Alternatives considered

- **只加 pytest mock 分支**：拒绝了。事故根因就是 mock 覆盖了 bwrap 存在性；再多的 mock 也不能证明主机能跑通真实探针。
- **在 Deploy 里自动 `apt-get` 或失败重试**：拒绝了。deploy 保持无特权；自动装包会把 root 权限带进日常发布，且失败重试会掩盖 provisioning 缺失。
- **依赖自托管 runner / 预装 bwrap 的镜像**：拒绝了。预装 bwrap 会让负例失真；门禁必须在没有该前置的干净环境里先红后绿。
- **把 preflight 从发布路径挪到 CI**：拒绝了。preflight 是运行期安全网，必须留在真实发布路径；CI 只是把同一契约前移，不替代它。

## Consequences

- PR 合并时间增加一个 lane（安装 Python 依赖 + 真实 provision，预计数分钟）；换来的是"新增运行时前置但没有 provisioning 路径"在合并前失败。
- 沙箱新增系统依赖时，先改 `deploy/attribution-runtime-prerequisites.list`，再同步 cloud-init 与 Provision 安装路径。
- 容器内无法加载宿主 AppArmor profile，运行时契约验证的是"包存在且服务账号可用 bwrap"；Ubuntu 24.04 的 AppArmor 修复路径仍由 Provision 脚本与部署手册覆盖。
- 分支保护必须把 `ci-ok` 设为 required check（仓库设置，一次性人工操作）；只加 job 不改保护时，PR 仍可能绕过。
