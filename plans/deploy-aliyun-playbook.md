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

1. 本机生成密钥对（如已有 `~/.ssh/id_ed25519` 可跳过）：`ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519 -N '""'`。
2. 把公钥装到服务器（提示输入 root 密码，只在本机输入）：`type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<公网IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`。
3. 验证免密：`ssh root@<公网IP> hostname` 返回主机名即可。

## 3. 服务器初始化（bootstrap 一次）

1. 上传配置与脚本：`ssh root@<IP> mkdir -p /opt/harness/shared/config`，然后 `scp deploy/* root@<IP>:/opt/harness/shared/config/`。
2. 执行初始化：`ssh root@<IP> "bash /opt/harness/shared/config/bootstrap-server.sh"`。
3. 记下脚本输出里的 MySQL 密码位置（`/root/harness-mysql-password.txt`）。
4. 填 `.env`：取回密码 `ssh root@<IP> cat /root/harness-mysql-password.txt`，本地生成 `HE_JWT_SECRET`（`openssl rand -hex 32`）与管理员密码，按 [deploy/env.production.example](../deploy/env.production.example) 组装 `HE_DB_URL`（`mysql+asyncmy://harness:<密码>@127.0.0.1:3306/harness_evolution?charset=utf8mb4`），scp 到 `/opt/harness/shared/.env`（root：`chown deploy:deploy` + `chmod 600`）。
5. 2核2G 机型加 swap：`fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`。

## 4. GitHub 仓库配置（网页粘贴）

1. Settings → Secrets and variables → Actions：
   - Secret `ALIYUN_HOST` = 公网 IP；
   - Secret `ALIYUN_USER` = `deploy`；
   - Secret `ALIYUN_SSH_KEY` = 本机 `~/.ssh/id_ed25519` **私钥**全文（含 BEGIN/END 行）；
   - Variable `ALIYUN_SSH_PORT` = 22。
2. Settings → Environments → 新建 `production`（可加 required reviewers）。

## 5. 首次发布与验收

1. 本分支 PR 合并后（或在 Actions 页手动 `workflow_dispatch` 触发 Deploy）。
2. 观察 `Deploy` job 全绿；失败看日志定位（常见：Secrets 值粘贴带空行、known_hosts 未收录）。
3. 服务器探活：`ssh deploy@<IP> "curl -sf http://127.0.0.1:8787/api/health"`。
4. 浏览器打开 `http://<公网IP>`，用 `HE_ADMIN_*` 账号登录，浏览 Session 列表与执行流图。
5. 回滚演练：Actions 重跑上一 release 的 Deploy（或在服务器手工软链退回 + `sudo systemctl restart harness-api`）。

## 6. 常见问题

- **80 访问不了**：安全组没放行 80；`systemctl status nginx`；`nginx -t` 报错按提示改。
- **502 Bad Gateway**：harness-api 没起来，`journalctl -u harness-api -n 50`；多半是 `.env` 缺 `HE_JWT_SECRET` 或 `HE_DB_URL` 密码错。
- **迁移失败**：确认 RDS/自建 MySQL 已启动、账号能连；`alembic.ini.release` 在 release 目录内可查注入结果。
- **Actions SSH 卡住**：ECS 安全组 22 端口来源是否放行 GitHub Actions runner（runner IP 段动态，先放行 0.0.0.0/0 并禁密码登录）。
- **换绑域名**：A 记录指向 IP → 备案完成 → 免费证书签发 → nginx 加 443 server 块 + `HE_WEB_BASE_URL`/`HE_CORS_ORIGINS` 改域名。

## 7. 状态记录

- 2026-11-09：issue #198 建立，分支 `deploy/m6-22-aliyun`；ECS 待购买（用户选定：新购 ECS / 自建 MySQL / 先 IP+HTTP / Ubuntu）。
