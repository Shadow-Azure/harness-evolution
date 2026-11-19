# M18 生产 Git 出网代理与失效回退

[English](m18-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m18
title: M18 生产 Git 出网代理与失效回退
status: planned
github:
  number: 27
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/27
```

## 目标

让生产机在访问 GitHub 不稳定时，通过一个只服务 git 子进程的本地 Xray/VLESS 代理完成目标仓库读取、版本列表与工作区同步；代理配置经 GitHub Secret 注入，健康时走代理、失效时在当前进程内自动直连，未配置或配置不合法时完全回到直连，不影响 API 的其它出网。

## 范围

`deploy/` 的 Xray 安装、配置渲染、systemd 单元与 bootstrap，`.github/workflows/deploy.yml` 的 Secret 接线与部署前探测，`apps/api/app/third_party_api/git/` 的代理感知 runner 与健康状态机，`apps/api/app/config.py` 与 `main.py` 的配置和装配，`docs/` 的代理运维文档，以及对应的流程文件与 Agent Note。

## 验收

- 未配置 `XRAY_CONFIG`：不安装、不启动代理，API 不注入 `HE_GIT_PROXY`，git 直连且行为不变。
- 配置合法：代理单元常驻在 `127.0.0.1` 的 mixed 入站，API 的 git 子进程（内容读取、`ls-remote`、工作区 clone/push）经 `HE_GIT_PROXY` 走代理，其它出网不受影响。
- 配置非法、代理起不来或隧道探测失败：部署告警并移除 `HE_GIT_PROXY`，发布继续直连。
- 运行中代理失效：连续失败后熔断为直连，代理层失败的单次请求直连重试一次；后台探测恢复后回到代理；不重启 API。
- 日志只记录状态、失败分类与耗时，不记录 UUID、公钥、服务器地址或完整配置。
- 双语运维文档覆盖 Secret 格式、关键字段、首次启用、轮换与回滚；流程与文档门禁通过。

## 非目标

不把 `HTTP_PROXY`/`HTTPS_PROXY` 做成全局开关，不代理 API 的普通 HTTP 调用，不改变 `preview/*` 同步契约或 20 秒内容读取预算，不把 Xray 安装放进日常发布，不提供跨境合规结论，不改前端 UI。
