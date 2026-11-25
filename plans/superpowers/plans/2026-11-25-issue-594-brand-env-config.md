# 品牌名与副标题 .env 配置实现计划（#594）

> **For agentic workers:** this plan follows the superpowers task-by-task style; the linked issue `.agents/flow/issues/bugfix-brand-env-config.md` is the implementation contract. Every interactive question is answered from `plans/fullstack-design`, not by asking the user.

**Goal:** 让部署方通过服务器 `.env` 的 `HE_BRAND_NAME` / `HE_BRAND_SUBTITLE` 覆盖顶栏、登录页、强制改密卡与浏览器标题的品牌文案，未配置、空串或纯空白时逐字保持当前 `Harness Evolution` / 「轨迹诊断与自进化」。

**Architecture:** 生产 `.env` 只进入 API（systemd `EnvironmentFile`），Web 产物在 CI 构建，因此品牌事实由 API 在启动时读入 `Settings`，经公开只读端点 `GET /api/app-config` 交给浏览器。Web 在 `bootstrapApp` 挂载前拉取一次并写入 Pinia `appConfig` store，`document.title` 由 store 在 `finally` 写入，任何失败都回落到 `DEFAULT_BRAND` 且不阻塞挂载。契约走 FastAPI OpenAPI → `packages/contracts/openapi.json` → `api.d.ts` 的生成链。

**Scope:** `apps/api/app/config.py`、`apps/api/app/api/app_config.py`（新增）、`apps/api/app/main.py`、`apps/api/app/middleware/auth.py`、`apps/api/tests/test_app_config.py`（新增）、`apps/api/tests/test_openapi.py`、`packages/contracts/**`、`apps/web/src/api/appConfig.ts`（新增）、`apps/web/src/stores/appConfig.ts`（新增）、`apps/web/src/bootstrap.ts`、`apps/web/src/components/layout/TopNav.vue`、`apps/web/src/pages/login/Index.vue`、`apps/web/src/pages/login/ChangePasswordCard.vue`、`apps/web/index.html`、对应 `*.test.ts`、`tests/e2e/m12-14-brand-config.test.mjs`（新增）、`.env.example`、`plans/fullstack-design/05-api-design.md`、`plans/fullstack-design/08-frontend-implementation.md`、`plans/**`、`.agents/flow/issues/bugfix-brand-env-config*`、`.agents/notes/implemented/feature/2026-11-25-brand-env-config*`。

## 交互问题的设计答案

| 问题 | 答案来源 | 决定 |
|---|---|---|
| 品牌配置放构建期还是运行期？ | issue 背景（CI 构建读不到服务器 `.env`）+ [05 §4.1](../../fullstack-design/05-api-design.md#41-基础端点健康检查与鉴权) | 运行期：API `Settings` 读 `HE_BRAND_*`，公开端点下发；不做 Vite 构建期注入 |
| 端点路径、方法与负载？ | issue「实现内容」+ 05 §4.1 公开端点惯例 | `GET /api/app-config` → `{"brand":{"name":...,"subtitle":...}}`，与 `/api/health` 同为公开 |
| 是否需要登录或审计？ | 05 §4.1 `/api/health` 公开边界 + issue 非目标 | 公开、只读；不写库、不写审计 |
| 响应模型要不要严格？ | [05 §1 约定](../../fullstack-design/05-api-design.md#1-总则) 与既有 `HealthResponse` | Pydantic 模型 `extra="forbid"`，与 health 一致 |
| 未设置 / `None` / 空串 / 纯空白如何取值？ | issue 验收 1、3 | before validator 统一归一为默认值；真实值 strip 后使用，不产生空品牌 |
| 只配置品牌名时副标题是什么？ | issue 验收 3 | 仍为默认「轨迹诊断与自进化」；两个字段彼此独立 |
| Web 何时拉取、拉几次？ | issue「前端装配」 | `bootstrapApp` 在 `app.use(pinia)` 之后、`app.mount` 之前加载一次；store 用单例 promise 防止重复请求 |
| 接口失败或响应不合法怎么办？ | issue 验收 4 | 保留 `DEFAULT_BRAND`，照常挂载，不抛错、不阻塞页面 |
| 谁写 `document.title`？ | issue「前端装配」+ `apps/web/index.html` 现状 | store 在 `finally` 写 `document.title = brand.name`（`typeof document !== "undefined"` 守卫）；`index.html` 保留 `Harness Evolution` 作为加载前默认 |
| 哪些位置改为读 store？ | [08 §4.1](../../fullstack-design/08-frontend-implementation.md#41-登录页与强制改密) | `TopNav.vue` 的品牌链接 `aria-label`/`<strong>`/`<small>`、`pages/login/Index.vue` 的登录左栏、`pages/login/ChangePasswordCard.vue` 的品牌名；改密卡「首次登录」逐字不变 |
| 长品牌名怎么处理？ | issue 验收 5 + [08 §4.1](../../fullstack-design/08-frontend-implementation.md#41-登录页与强制改密) 的 390px 约束 | `.brand-copy` `min-width:0` + 有界 `max-width`，strong/small 省略号；1408px 与 390px 不遮挡导航、用户区与 demo 角标 |
| 是否改顶栏布局、导航、间距或 token？ | issue 非目标 | 不改；只在品牌容器内加截断约束，保留 640/1100/1500 断点 |
| 品牌标记、favicon、能力说明、页脚是否可配？ | issue 非目标 | 不变；交付边界只是品牌名与副标题文本 |
| 支持热更新吗？ | issue「依赖与交付边界」 | 不支持；改 `.env` 必须重启 `harness-api`，文档写明 |
| 契约怎么同步？ | 根 `AGENTS.md` 契约源规则 + issue 门禁 | 先改 FastAPI，再 `pnpm contract:generate`，提交 `openapi.json`、`api.d.ts` 与 fixture；`index.ts` 导出 `AppConfigResponse` |
| 默认文案的既有断言要不要改？ | issue 验收 1 | 不弱化；默认场景必须与当前逐字一致，新增测试只加配置态断言 |
| 浏览器 E2E 怎么证明？ | issue「独立验证」 | 同一构建用带 `HE_BRAND_*` 的 API 启动，断言无鉴权接口、登录页文案、`document.title`、1408/390 无横向溢出与品牌截断 |

### Task 1: API 设置与归一化

**Files:** Modify `apps/api/app/config.py`; create `apps/api/tests/test_app_config.py`.

- [ ] `Settings` 增加 `brand_name: str = "Harness Evolution"` 与 `brand_subtitle: str = "轨迹诊断与自进化"`。
- [ ] before validator 覆盖 `brand_name` / `brand_subtitle`：`None`、空串、纯空白 → 默认值；真实值 strip 后返回，不改其他设置。
- [ ] 测试覆盖未设置、空串、纯空白、只配置一个、正常值带首尾空格五种输入。

### Task 2: 公开端点与公开路径

**Files:** Create `apps/api/app/api/app_config.py`; modify `apps/api/app/main.py`、`apps/api/app/middleware/auth.py`.

- [ ] 新增 `GET /api/app-config`，响应模型 `extra="forbid"`，从 `request.app.state.settings` 读取两个字段。
- [ ] 路由注册进 `create_app`，`/api/app-config` 加入 `_PUBLIC_API_PATHS`。
- [ ] `test_app_config.py` 增加无 token 请求返回 200 且字段值与 `Settings` 一致的用例。

### Task 3: 契约生成与导出

**Files:** Modify `packages/contracts/openapi.json`、`packages/contracts/src/generated/api.d.ts`、`packages/contracts/src/index.ts`、`apps/api/tests/test_openapi.py`、按生成结果同步 fixture。

- [ ] `test_openapi.py` 的精确 path 集合加入 `/api/app-config`，schema 断言加入 `AppConfigResponse`。
- [ ] `pnpm contract:generate`，审查并提交生成 diff（含 fixture 变化）。
- [ ] `packages/contracts/src/index.ts` 导出 `AppConfigResponse`，带 JSDoc 说明。

### Task 4: Web API 客户端与 store

**Files:** Create `apps/web/src/api/appConfig.ts`、`apps/web/src/stores/appConfig.ts`; create `apps/web/src/api/appConfig.test.ts`、`apps/web/src/stores/appConfig.test.ts`.

- [ ] `DEFAULT_BRAND = { name: "Harness Evolution", subtitle: "轨迹诊断与自进化" }` 与 `fetchAppConfig()`；复用 `./http` 的 `request`。
- [ ] 严格运行期校验：`brand` 必须是对象，`name` / `subtitle` 都是非空字符串；否则抛 `ApiError(..., "INVALID_RESPONSE")`。
- [ ] Pinia setup store：`brand` 默认 `DEFAULT_BRAND`，`load()` 只请求一次，成功覆盖、失败保留默认，`finally` 写 `document.title`，永不抛出。
- [ ] 单测：客户端成功、缺字段、空白字段、非 JSON/网络失败；store 成功更新 brand 与 title、失败保留默认与 title、不抛错。

### Task 5: 启动装配与组件切换

**Files:** Modify `apps/web/src/bootstrap.ts`、`apps/web/src/components/layout/TopNav.vue`、`apps/web/src/pages/login/Index.vue`、`apps/web/src/pages/login/ChangePasswordCard.vue`；extend `apps/web/src/bootstrap.test.ts`、`TopNav.test.ts`、`pages/login/Index.test.ts`、`pages/login/ChangePasswordCard.test.ts`.

- [ ] `BootstrapAppOptions` 增加可注入 `loadAppConfig?: () => Promise<void>`，默认调用 store `load()`；在 `app.use(pinia)` 之后、mount 之前 await。
- [ ] `TopNav.vue` 品牌 `aria-label`、`<strong>`、`<small>` 读 store；`.brand-copy` 加 `min-width:0`、有界 `max-width` 与 strong/small 省略号，保留既有断点。
- [ ] `Index.vue` 品牌名/副标题读 store，加 `min-width:0` 与省略号；其余文案与布局不变。
- [ ] `ChangePasswordCard.vue` 品牌名读 store，「首次登录」逐字不变，加省略号安全 CSS。
- [ ] 单测：bootstrap 证明配置在 mount 前加载；TopNav 配置态 `<strong>`/`<small>`/完整 `aria-label` 与长品牌源码 CSS 约束；登录页与改密卡配置态渲染；不弱化默认断言。

### Task 6: 浏览器 E2E

**Files:** Create `tests/e2e/m12-14-brand-config.test.mjs`.

- [ ] 标题含 “brand”，`pnpm test:e2e -- brand` 能选中；seed + API 启动注入 `HE_BRAND_NAME`（≥24 字符）与 `HE_BRAND_SUBTITLE`，再起 Vite。
- [ ] 断言无鉴权 `GET /api/app-config` 返回配置对；登录页渲染配置名/副标题且 `document.title === 配置名`。
- [ ] 1408px 与 390px：`scrollWidth === clientWidth`，品牌 `clientWidth <= scrollWidth` 且 `getBoundingClientRect` 在视口内；尽量完成登录/改密以断言顶栏品牌，若 seed 流程成本过高则记录到 PR 说明。
- [ ] Windows 用 `shell: process.platform === "win32"` 起 pnpm；不提交截图。

### Task 7: 文档、配置与 Note

**Files:** Modify `.env.example`、`plans/fullstack-design/05-api-design.md`、`plans/fullstack-design/08-frontend-implementation.md`; create `.agents/notes/implemented/feature/2026-11-25-brand-env-config.{md,en.md,i18n.yaml}`.

- [ ] `.env.example`「网络与站点」加注释版 `HE_BRAND_NAME` / `HE_BRAND_SUBTITLE`，写明默认值、空/空白回退与「改后需重启 harness-api 生效」。
- [ ] 05 端点清单与 §4.1 补公开 `GET /api/app-config` 与负载；08 §4.1 注明品牌/副标题可由 env 覆盖且默认不变。
- [ ] Agent Note 三件套：`Status: implemented`，Problem / Decision / Alternatives considered / Consequences，记录 API 运行期配置 + 公开端点相对构建期 Vite env 与 nginx 注入的取舍，以及重启生效。
- [ ] `pnpm record:i18n` 重录 Note 与 flow issue。

### Task 8: 流程与验证

**Files:** Modify `.agents/flow/issues/bugfix-brand-env-config.md` 与 `.en.md`.

- [ ] 两侧 yaml fence 逐字节一致：`status: ready → in-progress`、`scope` 加 `plans/**`、`adr: ../../notes/implemented/feature/2026-11-25-brand-env-config.md`。
- [ ] 运行 `pnpm test:api -- tests/test_app_config.py tests/test_openapi.py`、`lint:api`、`typecheck:api`、`test:web`、`lint:web`、`typecheck:web`、`contract:check`、`verify:flow`、`lint:docs`、`verify:docs`、`test:gates`、`test:e2e -- brand`，记录实际结果。
