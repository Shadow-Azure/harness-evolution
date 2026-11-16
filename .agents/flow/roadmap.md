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
  - m7
  - m8
  - m9
  - m10
  - m11
  - m12
```

## 愿景

Harness Evolution 用可回链的 Claude Code 轨迹、外部问题与归因数据，驱动组织内 coding agent 的诊断和自进化改进。V2 以工作空间为数据与权限边界，并把真实轨迹证据、对象归因和自进化执行链连成可解释闭环。

## Milestone 序列

- **m1 工程骨架与质量门禁**：FastAPI、Vue 3、双方言存储、契约、鉴权、任务/SSE 与 CI 元门禁。
- **m2 轨迹数据与归一化**：fixtures、本地数据导入、归一化、Agent 树、幂等、会话 API 与调度。
- **m3 会话浏览与执行流**：列表、概览、Agent 执行流图、深链与性能预算。
- **m4 问题与归因**：V1 bad_case/probe、问题卡、错误详情与只读归因。
- **m5 自进化闭环**：配置、运行、六步、事件、git candidate 与占位 patch/评测。
- **m6 真实接入与兑现**：真实上游、外部契约、真实执行和聚类升级。
- **m7 身份与空间边界**：唯一全局管理员、空间成员角色、鉴权接入缝、空间路由与管理。
- **m8 空间数据面与总览**：空间上报、额度、最新 Session、总览和时间分页。
- **m9 Session 证据与对象版本**：runtime 身份、parser 工厂、关系、完成状态、revision、定义/文件证据、触发坐标与知识库文档证据。
- **m10 归因管线与七步自进化**：潜在匹配、缓存、候选、四步向导和七步运行。
- **m11 多归因体验与 V2 切换**：lane DAG 执行流、多归因详情、对象总览、跨栈验收与兼容退役。
- **m12 真实接入与算法兑现**：真实上游、契约联调、patch/评测、聚类升级与平台质量欠账。

## 实施规则

- 每个 issue 以 `plans/fullstack-design` 的链接章节为技术权威；M9 证据门禁先于 M10 潜在匹配与归因。
- 每个 issue 合并前运行全仓静态门禁和聚焦验证；新增门禁必须有自测试并更新路由。
- CI 使用合成或脱敏 fixtures；原始 Session、用户 prompt、文档正文和生产凭据不得进入仓库。
- 远端流程对象只关闭不删除；`pnpm flow:sync -- --retire-missing` 是唯一退休入口。
