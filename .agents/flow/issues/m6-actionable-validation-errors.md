# 交互校验错误精准提示与修复建议

[English](m6-actionable-validation-errors.en.md) | 中文

```yaml flow
kind: issue
id: m6-21
milestone: m6
depends: []
priority: P1
status: ready
scope:
  - apps/api/app/errors.py
  - apps/api/app/api/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 191
  url: https://github.com/Shadow-Azure/harness-evolution/issues/191
```

## 背景

列表筛选、会话同步、自进化向导、run 重试和目标配置等交互都会触发接口校验或领域校验。当前部分页面只展示 `request validation failed`、英文后端短语或一句通用失败提示，用户难以判断是哪个输入越界、权限不足、资源冲突还是服务暂时不可用，也不知道下一步该改什么。

后端统一错误信封已经返回稳定 `code` 与 `details`，但前端缺少统一的可操作错误呈现层；不同 catch 块各自回退到简短文案，导致同类 422 在不同交互里质量不一致。

## 目标

- 为共享 API 错误提供统一格式化入口，优先使用稳定错误码、字段路径和校验详情生成本次操作相关文案。
- 对常见 422 校验失败输出中文原因和建议；无详情时保留明确的操作场景文案与重试建议，不展示内部英文短语或堆栈。
- 关键交互（登录/改密、自进化向导、run 重试、目标配置保存）在同一轮中验证可读、可定位的错误提示。
- `ApiError.details` 呈现保持脱敏，不泄露提交内容、内部路径、凭据或服务端堆栈。

## 设计依据

- [05 接口设计 §4.1](../../../plans/fullstack-design/05-api-design.md)：统一响应与错误信封契约。
- [08 前端实现 §2.2](../../../plans/fullstack-design/08-frontend-implementation.md)：`api/http.ts` 负责 `ApiError` 与统一错误详情传递。
- [08 前端实现 §9](../../../plans/fullstack-design/08-frontend-implementation.md)：自进化向导的前置校验与失败停留策略。

## 实现内容

- 新增 `formatApiError` / `formatValidationDetails` 展示层工具，按 `code`、`status`、`details.errors[].loc/msg/type` 归纳字段级原因和建议。
- 全局 query fallback 不再只处理 409；对 422 与业务错误使用同一格式化入口，业务页已有定制文案优先保留。
- 将目标配置、自进化向导、run 重试和登录/改密的裸 `error.message` 展示替换为共享格式化结果；已有稳定错误码分支保留。
- 后端 `RequestValidationError` 的 `details.errors` 保留 `loc/msg/type`，补充可安全展示的字段路径语义；契约类型保持 additive。
- 为错误格式化与关键页面失败态补前端单测；为 422 信封补 API 集成测试。

## 实施步骤

1. 先写共享错误格式化的失败测试，覆盖校验详情、无详情、网络、权限、冲突和服务错误。
2. 实现统一格式化工具，并接入全局 query fallback 与目标配置、向导、run 重试、登录/改密页面。
3. 为 FastAPI 422 响应补集成断言，必要时同步生成契约。
4. 运行前后端 lint、typecheck、聚焦单测、契约与流程文档门禁。

## 依赖与交付边界

- 依赖：无
- 非目标：<待补>
- 交付边界：只统一已有错误信封的展示语义；不重构页面架构、不改变稳定错误码、不新增外部依赖。
- 兼容：旧响应缺少 `details` 时必须回退；`#185` 继续负责进化对象配置的 `REPO_INVALID` 字段级专项。

## 独立验证

```sh
pnpm test:api -- tests/api
pnpm --filter @harness/web exec vitest run src/app src/pages/evolution src/pages/login
pnpm lint:api
pnpm lint:web
pnpm typecheck:api
pnpm typecheck:web
pnpm contract:check
pnpm verify:flow
pnpm verify:docs
```

- 422 fixture 返回字段定位、中文原因和修改建议；无详情响应回退到“请检查输入后重试”。
- 500、403、409、网络错误分别呈现等待/联系管理员、权限、冲突与网络建议，不暴露内部英文短语。
- 页面失败态测试证明错误出现在对应交互区域且不再出现裸 `request validation failed`。

## 验收标准

- 所有关键交互的接口校验失败都至少包含：发生了什么、哪个输入或操作需要修改、建议下一步。
- 422 详情中的字段路径被映射为用户可读字段名；未知字段路径仍能给出通用输入检查建议。
- 共享格式化工具的分支覆盖率纳入现有前端门禁，新增与更新测试全部通过。

## 门禁与 CI

- API/Web lint、typecheck、单测、契约校验进入 CI；覆盖率不低于 80%。
- `verify:flow --diff main` 校验 PR 标题包含远端 issue 编号且 diff 落在 scope 内。

## 非目标

- 不把原始异常、堆栈、服务器路径或请求体回显给用户。
- 不实现 `REPO_INVALID` 的 git 输出诊断；该项由 `#185` 处理。
- 不新增全局弹窗拦截所有错误；页面内联错误与用户主动操作上下文优先。
