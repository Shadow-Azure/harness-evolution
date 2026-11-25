# Linux 归因默认使用 bubblewrap，支持通过服务环境切换为单条证据工具

[English](bugfix-attribution-runtime-mode.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-55
milestone: bugfix
depends:
  - bugfix-32
priority: P2
status: ready
scope:
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/pyproject.toml
  - apps/api/tests/**
  - apps/web/src/pages/evolution/targets/components/AttributionRuntimeNotice.vue
  - .env.example
  - attribute/README*
  - docs/deployment*
  - plans/deploy-aliyun-playbook.md
  - plans/fullstack-design/02-features.md
  - .agents/notes/implemented/**
  - .agents/flow/issues/bugfix-attribution-runtime-mode*
adr:
  - ../../notes/implemented/architecture/2026-11-17-attribution-agent-executor.md
github:
  number: 595
  url: https://github.com/Shadow-Azure/harness-evolution/issues/595
```

## 背景

已有 Linux 主机可能缺少 bubblewrap，默认 Claude Provider 会在发布和领取归因批次前报告缺包。服务管理员需要在保留现有装机流程的前提下为这些主机选择执行方式。相关预检见 #544。

## 目标

让服务 `.env` 为绑定归因和向导重算选择同一种执行方式。默认继续使用 bubblewrap。

## 设计依据

两个入口共用 Provider、模型、冻结的输入和同一份报告协议。[对象绑定归因](../../../plans/fullstack-design/02-features.md#对象绑定归因)

## 实现内容

公共 Claude Provider 读取 `HE_ATTRIBUTION_BWRAP_ENABLED`。Linux 默认在 bubblewrap 中运行冻结的 Skill。显式设置 `false` 时，Claude 通过 `read_evidence` 读取当前 Badcase 和 Skill 资料，通过 `write_probe_report` 调用平台报告脚本。

## 实施步骤

1. 将服务配置传给 Provider 的预检与单条 Skill 执行入口。
2. 为单条证据工具限制可读文件，由平台固定报告身份和输出路径，并验证写入回执。
3. 在启动日志和每条归因日志中记录实际模式，校验两个入口的结果。

## 依赖与交付边界

发布脚本已在数据库迁移前导出服务 `.env` 并执行 Python 预检。主机初始化和系统包安装沿用 `main` 的部署流程。

## 独立验证

```sh
pnpm test:api:serial -- tests/test_attribution_preflight.py tests/attribution/test_case_tools.py
pnpm test:api:serial -- tests/m5-05-launch-wizard/test_launch_api.py::test_startup_claims_existing_binding_with_shared_provider tests/m5-05-launch-wizard/test_launch_api.py::test_local_attribution_from_wizard_to_cluster
```

测试使用临时 SQLite、合成 Badcase 和离线 Claude CLI。缺包时默认模式保留待领取的绑定，显式关闭后可恢复原代次并写入报告。

## 验收标准

- 未设置或显式开启时，缺包和命名空间探针失败分别报告对应错误。
- 显式关闭时，绑定归因和向导重算都能读取本条证据，经平台脚本生成报告并入库。日志记录 `case-tools`。
- PR 与 `main` 的 `deploy/` 文件树完全一致。

## 门禁与 CI

API 回归覆盖发布预检、绑定、向导和聚类。Ubuntu 的 `deploy-contract` 验证真实缺包与安装后的行为。

## 非目标

主机装包策略、报告格式、缓存选择和对象绑定规则由各自现有契约维护。
