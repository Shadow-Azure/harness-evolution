# 阿里云部署保姆级手册（m6-22 / #198）

对应 issue：[#198](https://github.com/Shadow-Azure/harness-evolution/issues/198)。本页是一次性操作记录（语料外），常驻事实见 [docs/deployment.md](../docs/deployment.md)。目标形态：单台 ECS 上 nginx + uvicorn(systemd) + 自建 MySQL 8，GitHub Actions 自动发布。

## 1. 购买 ECS（控制台操作）

1. 打开 <https://ecs-buy.aliyun.com/>，付费模式选**包年包月**，先买 1 个月。
2. 地域选离自己近的大区（如华东1·杭州）。
3. 实例规格：优先 2核4G（如 `ecs.u1-c1m2.large`）；预算紧可用 99元/年 活动的 2核2G 经济型 e 实例（部署后加 2G swap）。
4. 操作系统选 **Ubuntu 24.04 64位**（自带 Python 3.12，无需 PPA；22.04 也可，bootstrap 会自动走 deadsnakes）。
5. 系统盘 40GB ESSD Entry；带宽固定 3Mbps。
6. 登录凭证选**自定义密码**，设强密码并记牢。
7. 安全组端口勾选 22、80、443。
8. 支付后等实例**运行中**，记下公网 IP；本机 `ping <公网IP>` 有回复即通。

## 2. 安装部署公钥（本机一条命令）

1. 部署专用密钥对本机路径：`~\.ssh\harness-deploy`（私钥）/ `~\.ssh\harness-deploy.pub`（公钥），已生成，勿删除。
2. 把公钥装到服务器（提示输入 root 密码，只在本机输入）：`type $env:USERPROFILE\.ssh\harness-deploy.pub | ssh root@<公网IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`。
3. 验证免密：`ssh -i $env:USERPROFILE\.ssh\harness-deploy root@<公网IP> hostname` 返回主机名即可。

## 3. 服务器初始化（bootstrap 一次）

1. 上传配置与脚本：`ssh root@<IP> mkdir -p /opt/harness/shared/config`，然后 `scp deploy/* root@<IP>:/opt/harness/shared/config/`。
2. 执行初始化：`ssh root@<IP> "bash /opt/harness/shared/config/bootstrap-server.sh"`。脚本会幂等安装/更新带 `StateDirectory=harness-evolution` 的 systemd unit，并创建 `/var/lib/harness-evolution`（属主 `harness:harness`）。
3. 记下脚本输出里的 MySQL 密码位置（`/root/harness-mysql-password.txt`）。
4. 填 `.env`：取回密码 `ssh root@<IP> cat /root/harness-mysql-password.txt`，本地生成 `HE_JWT_SECRET`（`openssl rand -hex 32`）与管理员密码，按 [.env.example](../.env.example) 组装 `HE_DB_URL`（`mysql+asyncmy://harness:<密码>@127.0.0.1:3306/harness_evolution?charset=utf8mb4`）与 `HE_DATA_DIR=/var/lib/harness-evolution/data`，scp 到 `/opt/harness/shared/.env`（root：`chown deploy:deploy` + `chmod 600`）。
5. 确认系统状态：`systemctl show -p StateDirectory harness-api` 输出 `StateDirectory=harness-evolution`；`ls -ld /var/lib/harness-evolution` 属主/属组为 `harness:harness`。
6. 2核2G 机型加 swap：`fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`。

## 4. GitHub 仓库配置（网页粘贴）

1. Settings → Secrets and variables → Actions：
   - Secret `ALIYUN_HOST` = 公网 IP；
   - Secret `ALIYUN_USER` = `deploy`；
   - Secret `ALIYUN_SSH_KEY` = 本机 `~\.ssh\harness-deploy` **私钥**全文（含 BEGIN/END 行；用 `gh secret set ALIYUN_SSH_KEY < ~\.ssh\harness-deploy` 直推，不经聊天与剪贴板）；
   - Variable `ALIYUN_SSH_PORT` = 22。
2. Settings → Environments → 新建 `production`（可加 required reviewers）。
3. （可选）环境变量 `HE_DATA_DIR`：留空即用默认 `/var/lib/harness-evolution/data`；自定义时必须绝对路径、不在发布目录下且由 bootstrap/StateDirectory 授权。`gh variable set HE_DATA_DIR --env production --body /var/lib/harness-evolution/data`。
4. 存量机首次 Provision（一次性 root 授权，之后由 workflow 执行）：
   - 生成专用密钥：`ssh-keygen -t ed25519 -f ~/.ssh/harness-provision -N "" -C harness-provision`；
   - 把公钥追加到生产机 root：`ssh root@<IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys" < ~/.ssh/harness-provision.pub`（也可在阿里云 Cloud Assistant / VNC 执行同样内容）；
   - `gh secret set PROVISION_SSH_KEY --env production < ~/.ssh/harness-provision`（Environment Secret，只有带 `production` 环境的 job 能读）；`PROVISION_SSH_USER` 默认 `root`，无需设置；
   - Actions → `Provision` → `check`（缺包时应输出 `ATTRIBUTION_BWRAP_MISSING`）→ `install`，直到 `state=ready`。该密钥只用于 Provision，不用于 Deploy；轮换时替换 `production` 环境 Secret 并删除主机旧公钥。

5. （可选）接真实评测平台时（#244）：`gh secret set HE_EVAL_MODE`（填 `http`）、`gh secret set HE_EVAL_BASE_URL`、`gh secret set HE_EVAL_API_KEY`；`Deploy` 流水线会把它们注入 `/opt/harness/shared/.env`，未配置时跳过、不影响发布。注入细节：值 base64 传输，服务器侧 `deploy/inject-config.py` 解码后整文件临时文件+替换原子重写（无半写入、重跑幂等），`&`/`$`/反引号/`|`/引号等特殊字符均安全；单键解码失败（含解码结果含换行）告警跳过、不阻塞发布，SSH 或写盘失败则中止发布，重跑部署幂等修复。`HE_EVAL_API_KEY` 走 `gh secret set HE_EVAL_API_KEY --body "<密钥>"` 直推，不在聊天或截图出现。

5. （可选）Claude Code（#376）：`gh secret set CLAUDE_CODE_MODEL`（MiniMax 国内版填 `MiniMax-M3.1-Flash[1m]`）；`gh secret set CLAUDE_CODE_BASE_URL`（国内版 `https://api.minimax.cn/anthropic`）；`gh secret set CLAUDE_CODE_API_KEY`（先填占位，之后换真实 key）。版本可选用 `gh variable set CLAUDE_CODE_VERSION --body 2.1.311-1`。`Deploy` 会在发布前安装并写入服务器 `~/.claude`；三个 Secret 全未配置时该步骤跳过。

## 5. 首次发布与验收

1. 存量机先在 Actions 运行 `Provision`（`install`，确认 `state=ready`）；新机确认 cloud-init 已安装 bubblewrap。然后在本分支 PR 合并后（或在 Actions 页手动 `workflow_dispatch` 触发 Deploy）。
2. 观察 `Deploy` job 全绿；失败看日志定位（常见：Secrets 值粘贴带空行、known_hosts 未收录）。
3. 服务器探活：`ssh deploy@<IP> "curl -sf http://127.0.0.1:8787/api/health"`，响应应含 `"data":{"ok":true}`。
4. 启动向导选择 skill 版本 `v7.0.2`，应能解析成功、不再出现「目标文件暂时不可读取」。
5. 浏览器打开 `http://<公网IP>`，用 `HE_ADMIN_*` 账号登录，浏览 Session 列表与执行流图。
6. 回滚演练：Actions 重跑上一 release 的 Deploy（或在服务器手工软链退回 + `sudo systemctl restart harness-api`）。
7. Claude Code：`ssh deploy@<IP> '~/.local/bin/claude --version'`；`claude doctor` 应无 settings 错误；把占位 API key 换成 MiniMax 真实 key 后，`claude -p "只回复 OK"` 应返回结果。

### 验证 Skill 归因

对象绑定与向导重算共用 `AI_AGENT_PROVIDER`、CLI、服务 settings 和密钥。默认 `claude-code`，显式 `fake` 可用缓存。Claude 使用 `ANTHROPIC_MODEL`、共享 settings 和 CLI 默认模型，已冻结的批次保留原快照。上传包与产物位于 `HE_DATA_DIR/attribute`，可用 `HE_ATTRIBUTION_PACKAGE_DIR` 指定持久卷。

Ubuntu 首次 bootstrap 与新建 ECS 的 cloud-init 会安装 bubblewrap。存量机不再手工 SSH 装包：在 Actions 运行 `Provision`，先用 `check` 确认缺包并输出 `ATTRIBUTION_BWRAP_MISSING`，再以 `install` 安装并验证；`state=ready` 表示 `harness` 的最小命名空间探针已退出 0。Ubuntu 24.04 默认用 AppArmor 限制 unprivileged userns；Provision 会安装只放行 `/usr/bin/bwrap` 的 `/etc/apparmor.d/bwrap-userns-restrict` 并重试探针，不关闭主机级 `kernel.apparmor_restrict_unprivileged_userns`。Provision 只允许从 `main` 触发，使用专用 `PROVISION_SSH_KEY`，deploy 用户仍没有 apt/dpkg 权限。每次运行记录在 Actions run history；脚本只输出固定文案、路径和错误码，不打印环境变量或凭据。排障时可在主机上用服务账号复核同一条探针：

```sh
sudo -u harness bwrap --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true
```

发布时部署账号用候选 API 检查公共 Provider，失败时恢复备份的 `.env`，迁移和 release 切换均未执行。修复主机后重跑 Deploy。若该版本已在运行，执行 `sudo systemctl restart harness-api`。API 以服务账号再次检查，查看启动记录：

```sh
journalctl -u harness-api -b -g 'attribution.preflight|attribution_binding_worker'
```

`ATTRIBUTION_BWRAP_MISSING` 表示服务 PATH 找不到 bwrap，`ATTRIBUTION_BWRAP_UNUSABLE` 表示命名空间探针未能成功，检查服务账号权限和主机命名空间策略。`ATTRIBUTION_PROVIDER_UNSUPPORTED` 表示公共 Provider 缺少 Skill 能力。预检失败时两处对象页提示“归因未运行”，已排队绑定保留到下次就绪启动。

恢复后应看到 `ready=True`、`started=True`。以空间成员身份读取 `GET /api/workspaces/{wid}/attribution-skill-packages`，应有 `runtimeEnabled=true`。后台自动领取已到期的绑定。核对原 generation，避免重新绑定生成另一批次：

```sql
SELECT attribution_generation, attribution_due, attribution_owner, attribution_failures
FROM evolution_targets WHERE workspace_id = '<workspace>' AND id = '<target>';
SELECT attribution_skill_name, COUNT(*) AS reports
FROM probe_reports WHERE workspace_id = '<workspace>' AND binding_generation = '<generation>'
GROUP BY attribution_skill_name;
```

批次成功后 owner 和 due 均可为空。按同一代次核对对象总览报告及 `attribute/<workspace>/attribute_output/<generation>/<case>/probe_report.json`。历史生产事件 #544 的验收口径为原 generation 下 22 条 discovery 对应 22 份 `attribute-badcases` 报告。

## 6. 常见问题

- **80 访问不了**：安全组没放行 80；`systemctl status nginx`；`nginx -t` 报错按提示改。
- **502 Bad Gateway**：harness-api 没起来，`journalctl -u harness-api -n 50`；多半是 `.env` 缺 `HE_JWT_SECRET` 或 `HE_DB_URL` 密码错。
- **迁移失败**：确认 RDS/自建 MySQL 已启动、账号能连；`alembic.ini.release` 在 release 目录内可查注入结果。
- **切换版本报「目标文件暂时不可读取」**：`/api/health` 的 `data.ok` 为 false，或 `HE_DATA_DIR` 落到了发布目录；检查 `vars.HE_DATA_DIR` 与 `/var/lib/harness-evolution` 属主，必要时重跑 bootstrap。
- **发布在切换 current 前失败**：看 `release.sh` 输出的 `HE_DATA_DIR` 路径与原因；修复后重跑 Deploy，`.env` 已自动恢复。
- **Actions SSH 卡住**：ECS 安全组 22 端口来源是否放行 GitHub Actions runner（runner IP 段动态，先放行 0.0.0.0/0 并禁密码登录）。
- **Claude Code 未安装或 401**：看 Deploy 的“准备/安装并配置 Claude Code”步骤；`CLAUDE_CODE_MODEL` 与 `CLAUDE_CODE_API_KEY` 必须同时存在；服务器 `~/.claude/settings.json` 的 base URL 要与 key 的区域一致（国内版 `.cn`，国际版 `.io`）。
- **换绑域名**：A 记录指向 IP → 备案完成 → 免费证书签发 → nginx 加 443 server 块 + `HE_WEB_BASE_URL`/`HE_CORS_ORIGINS` 改域名。

## 7. 状态记录

- 2026-11-09：issue #198 建立，分支 `deploy/m6-22-aliyun`；ECS 待购买（用户选定：新购 ECS / 自建 MySQL / 先 IP+HTTP / Ubuntu）。
