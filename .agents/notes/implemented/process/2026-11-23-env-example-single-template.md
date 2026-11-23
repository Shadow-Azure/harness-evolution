# Agent Note: 生产 .env 模板收敛到根 .env.example

Status: implemented

[English](2026-11-23-env-example-single-template.en.md) | 中文

## Problem

生产 `.env` 由 systemd 的 `EnvironmentFile=` 读取，缺少 `HE_JWT_SECRET` 会让服务拒绝启动，缺少管理员凭据会让首次部署没有可登录账号。`deploy/env.production.example` 按网络、数据、Git 等领域分组，必填与选填混排，操作者必须对照 `apps/api/app/config.py` 才能判断哪些不能留空。用户需要一份必填在前、逐行说明填写内容与作用的 `.env.example`；同时 systemd 不支持变量行尾注释，说明不能直接写在赋值行末尾。

## Decision

仓库根 `.env.example` 是生产 `.env` 的唯一模板，必填字段在前、选填字段在后，每个赋值行的下一行用 `# 必填｜...` 或 `# 选填｜...` 说明值、作用、默认值与约束。`deploy/env.production.example` 删除，部署文档、bootstrap 与 playbook 的模板链接统一指向根模板；`.gitignore` 保留 `.env` / `.env.*` 的忽略规则，只放行 `.env.example`。注释独立成行，模板可直接复制为服务器 `.env` 而不改变任何值。

## Alternatives considered

保留 `deploy/env.production.example` 并在根新增一份说明文件：两份模板会随 Settings 演进漂移，且操作者仍需判断哪份可复制。把必填/选填写在赋值行尾：systemd 会把 `#` 后的文字并入变量值，`HE_HOST`、`HE_DATA_DIR` 等字段会因此校验失败，模板不再可用。用脚本从 `Settings` 生成模板：默认值和字段清单可机械生成，但「为什么必填」「首次部署才需要管理员」与部署注入语义无法从类型推导，仍要维护人工注释。只改旧模板不移动路径：用户明确要 `.env.example`，而且旧路径让模板藏在 `deploy/` 下，不符合仓库根入口的预期。

## Consequences

模板只有一个 home，Settings 增删字段时只需改根 `.env.example` 与部署文档中的链接。历史 `plans/` 检视记录仍可能提到旧路径，它们是过程快照，不参与链接门禁。注释独立成行让模板可直接复制；后续若有人把说明改回行尾注释，systemd 会把注释当成值，必须靠评审阻止。`HE_VERSION` / `HE_PHASE` 等构建元数据未展开，避免把内部健康检查字段误当成部署必填项。
