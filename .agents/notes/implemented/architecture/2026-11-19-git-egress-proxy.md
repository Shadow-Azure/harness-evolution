# Agent Note: 生产 Git 出网代理与失效回退

Status: implemented

[English](2026-11-19-git-egress-proxy.en.md) | 中文

## Problem

生产读取目标仓库的 `SKILL.md` / `AGENT.md` 时，冷缓存会触发对 GitHub 的 git 操作；国内链路在 20 秒内经常完不成，用户看到「读取目标文件超时」。单 ref 浅拉取减少传输量，但出网不稳定本身仍在，需要可选代理。

代理不能按「把一个 VLESS 串填进 `HTTPS_PROXY`」实现：VLESS 是 Xray 的出站协议，git 只认 HTTP CONNECT 或 SOCKS 代理；生产机必须先跑一个本地客户端，把 VLESS 出站转成回环上的 HTTP 入站。也不能靠改 `.env` 后等运行中的进程自动生效：systemd `EnvironmentFile` 只在启动时读取，重启 API 会打断正在跑的进化任务，还可能与健康检查形成重启风暴。全局 `HTTP_PROXY` 又会把上游、评测和内部调用一起绑在代理上，`NO_PROXY` 漏一个就可能出事故。

## Decision

- 配置入口收敛为一个 GitHub Environment Secret `XRAY_CONFIG`（完整 Xray JSON）。流水线在 runner 侧校验结构，只接受回环上的 `mixed`/`http` 入站和 `vless` 出站；服务器侧原子写成 `/opt/harness/shared/proxy/config.json`（`0600`，归 `deploy`），不进入仓库、API `.env`、日志或 PR。
- Xray 二进制由 runner 从官方 release 下载，固定版本 `v26.11.9` 与 amd64/arm64 SHA256，连同 `geoip.dat`/`geosite.dat` 上传；服务器不访问 GitHub，避免「装代理要先有代理」的循环。`harness-proxy.service` 以 `deploy` 用户常驻，只监听回环，由 bootstrap 幂等安装。
- API 只新增 `HE_GIT_PROXY=http://127.0.0.1:<port>` 这一个不含凭据的变量。`ProxyAwareGitRunner` 在 `SubprocessGitContent`、`SubprocessGitRemote` 和 `GitWorkspaceManager` 三个既有 runner 接缝上注入；使用代理时设置 `HTTPS_PROXY`/`HTTP_PROXY` 并对 clone/fetch/ls-remote 做 GitHub SSH→HTTPS 重写（push 保持原 remote 以保留 SSH 认证），直连时移除全部代理变量。其它 HTTP 出网完全不受影响。
- 进程内状态机决定是否走代理：`closed` 正常使用，代理层连续 3 次失败进入 `open` 直连，冷却后后台用经代理的 HTTPS HEAD 探测，进入 `half_open`，连续 2 次成功回到 `closed`。单次请求遇到代理层失败立即直连重试一次；代理正常但 GitHub 慢仍归入内容读取超时，不误判为代理故障。状态不持久化，部署/重启从 `closed` 开始。
- 部署在写 `.env` 前做一次隧道探测；只有探测通过才注入 `HE_GIT_PROXY`，否则移除旧值、停止代理、删除服务器配置并继续发布。Secret 缺失、JSON 非法、下载校验失败、单元未安装、启动或探测失败都走同一条直连回退。
- 日志只记录 `git.proxy.state`、失败次数与失败分类；代理地址是本地回环地址，UUID/公钥/服务器地址只存在 Secret 与 `0600` 配置文件。

## Alternatives considered

- **全局 `HTTPS_PROXY` + `NO_PROXY` 清单。** 否决：范围不可控，任何遗漏都会把内部调用送进代理；代理故障时影响所有出网，而本次只解决 git 读取。
- **运行中代理失效时改 `.env` 并重启 API。** 否决：环境变量不热更新，重启会打断进化任务，健康检查失败还可能形成重启风暴；运行时回退应是进程内布尔状态。
- **每次请求临时 `curl`/shell 包一层代理。** 否决：增加进程与超时层，错误分类分散，还会绕过现有 runner 的取消与进程组清理。
- **统一用 SSH `ProxyCommand` 代理所有远端。** 否决：需要额外 `connect` 工具，非 GitHub SSH 仍无法复用 HTTP 代理；把 GitHub SSH 重写为 HTTPS 更小且可测。
- **在生产服务器安装 Xray。** 否决：服务器当前到 GitHub 的链路正是问题所在，下载会先失败；runner 下载并校验后上传更可靠。
- **让代理配置与应用配置同放 `.env`。** 否决：会把 UUID/公钥带进 API 进程和备份；Secret 与本地配置文件分离更小。

## Consequences

- 首次启用需要一次 root 操作：以 root 重跑 `deploy/bootstrap-server.sh` 安装 `harness-proxy.service` 与对应 sudo 收敛；之后轮换 Secret 只需重新发布。
- 代理是单点；节点失效、限速或 TLS 指纹变化会导致探测失败，系统回退直连但不会自动换节点。需要监控与人工换节点。
- 未配置 Secret 时行为与现在完全一致；配置后 git 子进程走代理，其它出网不变。`preview/*` 契约、20 秒内容预算和 body hash 语义都不变。
- 部署脚本新增 `fetch-xray.sh`、`xray-config.py` 与 `inject-config.py --unset`，配置/runner/状态机均有单测；日志与文档不包含代理凭据。
- 非 GitHub 的 SSH 远端不会被重写，也不会走 HTTP 代理；需要时改用 HTTPS 或单独配置 `ProxyCommand`。
