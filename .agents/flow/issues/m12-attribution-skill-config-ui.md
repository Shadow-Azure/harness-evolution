# 对象归因 Skill 配置 API、页面与运行快照

[English](m12-attribution-skill-config-ui.en.md) | 中文

```yaml flow
kind: issue
id: m12-21
milestone: m12
depends:
  - m12-06
  - m12-25
  - m12-19
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 319
  url: https://github.com/Shadow-Azure/harness-evolution/issues/319
```

## 背景

对象级归因 Skill 只有在用户能看到当前生效来源、选择 revision、解绑回退并在 Run 中确认快照时才是完整产品能力。仅提供后端绑定会让管理员依赖数据库操作，也容易把 Workspace 默认、对象覆盖和历史 Run 使用版本混为一谈。

## 目标

- 在进化对象配置 API 和页面中提供 Attribution Skill 绑定管理。
- 在启动向导与 Run 详情展示实际生效的 Skill 来源、revision 与缓存影响。
- 保持历史 Run 快照只读，不随当前对象配置更新。

## 设计依据

- [08 §9.5](../../../plans/fullstack-design/08-frontend-implementation.md)：进化对象配置页。
- [05 §4.11、§4.19–4.20](../../../plans/fullstack-design/05-api-design.md)：对象配置、归因和 Run API。
- [06 §5.1–5.2](../../../plans/fullstack-design/06-database-design.md)：对象与 Run 快照。

## 实现内容

- 扩展 target DTO，返回 effective Skill、binding source、revision、状态和兼容性。
- 配置页支持使用默认、绑定 revision、回滚和解绑；只有 Workspace admin 可写。
- 向导范围/归因预览展示 effective Skill 和缓存将失效/复用的解释。
- Run 卡与归因详情展示实际快照，不读取当前绑定覆盖历史。
- 与 m12-06 的 git/字段诊断共用错误呈现，避免同页两套错误模型。

## 实施步骤

1. 先写 API/RBAC 与组件交互测试。
2. 扩展 target、preview 和 Run DTO。
3. 实现配置页绑定、回退和只读快照展示。
4. 补 E2E、键盘可访问性、空态和冲突错误。

## 依赖与交付边界

- 依赖：m12-06、m12-25、m12-19。
- 交付边界：选择和展示已发布 Skill revision；不在浏览器中编辑或发布 Skill 正文。

## 独立验证

```sh
pnpm test:api -- tests/attribution_skills
pnpm test:web
pnpm typecheck:web
pnpm test:e2e -- --pattern attribution-skill
```

- 管理员可绑定、回滚、解绑；成员只读，viewer 不能写。
- 历史 Run 始终显示启动时的 effective Skill revision。

## 验收标准

- 页面明确区分对象覆盖、Workspace 默认和平台默认。
- 不兼容、未发布或停用 revision 不能用于新 Run，并返回可操作错误。
- 修改绑定后预览缓存数按新执行清单重新计算。

## 门禁与 CI

- API、Web、类型、E2E、无障碍、契约、文档与 Flow 门禁。

## 非目标

- 不实现 Skill 正文编辑、上传任意代码、外部市场或模型凭据管理。
- 不修改归因算法、Session 匹配或聚类。
