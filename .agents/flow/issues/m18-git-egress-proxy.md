# 生产 Git 出网代理：Xray/VLESS 配置、Secret 注入与健康回退

[English](m18-git-egress-proxy.en.md) | 中文

```yaml flow
kind: issue
id: m18-01
milestone: m18
depends: []
priority: P1
status: in-progress
scope:
  - apps/api/**
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - README.md
  - README.en.md
  - README.i18n.yaml
adr: []
github:
  number: 397
  url: https://github.com/Shadow-Azure/harness-evolution/issues/397
```

## 背景

生产机读取目标仓库的 `SKILL.md` / `AGENT.md` 时，冷缓存会触发对 GitHub 的 git 操作；国内链路下 20 秒内经常完不成，前端表现为「读取目标文件超时」（[issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)）。单 ref 浅拉取减少传输量，但无法解决出网本身不稳定；需要在 git 子进程这一层提供可选的出网代理，并且代理失效时不能让 API 或正在运行的进化任务一起失败。

VLESS 是 Xray 的出站协议，不是 HTTP 代理，不能直接填入 `HTTPS_PROXY`；生产机必须有一个常驻的本地 Xray 客户端，把 VLESS 出站转成 `127.0.0.1` 上的 mixed/HTTP 入站。代理凭据只放在 GitHub Secret 与服务器本地配置文件中，API 只拿到一个不含凭据的本地地址。

## 目标

- 新增一个 GitHub Environment Secret `XRAY_CONFIG`，值为完整 Xray JSON；部署时渲染成服务器本地配置文件，不进入仓库、API `.env`、日志或 PR。
- 部署流水线在 runner 侧下载固定版本、固定校验和的 Xray 二进制，服务器只安装二进制、配置与 systemd 单元；代理只监听回环。
- API 只在 git 子进程上注入 `HE_GIT_PROXY`，覆盖目标内容读取、`ls-remote` 与工作区 clone/push，不设置全局 `HTTP_PROXY`/`HTTPS_PROXY`。
- 进程内健康状态机：代理层连续失败后熔断为直连，后台探测恢复后回到代理；代理层失败的单个请求直连重试一次，不重启 API。
- 未配置 Secret、JSON 非法、代理起不来或隧道探测失败时，部署移除 `HE_GIT_PROXY`，发布与 git 操作完全回到直连。

## 设计依据

- [01 §2 组成与分层](../../../plans/fullstack-design/01-architecture.md#2-组成与分层)：git 读取属于出站集成边界，代理不应扩散成全局网络开关。
- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：`third_party_api` 隔离 git 进程，业务规则留在 service。
- [04 §9 配置项清单](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单)：`HE_GIT_PROXY` 是唯一新增的 API 配置，且只承载本地代理地址。
- [issue #394](https://github.com/Shadow-Azure/harness-evolution/issues/394)：一个 Secret、git-only 接线、健康熔断与直连回退的方案与失效矩阵。

## 实现内容

- `apps/api/app/third_party_api/git/proxy.py` 提供代理控制器：`closed` 走代理、连续失败进入 `open` 直连、冷却后 `half_open` 探测、连续成功恢复；探测用本地 HTTP CONNECT 到 `api.github.com:443`，带 5 秒上限。
- `main.py` 把代理感知 runner 注入 `SubprocessGitContent`、`SubprocessGitRemote` 与 `GitWorkspaceManager`；runner 在代理使用时设置 `HTTPS_PROXY`/`HTTP_PROXY` 与 GitHub SSH→HTTPS 重写，直连时清除这些变量，失败分类不匹配代理层时不误熔断。
- `config.py` 新增 `HE_GIT_PROXY`、探测间隔与探测超时；生产缺省为空，配置非法时启动失败；`main.py` 的 lifespan 启停后台探测。
- `deploy/` 新增 Xray 二进制获取脚本、配置写入脚本、`harness-proxy.service`，bootstrap 幂等安装单元并收敛 sudo；`deploy.yml` 解析 Secret、下载并上传二进制、写配置、重启代理、探测通过后才注入 `HE_GIT_PROXY`，否则 unset。
- `docs/git-proxy.md` 记录 Secret 形状、关键字段与占位示例、首次启用、轮换、回滚、限制与排障；`deploy/env.production.example` 与设计文档同步 `HE_GIT_PROXY`。

## 实施步骤

1. 建立 m18 流程文件与 issue。
2. 实现代理控制器、runner、配置与 lifespan 接线，补单元测试。
3. 实现部署脚本、systemd 单元、Secret 注入与回退，补部署脚本测试。
4. 更新双语文档与 Agent Note，跑门禁并开 PR。

## 依赖与交付边界

- 依赖：无；Xray 二进制由 GitHub Actions runner 下载，不新增 Python 依赖，不改数据库或 API 契约。
- 边界：代理凭据只存在于 GitHub Secret 与服务器 `0600` 配置；API `.env` 只有 `HE_GIT_PROXY` 地址，日志只记状态与失败分类。
- 非目标：不做全局代理、不代理普通 HTTP 出网、不改 `preview/*` 同步契约或 20 秒预算、不改前端 UI、不把 Xray 安装放进日常发布、不给出跨境合规结论。

## 独立验证

```sh
pnpm test:api
pnpm typecheck:api
pnpm lint:api
pnpm verify:flow
pnpm lint:docs
bash -n deploy/bootstrap-server.sh deploy/release.sh deploy/fetch-xray.sh
```

- 代理控制器单测覆盖禁用、熔断阈值、冷却后半开、探测恢复、代理层失败直连重试与成功计数。
- runner 单测断言使用代理时设置代理变量与 SSH 重写，直连时移除全部代理变量，非代理层失败不触发熔断。
- 配置单测覆盖合法本地地址、非法 scheme、带凭据地址与生产缺省的直连行为。
- 部署脚本测试覆盖 `inject-config.py --unset`、Xray 配置提取/校验与非法配置回退；shell 脚本通过 `bash -n`。

## 验收标准

- 未配置 `XRAY_CONFIG`：不写代理配置、不注入 `HE_GIT_PROXY`，git 直连且现有行为不变。
- 配置合法：代理单元常驻回环，内容读取、`ls-remote` 与工作区 clone/push 走代理，其它出网不受影响。
- 配置非法、代理起不来或探测失败：部署告警并移除 `HE_GIT_PROXY`，发布继续直连。
- 运行中代理失效：不重启 API，请求按熔断状态直连；恢复后后台探测自动回到代理；日志无凭据。
- 双语文档覆盖首次启用、Secret 轮换与回滚；流程、文档与聚焦测试门禁通过。

## 门禁与 CI

- `pnpm test:api`、`pnpm typecheck:api`、`pnpm lint:api`、`pnpm verify:flow`、`pnpm lint:docs`、`pnpm contract:check`。
- `verify:flow --diff` 校验 PR 标题与提交的 `(#N)` 及 scope 覆盖。
- 新增测试覆盖代理状态机、runner 环境、配置校验与部署脚本回退。

## 非目标

- 不把 `HTTP_PROXY`/`HTTPS_PROXY` 做成全局开关。
- 不代理 API 的普通 HTTP 调用或评测平台请求。
- 不改变 `preview/*` 的同步契约、内容读取预算或异步化。
- 不提供 Xray 节点采购、跨境合规结论或前端 UI 改动。
