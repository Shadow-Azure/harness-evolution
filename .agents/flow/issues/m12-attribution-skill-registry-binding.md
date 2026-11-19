# 归因 Skill 注册、版本解析与对象绑定

[English](m12-attribution-skill-registry-binding.en.md) | 中文

```yaml flow
kind: issue
id: m12-25
milestone: m12
depends:
  - m7-07
  - m12-24
priority: P0
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
  number: 320
  url: https://github.com/Shadow-Azure/harness-evolution/issues/320
```

## 背景

平台需要为不同进化对象选择不同归因方法，但当前只有全局 `HE_ATTRIBUTION_ENGINE`，没有归因 Skill 身份、不可变 revision、对象绑定或默认回退。若把 Skill 内容直接塞进 target 或运行请求，历史 Run 无法复现，解绑与回滚也会改变旧报告含义。

## 目标

- 提供平台 Default Attribution Skill、Workspace 默认和对象级覆盖的统一解析顺序。
- 保存不可变 Skill revision、内容 hash、执行器类型和输出 schema 兼容信息。
- 让 Run 和 Probe Report 固化实际生效的 Skill revision，不随当前配置漂移。

## 设计依据

- [06 §5.1–5.2](../../../plans/fullstack-design/06-database-design.md)：进化对象与 Run 快照。
- [05 §4.11](../../../plans/fullstack-design/05-api-design.md)：进化对象配置 API。
- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md)：归因引擎纯函数边界。

## 实现内容

- 建立 Skill definition、不可变 revision 与 target binding 存储；平台 Default Skill 可引用但不可删除。
- 实现 `AttributionSkillResolver`，固定按对象绑定、Workspace 默认、平台默认解析。
- 支持发布、停用、解绑、回滚和删除引用保护；历史 revision 保持只读。
- Skill 只承载受控说明、流程和工具配置，不执行用户上传代码；密钥仍由环境注入。
- 向 Run/归因执行清单写入 effective skill key、revision 与 content hash。

## 实施步骤

1. 写解析优先级、不可变 revision、解绑和引用保护测试。
2. 实现迁移、repository、resolver 与管理 API。
3. 接 Run 创建与归因执行清单快照。
4. 补双库、RBAC、契约与迁移验证。

## 依赖与交付边界

- 依赖：m7-07、m12-24。
- 交付边界：提供注册、revision、解析和绑定后端；完整配置页面由 m12-21 交付。

## 独立验证

```sh
pnpm test:api -- tests/attribution_skills
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
```

- 对象覆盖、Workspace 默认和平台默认依次回退，结果包含稳定 revision 与 hash。
- 被历史 Run 引用的 revision 不可删除，解绑不改变历史快照。

## 验收标准

- 两个对象可绑定不同 Skill revision，并生成互不混用的执行清单和缓存身份。
- 对象解绑后回退到 Workspace 或平台默认；停用 Skill 不影响历史读取。
- 未发布或 schema 不兼容的 revision 不能用于新 Run。

## 门禁与 CI

- API、双库、RBAC、契约、文档与 Flow 门禁。

## 非目标

- 不实现任意代码插件执行、在线 Skill 正文编辑器或外部市场。
- 不调用模型，不组装 Session Trace，不决定归因结论。
