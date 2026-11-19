# Agent Note: 目标内容读取按单 ref 浅拉取

Status: implemented

[English](2026-11-19-single-ref-target-content.en.md) | 中文

## Problem

启动向导把所选版本解析成 body hash 时，`SubprocessGitContent` 先在请求路径里对目标仓库做 `git clone --mirror`，再 `git show` 一个 `SKILL.md` / `AGENT.md`。生产数据目录迁移后缓存为空，国内到 GitHub 的链路在 20 秒内拉不完全量 mirror，用户看到的是「读取目标文件超时」（[issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)）。只读一个 ref 却下载全部历史与所有 ref，既浪费传输量，也把失败窗口放大。出网代理是正交问题，由后续独立任务处理（设计见 [#394](https://github.com/Shadow-Azure/harness-evolution/issues/394)）。

## Decision

- 目标内容缓存从 per-repo mirror 改为 per-(`repo_url`, `ref`) 浅仓库。tag/分支首次读取用 `git clone --depth 1 --single-branch --filter=blob:none --no-checkout --branch <ref>`；完整 40 位 commit 用 `git init` + promisor remote 配置 + `git fetch --depth 1 --filter=blob:none origin <sha>`。后续只 fetch 同一 ref，`git show` 由 promisor remote 按需拉一个 blob；不再使用 `--mirror`。
- 缓存键包含 URL 与 ref，进程内锁按缓存路径串行；ref 缺失、文件缺失、网络、超时、git 不可用与路径越界都保持稳定分类，失败清理半成品目录。
- 保持 `read_file` 接口、20 秒上限与 body hash 语义不变；不引入 GitHub API、私有仓库凭据或公共镜像。旧 mirror 缓存目录留在原处，新布局不读取它们，不做数据迁移。

## Alternatives considered

- **GitHub Contents API / raw.githubusercontent.com 直接取文件。** 需要 token 与配额，私有仓库授权和错误分类另起一套；与现有 git ref 语义（tag/分支/commit）不一致，暂不作为主路径。
- **mirror 预热或把 preview 异步化。** 预热需要部署后后台任务，异步会改 `preview/*` 同步契约与前端；两者都超出本次「只读一个 ref」的修复面，[#391](https://github.com/Shadow-Azure/harness-evolution/issues/391) 已单列。
- **保留全量 mirror，仅调大超时。** 链路本身不稳定，传输量与失败窗口没有下降；单 ref 浅拉取直接减少要传的数据。

## Consequences

- 冷读一个新 ref 仍要联网，但只传该 ref 与按需 blob；tag/分支每次读取刷新一次小 fetch，完整 commit 直接复用缓存。
- 旧 mirror 缓存目录不再被读取，也不会自动清理；它们不影响新布局，可人工删除。
- 出网代理（Secret、Xray 部署、代理环境与熔断）不在本次变更内；代理失效处理与部署是后续独立任务。
- `read_file` 的调用方与错误码保持不变；现有单测与跨栈流程不需要调整契约。
