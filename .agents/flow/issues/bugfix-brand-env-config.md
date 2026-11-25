# 品牌名与副标题支持 .env 配置，未配置保持当前文案

[English](bugfix-brand-env-config.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-54
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/issues/bugfix-brand-env-config*
  - .agents/notes/**
  - .env.example
  - apps/api/app/**
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/**
  - tests/e2e/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/08-frontend-implementation.md
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/feature/2026-11-25-brand-env-config.md
github:
  number: 594
  url: https://github.com/Shadow-Azure/harness-evolution/issues/594
```

## 背景

顶栏左上角的品牌区（讨论截图红框）现在固定渲染 `Harness Evolution` 与「轨迹诊断与自进化」：`apps/web/src/components/layout/TopNav.vue` 的品牌链接、`apps/web/src/pages/login/Index.vue` 的登录左栏、`apps/web/src/pages/login/ChangePasswordCard.vue` 的改密卡、`apps/web/index.html` 的 `<title>` 以及品牌链接的 `aria-label` 都是硬编码。部署方换一个站点名只能改源码重新构建。

生产 `.env` 由 systemd 的 `EnvironmentFile=/opt/harness/shared/.env` 注入 API；前端产物在 CI 构建后同步到服务器，构建环境读不到服务器 `.env`。因此“走 `.env` 配置”只能由 API 在运行期读出配置，再通过公开接口交给浏览器；未配置时必须给出与现在完全相同的默认文案。

## 目标

- API 增加两个可选环境变量：`HE_BRAND_NAME`（品牌名，默认 `Harness Evolution`）与 `HE_BRAND_SUBTITLE`（副标题，默认 `轨迹诊断与自进化`）；空串或纯空白视为未配置，回落到默认值。
- 新增公开只读接口 `GET /api/app-config`，返回品牌名与副标题，无需登录；登录页与顶栏共用同一份值。
- Web 在挂载前拉取一次配置，顶栏、登录页、强制改密卡与浏览器 `<title>` 统一使用该配置；接口失败或响应不合法时保持现有默认文案，且不阻塞页面加载。
- 未配置部署的页面文案与 `aria-label` 与当前逐字一致，已有测试仍按当前默认值通过。

## 设计依据

- [05 §4.1 基础端点：健康检查与鉴权](../../../plans/fullstack-design/05-api-design.md#41-基础端点健康检查与鉴权)：公开端点清单与 `/api/health` 的公开边界，`/api/app-config` 沿用同一惯例。
- [08 §4 登录页、强制改密与顶栏用户区](../../../plans/fullstack-design/08-frontend-implementation.md#4-登录页强制改密与顶栏用户区pageslogin)：品牌出现在登录左栏、改密卡与顶栏三处的现状。
- [03 §8.1 分层与清单](../../../plans/fullstack-design/03-frontend-architecture.md#81-分层与清单)：`TopNav.vue` 是全局壳的导览与品牌位。
- [部署 · 配置注入](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md#配置注入)：`.env` 的注入路径与“真实 `.env` 不入仓库”的部署边界。

## 实现内容

### API 与契约

- `Settings` 增加 `brand_name` 与 `brand_subtitle`，默认值即当前文案；before 校验器把空串、纯空白归一到默认值，其余值 strip 后使用。
- 新增 `apps/api/app/api/app_config.py`，`GET /api/app-config` 返回 `{"brand": {"name": ..., "subtitle": ...}}`；响应模型 `extra="forbid"`，路由注册进 `apps/api/app/main.py`。
- `/api/app-config` 加入 `apps/api/app/middleware/auth.py` 的公开路径集合，未登录可读；不新增数据库表、不写审计。
- 契约走生成链：`pnpm contract:generate` 更新 `packages/contracts/openapi.json` 与生成类型，`packages/contracts/src/index.ts` 导出 `AppConfigResponse`。

### 前端装配

- 新增 `apps/web/src/api/appConfig.ts` 与默认常量，负责请求与响应校验；校验失败按默认值处理。
- `bootstrapApp` 在挂载前加载一次品牌配置并写入 Pinia store（或等价单例），同时设置 `document.title = brand.name`；加载失败捕获后继续挂载并保留默认文案。
- `TopNav.vue` 的品牌链接 `aria-label`、`<strong>` 与 `<small>` 改为读取 store；`pages/login/Index.vue` 与 `pages/login/ChangePasswordCard.vue` 的品牌名与副标题同样读取 store，改密卡的「首次登录」文案保持不变。
- `apps/web/index.html` 的 `<title>` 保留 `Harness Evolution` 作为配置加载前默认，加载后由应用覆盖；长品牌名用省略号截断，390px 视口不挤压导航与用户区。

### 配置与文档

- `.env.example` 在“网络与站点”可选组增加 `HE_BRAND_NAME` 与 `HE_BRAND_SUBTITLE` 注释行，写明默认值、空值回退与改后需重启 `harness-api` 生效。
- `plans/fullstack-design/05-api-design.md` 的公开端点清单与 §4.1 补 `GET /api/app-config`；`plans/fullstack-design/08-frontend-implementation.md` §4 的品牌描述改为可由 env 覆盖。
- 按 `.agents/notes/README.md` 新增一条 `implemented/feature/2026-11-25-brand-env-config.md`，记录“API 运行期配置 + 公开端点”相对“构建期 Vite env”和“nginx 注入”的取舍，并把路径回填到本 issue 的 `adr`。

## 实施步骤

1. 在 `apps/api/app/config.py` 落两个字段与归一化测试，覆盖未设置、空串、纯空白与正常值四种输入。
2. 增加 `app_config` 路由、公开路径与 `apps/api/tests/test_app_config.py`（无 token 请求 200，字段值与 `Settings` 一致）；运行 `pnpm contract:generate` 并审查契约 diff。
3. 落前端 API 客户端、store 与 `bootstrapApp` 装配并设置标题；补单测覆盖成功、失败、缺字段三种情况。
4. 把顶栏、登录页、改密卡切换到 store；更新既有硬编码断言，补一条长品牌名与 390px 视口的渲染测试。
5. 更新 `.env.example`、05/08 设计说明与 Agent Note；补一条真实浏览器 E2E 覆盖默认值与配置值。
6. 跑本 issue 的验证命令与截图，PR 说明写清“未配置”与“已配置”两组证据。

## 依赖与交付边界

- 无前置 issue 依赖；不涉及数据库迁移、鉴权模型变化或部署流水线新增 Secret。
- 品牌只在 API 启动时读取一次；改 `.env` 后需要重启 `harness-api`，不做运行期热更新。
- 交付边界是品牌名与副标题文本；品牌标记图形、favicon、登录页能力说明与页脚文案不随 `.env` 变化。

## 独立验证

```sh
pnpm test:api -- tests/test_app_config.py
pnpm test:web
pnpm contract:check
HE_BRAND_NAME='Acme Diagnostics' HE_BRAND_SUBTITLE='Acme Self-Evolution' pnpm test:e2e -- 'brand'
```

- `test_app_config.py`：未设置、空串、纯空白均返回当前默认值，配置值原样返回；无 token 的 `GET /api/app-config` 为 200。
- Web 单测：请求失败时保留默认品牌；配置值渲染到顶栏、登录页与 `<title>`；改密卡品牌名更新而「首次登录」不变。
- E2E：同一构建在默认环境与带 `HE_BRAND_NAME`、`HE_BRAND_SUBTITLE` 的启动参数下，顶栏、登录页与 `document.title` 分别显示当前文案与配置文案；390px 无横向溢出。

## 验收标准

1. 不配置任何新变量时，顶栏、登录页、改密卡、`aria-label` 与浏览器标题与当前逐字一致，既有 E2E 断言无需改名。
2. 配置两个变量并重启后，上述位置显示新品牌名与副标题，`GET /api/app-config` 返回同一对值。
3. 只配置 `HE_BRAND_NAME` 时副标题仍为当前默认；空串与纯空白不会产生空品牌。
4. `GET /api/app-config` 无需登录；接口异常或响应不合法时应用仍可加载，并回落到当前文案。
5. 长品牌名（不少于 24 个字符）在 1408px 与 390px 视口截断或省略，不遮挡导航、用户菜单与 demo 角标。

## 门禁与 CI

- 契约：`pnpm contract:check` 必须无 diff；新增公开路径同步 OpenAPI 快照与生成类型。
- Web/API：`pnpm lint:web`、`pnpm typecheck:web`、`pnpm lint:api`、`pnpm typecheck:api` 与对应测试 job 通过。
- 文档：`.env.example` 与设计说明改动后运行 `pnpm verify:docs`，新增 Agent Note 通过 `pnpm lint:docs`。
- 流程：issue 已激活（in-progress），提交与 PR 标题带 `(#N)`；PR 关联 `Bugfix 问题修复` milestone，合入前运行 `pnpm verify:flow` 与 `pnpm verify:flow-online`。
- UI 变更：PR 描述附同视口、同主题的 before（当前文案）与 after（配置文案）截图，标明基线与候选提交。

## 非目标

- 不把品牌标记图形、favicon、登录页能力说明与页脚替换成可配置内容。
- 不做按工作空间、按角色或按用户的品牌差异，也不做后台品牌设置页。
- 不改顶栏布局、导航、间距或设计 token。
- 不支持运行中热更新品牌配置；改 `.env` 必须重启 API。
