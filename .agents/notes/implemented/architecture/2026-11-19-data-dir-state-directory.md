# Agent Note: 生产数据目录由 systemd StateDirectory 托管

Status: implemented

[English](2026-11-19-data-dir-state-directory.en.md) | 中文

## Problem

启动向导在选择 skill 版本后要读取 `SKILL.md` 并计算 body hash；服务端在跑任何 git 命令前先创建 `data_dir/target-content` 缓存目录。`HE_DATA_DIR` 未配置时 `data_dir` 默认 `data`，相对 systemd `WorkingDirectory=/opt/harness/current/api` 落到发布目录。生产以 `User=harness` 运行，发布目录归 `deploy` 所有且随发布整体替换，`harness` 无法 `mkdir`，`OSError` 被统一映射为 `content_unavailable`，向导第一步就失败。

这不是仓库地址、子目录、tag 或网络问题，而是「服务端第一次需要持久写目录」暴露的部署缺口：MySQL 部署不经过 SQLite 的 `data_dir.mkdir`，生产也从未跑过会写 `data/repos` 的进化运行。发布目录不可写是设计事实，数据目录必须落在发布目录之外并由 systemd 管理。

## Decision

- `deploy/harness-api.service` 声明 `StateDirectory=harness-evolution`，由 systemd 在每次启动时创建 `/var/lib/harness-evolution` 并 chown 给 `harness`；bootstrap 以 root 幂等安装/更新 unit、`daemon-reload`、补建目录并重启一次。unit 安装是每环境一次的环境初始化，不进日常发布，deploy 的 sudo 权限不扩大。
- 生产 `HE_DATA_DIR` 必须是绝对路径，默认 `/var/lib/harness-evolution/data`；API 配置在 production 下拒绝相对路径。本地开发继续默认 `./data`，相对进程 cwd 解析。
- `Deploy` 从 GitHub Environment `vars.HE_DATA_DIR` 取值（空值用默认绝对路径），经泛化的 `inject-config.py` 与评测配置一起原子写入 `.env`，注入前备份为 `.env.bak.<sha>`。
- `release.sh` 在切换 `current` 前校验路径：非空、绝对、无空白/换行/`..`、不在 `current` 或 `releases` 下，且目录属主为 `harness:harness` 或已被 unit 的 `StateDirectory=` 覆盖。失败直接退出，当前 release 继续服务。任何失败路径恢复注入前 `.env`；探活失败时先恢复 `.env` 再切回上一 release 并重启。
- API 启动时解析绝对路径、`mkdir(parents=True, exist_ok=True)` 并创建/删除写探针；结果只以 `data: {ok}` 暴露在 `/api/health`，不可写时返回 503，触发发布探活失败与回滚。启动不因目录不可写直接崩溃，避免坏配置造成无 health 响应的 crash loop。路径与错误细节只进日志。
- 路径变更等于数据迁移：`target-content`、`repos`、`workspaces` 不跟随，文档要求停服务、迁移目录后再改配置。

## Alternatives considered

- **方案 B：root helper + sudoers，让 `release.sh` 每次安装 unit。** 否决：unit 源文件在 deploy 可写目录，原样安装等于把 root 信任扩展给发布流水线；unit 变更很少，不值得这个信任面。
- **应用把相对路径锚定到 `$STATE_DIRECTORY`。** 否决：隐藏配置错误，生产与本地语义分叉；部署前无法发现路径写错。
- **只做 `release.sh` 静态校验。** 否决：deploy 用户无法证明 `harness` 真能写，只读挂载、磁盘满、ACL 拒绝都测不出；而且校验发生在 `.env` 已写入之后。
- **只做 health 写探针。** 否决：坏 `.env` 会留在共享文件，回滚后旧 release 仍会读它；探活失败时若不先恢复 `.env`，回滚也可能起不来。
- **启动时 fail fast 退出。** 否决：配合 `.env` 恢复才安全；否则坏值会让新旧 release 都起不来。health 503 已能让发布流水线回滚，同时保留诊断响应。

## Consequences

- `/api/health` 新增 `data.ok`，`HealthResponse` 契约与生成类型同步；监控与发布探活都能看到数据目录可写性。
- 现有环境需要一次性 root 操作：重跑更新后的 bootstrap，或在 `/etc/systemd/system` 安装 unit 后 `daemon-reload` 并重启。此后日常发布全自动。
- `.env` 新增 `HE_DATA_DIR`（由流水线注入）；生产若手工启动且未配置绝对路径，配置校验失败。路径变更需要人工迁移数据。
- 发布失败会恢复 `.env.bak.<sha>`；备份最多保留 5 份，与 release 保留策略一致。
- 该决策不改变 body-hash 与 target revision 解析语义；它只保证解析所需的本地写目录在正确的位置且可写。
