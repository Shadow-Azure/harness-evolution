# 生产归因绑定静默挂起：补齐运行时前置校验与可见状态

[English](bugfix-attribution-runtime-silent-hang.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-32
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/app/main.py
  - apps/api/app/service/evolution/attribution_skills.py
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - apps/web/src/pages/evolution/targets/**
  - apps/web/src/pages/evolution/components/LaunchWizard*
  - apps/web/src/pages/overview/components/TargetsOverview.vue
  - apps/web/src/pages/overview/components/TargetSideList.vue
  - apps/web/src/pages/overview/Index.test.ts
  - tests/e2e/m5-target-config.test.mjs
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - .env.example
  - plans/**
  - .agents/**
adr: []
github:
  number: 544
  url: https://github.com/Shadow-Azure/harness-evolution/issues/544
```

## 背景

2026-11-23 17:13:08 CST，生产前端把系统默认 `attribute-badcases` 绑定到进化对象 `codespec-subagent-driven-development`（target `01M7Y37ZR7N61GVWMZ31FPN8JY`，workspace `01M7KJ05ENF9784GPBDV544VB0`）。PUT 返回 200，目标行的 `attribution_package_id=default-attribute-badcases`、`attribution_generation=01M83TWE7ZSTC6Z5MNF0P0KQDM`、`attribution_due=attribution_cutoff=2026-11-23 17:13:08`。到 17:39（DB `NOW()` 17:39:51）仍是 `attribution_owner=NULL`、`attribution_failures=0`、`attribution_error=NULL`、`updated_at=17:13:08`；没有 claim，也没有失败重试。服务在 17:36 重新发布到 `065a96ae` 后状态完全不变。

### 问题描述

绑定请求成功、目标行也已写入 `attribution_due`，但后台没有任何消费者领取。25 分钟后仍无 owner、无失败、无报告、无重试；目标页只显示“已绑定”，用户无法从列表或详情判断归因是否在运行。生产机没有 `HE_ATTRIBUTION_AGENT`，也没有 bubblewrap，因此即使只补开关，批次也会在 claim 后失败并消耗绑定。该对象实际有 22 条待处理 Badcase，不是数据为空。

### 根因定位过程

1. **确认绑定与排队状态**：17:13:08 PUT 返回 200；DB 中 package、generation、due、cutoff 均已写入；到 17:39 仍是 `owner=NULL`、`failures=0`、`error=NULL`、`updated_at=17:13:08`，说明不是 worker 执行失败，而是从未被 claim。
2. **确认消费者是否启动**：`apps/api/app/main.py` 的 lifespan 只在 `resolved_settings.attribution_agent` 非空时调用 `binding_worker.start()`；`/opt/harness/shared/.env` 与 `harness-api` 进程环境都没有 `HE_ATTRIBUTION_AGENT`，release 目录没有本地 `.env`；`config.py` 默认 `None`，`.env.example` 明确“留空关闭本地归因”。
3. **确认是否有实际产出**：`attribute/<workspace>/` 下只有 `attribute_source` / `attribute_skill`，没有 `attribute_input` / `attribute_output`，也没有 generation `01M83TWE...` 的批次目录；journal 没有该 worker 的日志。
4. **确认数据面是否为空**：22 个 session 含 `codespec-subagent-driven-development` 的 skill 事件，各有 1 条 `discovery` Badcase（共 22 条，均早于 cutoff）；关联数据存在，修复后不需要重新绑定。
5. **确认运行时前置**：服务器 `dpkg` 无 bubblewrap、`bwrap` 不在 PATH、服务账号 `shutil.which("bwrap")` 为 `None`；`apps/api/app/third_party_api/ai_agent/claude_skill.py` 在 Linux 缺 bwrap 会抛 `attribution requires bubblewrap on Linux`。只加 `HE_ATTRIBUTION_AGENT=provider` 会让批次 claim 后失败，3 次后 `attribution_due=NULL`，绑定被消耗。
6. **确认 UI 可见性**：目标页只有编辑弹窗里的一句提示，列表/详情没有持续状态；服务在 17:36 重新发布到 `065a96ae` 后 due/owner 状态完全不变，说明不是一次性请求失败。

### 结论

- 直接原因：生产未启用归因运行时（`HE_ATTRIBUTION_AGENT` 缺失），`BindingWorker` 从未启动；绑定任务一直停在队列。
- 第二阻塞：服务器缺 bubblewrap；即使只补开关，第一批也会失败并消耗重试。
- 放大因素：UI 只在编辑弹窗提示，绑定后没有持续状态；用户看到“已绑定”会误以为已开始。
- 非根因：绑定写入、generation/due 生成、对象匹配与 22 条 Badcase 数据都正常；不是绑定 API 或数据面缺陷。
- 修复方向采用 #542 的公共 Provider 方案。绑定消费者、重算和发布检查直接使用同一工厂选择，Linux Claude 在领取前验证 bubblewrap 能实际启动隔离进程。

## 目标

空间中的 Skill 绑定应能在依赖恢复后自动执行。目标配置与对象总览持续显示暂停状态。运维能从启动和发布日志区分 Provider 能力不足、缺少 bubblewrap 与权限受限。

## 设计依据

- [07 §5.5.1 AI Agent Provider 出站适配层](../../../plans/fullstack-design/07-backend-implementation.md) 定义公共 Provider、模型设置及 Skill 执行能力。
- [07 §5.13 归因生成与缓存](../../../plans/fullstack-design/07-backend-implementation.md) 定义绑定代次、租约及报告写入。[对象绑定归因](../../../plans/fullstack-design/02-features.md#对象绑定归因) 定义后台与向导的用户行为。

## 实现内容

- API 与发布程序通过公共工厂读取 `AI_AGENT_PROVIDER`，默认 `claude-code`。模型、CLI 和凭据沿用该 Provider 的配置。兼容历史部署时忽略旧归因开关。
- API 记录 `attribution.preflight`。缺少 bubblewrap 记录 `ATTRIBUTION_BWRAP_MISSING`，无法启动命名空间记录 `ATTRIBUTION_BWRAP_UNUSABLE`，缺少 Skill 能力记录 `ATTRIBUTION_PROVIDER_UNSUPPORTED`。预检结果控制 `runtimeEnabled`、`canRecompute` 和绑定消费者。暂停时可保存绑定、查看历史和复用报告。
- 发布脚本在迁移与切换 `current` 前用候选 API 检查同一 Provider。Linux Claude 沙箱异常中止发布并恢复备份环境。显式选 `fake` 的部署可发布并读缓存。API 进程以服务账号再次检查。
- 对象配置和总览在能力为 false 时持续提示，已绑定对象带“归因未运行”标记。编辑弹窗和向导提示与后台一致。

## 实施步骤

1. 实现公共能力预检，接入 API、绑定消费者、向导和发布流程。
2. 更新两个前端入口、部署说明与配置模板，覆盖暂停、恢复和正常显示。
3. 在隔离环境验证原批次恢复及发布失败时的旧版本。生产部署后由运维核对原代次与报告。

## 依赖与交付边界

复用现有绑定、快照、公共 AI Agent 配置与包列表契约。系统管理员负责安装 bubblewrap 和提供服务账号可用的命名空间。生产验收独立于合成数据验证。

## 独立验证

```sh
pnpm test:api -- --serial tests/test_attribution_preflight.py tests/m5-05-launch-wizard/test_launch_api.py::test_startup_claims_existing_binding_with_shared_provider
pnpm test:web
pnpm test:e2e --pattern 'm5 target configuration'
bash -n deploy/release.sh
```

在同一临时 SQLite 创建 22 个合成 Session，各上报一条 discovery，绑定默认包。模拟 Linux 缺少 bwrap 后 owner 为空、due 保留、失败为零。恢复具备 Skill 能力的测试 Provider 并重启，核对原代次的 22 份报告、绑定 Skill 与逐条日志。临时 release 脚本覆盖缺工具、工具不可用、工具可用与仅缓存部署。

## 验收标准

- 前置异常时没有 claim 或失败重试，两个页面均展示暂停状态。已有绑定保留，历史报告可复用。
- 缺失或不可执行的沙箱让发布在迁移前失败，当前 release 继续服务。
- 生产恢复后原 generation `01M83TWE7ZSTC6Z5MNF0P0KQDM` 自动处理原有 22 条 Badcase，按代次和 Skill 对照入库报告、目标页与落盘结果。

## 门禁与 CI

执行 API/Web 测试、lint 与 typecheck、浏览器集成、`pnpm verify:docs`、`pnpm verify:flow`、`pnpm test:gates` 和发布脚本预检测试。

## 非目标

绑定租约、重试次数、报告格式与既有 Skill 沙箱策略遵循现有协议。主机软件安装和生产数据核对由运维完成。
