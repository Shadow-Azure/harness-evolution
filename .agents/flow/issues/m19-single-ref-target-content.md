# 生产目标内容读取：单 ref 浅拉取

[English](m19-single-ref-target-content.en.md) | 中文

```yaml flow
kind: issue
id: m19-01
milestone: m19
depends: []
priority: P2
status: done
scope:
  - apps/api/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 395
  url: https://github.com/Shadow-Azure/harness-evolution/issues/395
```

## 背景

启动向导把所选版本解析成 body hash 时，`SubprocessGitContent` 先在请求路径里对目标仓库执行 `git clone --mirror`，再 `git show` 一个 `SKILL.md` / `AGENT.md`。生产数据目录迁移后缓存为空，国内到 GitHub 的链路在 20 秒内拉不完全量 mirror，用户看到「读取目标文件超时」（[issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)）。只读一个 ref 却下载全部历史，失败窗口被放大。

出网代理是另一个正交问题，本轮不实现：代理配置、Secret、部署与失效回退的设计记录在 [#394](https://github.com/Shadow-Azure/harness-evolution/issues/394)，作为后续独立任务。

## 目标

- 目标内容缓存从 per-repo mirror 改为 per-(`repo_url`, `ref`) 浅仓库，只 fetch 目标 ref。
- tag/分支用 `git clone --depth 1 --single-branch --filter=blob:none`；完整 commit 用 `git init` + 单 ref `fetch`；随后 `git show` 只按需拉一个 blob。
- 保持 `read_file` 接口、20 秒上限、稳定错误分类与 body hash 语义不变。

## 设计依据

- [01 §2 组成与分层](../../../plans/fullstack-design/01-architecture.md#2-组成与分层)：目标内容读取属于出站集成的边界。
- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：`third_party_api` 隔离 git 进程，业务规则留在 service。
- [issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)：冷克隆超时的证据与单 ref 浅拉取的取舍。
- [git partial clone](https://git-scm.com/docs/partial-clone)：`--filter=blob:none` 的按需 blob 语义。

## 实现内容

- 缓存键为 `<data_dir>/target-content/<sha256(repo_url)[:32]>/<sha256(repo_url + "\0" + ref)[:16]>/`；同一缓存路径用进程内锁串行，避免并发读取互相删除目录。
- 首次读取 tag/分支：`git clone --depth 1 --single-branch --filter=blob:none --no-checkout --branch <ref> -- <repo_url> <dir>`；完整 40 位 commit SHA：`git init` + `remote.origin.promisor=true` + `remote.origin.partialclonefilter=blob:none` + `git fetch --depth 1 --filter=blob:none --no-tags origin <sha>`。
- 已有缓存：tag/分支执行 `git fetch --depth 1 --filter=blob:none --no-tags origin <ref>` 保持最新；完整 SHA 直接复用。随后 `git show <FETCH_HEAD|HEAD>:<path>`，由 promisor remote 按需拉取一个 blob。
- 失败分类保持稳定且不暴露 stderr：ref 缺失 → `ref_not_found`，文件缺失 → `file_not_found`，网络/代理不可用 → `repo_unreachable`，超时 → `timeout`，git 不可执行 → `git_unavailable`，路径越界 → `path_invalid`，非法 ref → `ref_invalid`；失败或中断时清理半成品缓存目录。
- 不解析 GitHub API、不依赖私有仓库凭据；`TargetContentResolver` 不动。

## 实施步骤

1. 建立 m19 流程文件与 issue。
2. 重写 `SubprocessGitContent` 的缓存与单 ref 拉取。
3. 补 tag/分支/完整 SHA、缺失 ref、缺失文件、缓存复用、清理与 argv 断言测试。
4. 更新 Agent Note，跑门禁并开 PR。

## 依赖与交付边界

- 依赖：无；不新增 Python 依赖，不改数据库或 API 契约。
- 非目标：不实现出网代理（含 Secret、Xray 部署、代理环境与熔断，见 #394）；不改 `preview/*` 同步契约或异步化；不改前端；不改 run workspace 的 mirror/push 模型；不引入 GitHub Contents API 或公共镜像。
- 旧 mirror 缓存目录留在原处，新布局不读取它们，不做数据迁移。
- 完整 commit SHA 直接 fetch；缩写 SHA 不再在本地 mirror 中解析，返回 `ref_not_found`，需要时由后续任务经 GitHub API 或调用方补全。

## 独立验证

```sh
pnpm test:api
pnpm typecheck:api
pnpm verify:flow
pnpm lint:docs
```

- 单测：本地 bare 仓库的 tag、分支与完整 commit 均可读取；冷读 argv 含 `--depth 1 --single-branch --filter=blob:none` 且不含 `--mirror`；缺失 ref/文件返回稳定 reason；复用缓存不再 clone；失败清理缓存。

## 验收标准

- 冷读一个 ref 只 fetch 该 ref，不再 `--mirror`；读取一个文件只按需拉取该 blob。
- tag、分支、完整 commit SHA 都能解析到同一 body hash；缺失 ref/文件保持既有错误码。
- 旧 mirror 缓存存在时不受影响，也不需要迁移。

## 门禁与 CI

- `pnpm test:api`、`pnpm typecheck:api`、`pnpm lint:api`、`pnpm verify:flow`、`pnpm lint:docs`、`pnpm contract:check`。
- `verify:flow --diff` 校验 PR 标题与提交的 `(#N)` 及 scope 覆盖。
- 新测试覆盖单 ref argv、缓存复用、失败分类与清理。

## 非目标

- 不实现代理出网与失效回退。
- 不做 mirror 预热，也不把 `preview/*` 改成异步任务。
- 不改 run workspace 的完整性与推送模型。
