# Deploy 流水线 SSH 会话保活

[English](m6-deploy-ssh-keepalive.en.md) | 中文

```yaml flow
kind: issue
id: m6-23
milestone: m6
depends:
  - m6-22
priority: P1
status: ready
scope:
  - .github/workflows/**
  - .agents/flow/**
adr: []
github:
  number: 202
  url: https://github.com/Shadow-Azure/harness-evolution/issues/202
```

## 背景

m6-22 交付的首次真实发布中，远程 pip 安装期间 SSH 会话被网络中间设备重置（`Connection reset by peer`，exit 255），Deploy 随之失败。服务器侧已改用阿里云 pip 镜像缩短饱和窗口，但长耗时远程步骤（迁移、大体积上传）仍依赖默认无保活的 SSH 连接，任何一次网络抖动都会让整条发布作废。

## 目标

- Deploy workflow 的两处 SSH（rsync 上传与远程发布脚本）带 `ServerAliveInterval=30` / `ServerAliveCountMax=6`，空闲期主动保活，连接抖动可自愈。

## 设计依据

- [plans/fullstack-design/01-architecture.md §6 部署形态与扩展路径](../../../plans/fullstack-design/01-architecture.md)：单实例 SaaS 交付通道的可靠性属于该形态的运行要求；本 issue 只加固通道，不改变部署语义。
- m6-22 issue 的实现内容（Deploy workflow 与 release.sh 职责划分）为本 issue 的直接前置。

## 实现内容

- `.github/workflows/deploy.yml`：`SSH_CMD` 与发布步骤的 ssh 命令追加两个 keepalive 参数。

## 实施步骤

1. 在 m6-22 交付后的缺陷修复 PR 中修改 `deploy.yml` 并同 PR 内推进本 issue 至 ready。
2. 由合并后的 Deploy run 验证真实发布链路。

## 依赖与交付边界

- 依赖：m6-22（Deploy workflow 本体）。
- 交付边界：只改 workflow 的 ssh 参数；不动发布脚本与服务器配置。
- 非目标：见下方专节。

## 独立验证

```sh
pnpm verify:flow
```

- `verify:flow` 全部通过；合并后的 Deploy run 全绿且服务器 `/api/health` 返回 200。

## 验收标准

- Deploy workflow 的 ssh 命令含保活参数。
- 合并后的自动发布全绿，健康检查通过。

## 门禁与 CI

- `verify-flow --diff`：标题带 `(#202)`，diff 落在登记 scope 内。
- 本 issue 由缺陷修复 PR 在同 PR 内从 backlog 激活（flow README 允许的合法路径）。

## 非目标

- 不改 rsync 排除规则、触发条件与发布脚本。
- 不引入第三方 Actions。
