# Roadmap

[English](roadmap.en.md) | 中文

```yaml flow
kind: roadmap
milestones:
  - m1
  - m2
  - m3
  - m4
  - m5
  - m6
```

## 愿景

Harness Evolution 用可回链的 Claude Code 轨迹、外部问题与归因数据，驱动组织内 coding agent 的诊断和自进化改进。交付遵循 `plans/fullstack-design` 的 SaaS 边界，不恢复时间线页面。

## Milestone 序列

- **m1 工程骨架与质量门禁**：FastAPI、Vue 3、双方言数据基座、契约、鉴权、任务/SSE 和 CI 元门禁。
- **m2 轨迹数据与归一化**：fixtures、本地真实数据导入、归一化、Agent 树、幂等、会话 API 与调度。
- **m3 会话浏览与执行流**：列表、概览、Agent 执行流图、深链与性能预算。
- **m4 问题与归因**：外部只读 bad_case/probe 贯穿 API、执行流问题卡和错误详情。
- **m5 自进化闭环**：配置、运行、六步、事件、真实 git candidate 与占位 patch/评测自动闭环。
- **m6 真实接入与兑现**：真实上游、外部契约、真实 patch/评测和聚类升级。

## 实施规则

- 每个 issue 以 `plans/fullstack-design` 链接章节为技术权威；issue 只定义切片、步骤、验证和边界。
- 每个 issue 合并前运行全仓静态门禁和聚焦验证；新增门禁必须有自测试并更新路由。
- CI 使用合成 fixtures；`claude-code-sessions/` 与 `data/` 只保留在本地，禁止提交或写入 issue 正文。
- 远端流程对象只关闭不删除；`pnpm flow:sync -- --retire-missing` 是唯一退休入口。
