# Git 出网代理

[English](git-proxy.en.md) | 中文

生产机访问 GitHub 不稳定时，可为 git 子进程启用本机 Xray/VLESS 代理。代理只覆盖目标仓库读取、`ls-remote` 和进化工作区 clone/push；API 的其它出网保持直连。凭据只存在 GitHub Environment Secret 与服务器本地文件，API 只拿到一个不含凭据的本地 HTTP 地址。

## 链路

```text
git subprocess --HTTPS_PROXY--> 127.0.0.1:10808 (Xray mixed inbound)
                                      |
                                      +--VLESS/REALITY--> proxy host --> github.com
```

VLESS 是 Xray 的出站协议，不是 HTTP 代理，不能直接写进 `HTTPS_PROXY`。服务器必须常驻一个 Xray 客户端，把 VLESS 出站转成回环上的 mixed/HTTP 入站；`deploy/harness-proxy.service` 负责这个客户端。

## GitHub Secret

| 名称 | 位置 | 内容 |
|---|---|---|
| `XRAY_CONFIG` | Environment `production` 的 Secret | 完整 Xray JSON 配置 |

`XRAY_CONFIG` 是唯一新增的 Secret。流水线把它经 base64 + stdin 送到服务器，写成 `/opt/harness/shared/proxy/config.json`（`0600`，归 `deploy`），不进入仓库、API `.env`、日志、issue 或 PR 描述。

配置至少满足：

- 一个 `protocol` 为 `mixed` 或 `http` 的入站，`listen` 必须是 `127.0.0.1`、`localhost` 或 `::1`，端口合法；流水线据此生成 `HE_GIT_PROXY=http://127.0.0.1:<port>`。
- 一个 `protocol` 为 `vless` 的出站，带 `settings.address`、`settings.port`、`settings.id`、`encryption: "none"`、`flow: "xtls-rprx-vision"`，以及 `streamSettings.security: "reality"` 与 `realitySettings` 的 `serverName`、`fingerprint`、`publicKey`、`shortId`。
- 入站不得监听 `0.0.0.0` 或 `::`，否则配置校验失败并回退直连；本机代理不能成为公网开放代理。
- `dns`、`routing` 可选；引用 `geosite:` / `geoip:` 时需保留发布包里的 `geosite.dat` / `geoip.dat`，流水线会一起上传。

占位示例只说明形状，真实值由你在 Secret 中填写：

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "tag": "mixed",
      "listen": "127.0.0.1",
      "port": 10808,
      "protocol": "mixed",
      "settings": { "auth": "noauth", "udp": true }
    }
  ],
  "outbounds": [
    {
      "tag": "proxy",
      "protocol": "vless",
      "settings": {
        "address": "<PROXY_HOST>",
        "port": 443,
        "id": "<VLESS_UUID>",
        "encryption": "none",
        "flow": "xtls-rprx-vision"
      },
      "streamSettings": {
        "network": "raw",
        "security": "reality",
        "realitySettings": {
          "serverName": "<REALITY_SERVER_NAME>",
          "fingerprint": "chrome",
          "publicKey": "<REALITY_PUBLIC_KEY>",
          "shortId": "<REALITY_SHORT_ID>"
        }
      }
    },
    { "tag": "direct", "protocol": "freedom" },
    { "tag": "block", "protocol": "blackhole" }
  ]
}
```

## 部署流水线

`Deploy` 在写 `.env` 前执行以下步骤，任一步失败都只告警并回退直连，不阻断发布：

1. 用 `deploy/xray-config.py --extract` 在 runner 侧校验 JSON、回环入站和 VLESS 出站，并解析出本地代理地址。
2. 按服务器架构用 `deploy/fetch-xray.sh` 下载固定版本 Xray（`v26.11.9`，amd64/arm64 各有固定 SHA256），解包 `xray`、`geoip.dat`、`geosite.dat`。
3. 上传到 `/opt/harness/shared/proxy/bin/`，原子写配置，`sudo systemctl restart harness-proxy`。
4. 等待单元 active，并用 `curl -x <本地代理> https://api.github.com/zen` 做一次隧道探测。
5. 探测通过才把 `HE_GIT_PROXY` 写入 `.env`；否则 `inject-config.py --unset HE_GIT_PROXY` 移除旧值，API 直连。

Secret 未配置、配置非法、下载/校验失败、单元未安装、代理未启动或探测失败，都会走同一条直连回退路径。服务器未安装单元时，流水线会提示以 root 重跑 `deploy/bootstrap-server.sh`。

## 运行时健康与回退

API 进程内维护一个状态机，只决定 git 子进程是否使用代理：

- `closed`：代理可用，git 子进程设置 `HTTPS_PROXY`/`HTTP_PROXY`；GitHub 的 `git@github.com:` 与 `ssh://git@github.com/` 远端在子进程内重写为 HTTPS，非 GitHub SSH 远端不受影响。
- 代理层失败（连接拒绝、代理握手失败、407、CONNECT 502）：累计三次后进入 `open`，后续请求直连；单次请求遇到代理层失败会立即直连重试一次。
- `open`：后台探测按冷却时间重试；成功一次进入 `half_open`，连续成功两次回到 `closed`。
- 代理正常但 GitHub 慢：不切直连，仍按原有内容读取超时处理，避免把链路慢误判成代理故障。
- 状态只在进程内，部署或重启后从 `closed` 开始；不重启 API、不改 `.env` 完成回退。日志只记录状态、失败次数和失败分类，不记录 UUID 或配置内容。

探测间隔与单次上限可用 `HE_GIT_PROXY_PROBE_INTERVAL_SECONDS` / `HE_GIT_PROXY_PROBE_TIMEOUT_SECONDS` 调整，默认 60 / 5 秒。

## 首次启用与轮换

1. 在 GitHub Environment `production` 新增 Secret `XRAY_CONFIG`，填入真实 Xray JSON。
2. 首次启用需服务器以 root 重跑 `deploy/bootstrap-server.sh`，安装 `harness-proxy.service` 和对应的 sudo 收敛；这是一次性环境初始化。
3. 触发 `Deploy`；在日志中确认代理就绪或看到回退告警。
4. 轮换凭据：更新 `XRAY_CONFIG` Secret 后重新发布；流水线会原子替换配置并重启代理，API 无需改配置。
5. 回退：删除 Secret 或填入非法配置后重新发布，流水线会移除 `HE_GIT_PROXY` 并停止代理；也可在服务器上 `sudo systemctl stop harness-proxy`，API 的熔断会把 git 切到直连。

## 限制与边界

- 代理是单点：节点失效、限速或 TLS 指纹变化都会失败；健康探测能回退直连，但不会自动换节点。
- 只覆盖 git 子进程。API 的普通 HTTP 调用、评测平台请求和上游同步不走这个代理。
- 非 GitHub 的 SSH 远端不会重写，也不会走 HTTP 代理；需要时改用 HTTPS 或单独配置 `ProxyCommand`。
- GitHub 的 SSH 远端在代理模式下重写为 HTTPS；依赖 SSH 私钥认证的私有仓库需改用 HTTPS 凭据，或关闭代理。
- 代理不改变 `preview/*` 的同步契约与 20 秒内容读取预算；冷克隆仍可能超时。
- 跨境链路与自建代理的使用需先过组织合规与安全评审；本页只描述运维接线。

## 排障

- `systemctl status harness-proxy` 与 `journalctl -u harness-proxy` 查看客户端状态；日志不应包含 UUID 或完整配置。
- `curl -x http://127.0.0.1:<port> --max-time 5 https://api.github.com/zen` 手工验证隧道。
- API 日志中 `git.proxy.state` 为 `open` 表示已熔断直连，`git.proxy.retry_direct` 表示单次请求已回退；检查代理单元和 Secret。
- `.env` 中没有 `HE_GIT_PROXY` 表示当前部署走直连，通常意味着 Secret 缺失或代理探测失败。
