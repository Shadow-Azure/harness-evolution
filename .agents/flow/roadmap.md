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
  - m13
  - m14
  - m15
  - m16
  - m17
  - m18
  - m19
  - m20
  - m21
  - m22
  - m23
```

## 愿景

Harness Evolution 用可回链的 Claude Code 轨迹、外部问题与归因数据，驱动组织内 coding agent 的诊断和自进化改进。V2 以工作空间为数据与权限边界，并把真实轨迹证据、对象归因和自进化执行链连成闭环。

## Milestone 序列

- **m1 工程骨架与质量门禁**：FastAPI、Vue 3、双方言存储、契约、鉴权、任务/SSE 与 CI 元门禁。
- **m2 轨迹数据与归一化**：fixtures、本地数据导入、归一化、Agent 树、幂等、会话 API 与调度。
- **m3 会话浏览与执行流**：列表、概览、Agent 执行流图、深链与性能预算。
- **m4 问题与归因**：V1 bad_case/probe、问题卡、错误详情与只读归因。
- **m5 自进化闭环**：配置、运行、六步、事件、git candidate 与占位 patch/评测。
- **m6 真实接入与兑现**：真实上游、外部契约、真实执行和聚类升级。
- **m7 身份与空间边界**：唯一全局管理员、空间成员角色、鉴权接入缝、空间路由与管理。
- **m8 空间数据面与总览**：空间上报、额度、最新 Session、总览和时间分页。
- **m9 Session 证据与对象版本**：runtime 身份、parser 工厂、完成状态、revision、文件证据与知识库文档证据。
- **m10 归因管线与七步自进化**：潜在匹配、缓存、候选、四步向导和七步运行。
- **m11 多归因体验与 V2 切换**：lane DAG 执行流、多归因详情、对象总览、跨栈验收与兼容退役。
- **m12 真实接入与算法兑现**：真实上游、契约联调、patch/评测与平台质量欠账。
- **m13 归因身份与后处理锚点**：skill/agent/知识库统一按归一化 body hash 匹配，tag/文档 revision 解析 body hash，后处理 case 用显式最后触发点。
- **m14 问题卡展示与原型对齐**：问题卡以描述为主体，补类型/对象徽章与完整 ID、关联行。
- **m15 生产环境 Claude Code 运维**：部署流水线自动安装 Claude Code 并注入模型配置，保持无 root/Node。
- **m16 生产数据目录与部署可写性**：systemd 目录、绝对 `HE_DATA_DIR`、部署写校验。
- **m17 对象卡版本显示**：ref 与短 commit 替代 digest，合并别名。
- **m18 生产 Git 出网代理与失效回退**：Xray/VLESS 本地代理、Secret 注入、git-only 接线与健康熔断。
- **m19 生产目标内容单 ref 读取**：只读一个 ref 的浅拉取缓存，避免全量 mirror。
- **m20 启动向导 Session 关联展示**：短标签加完整标题提示，四列同屏；关联与统计口径不变。
- **m21 运行详情与原型对齐**：运行详情页按 V2 原型重排目标与输入、工作区折叠与执行日志页签。
- **m23 运行列表与原型对齐**：历史卡片补齐工作空间、潜在策略与缓存标签，创建人退出列表 meta。

## 实施规则

- 每个 issue 以 `plans/fullstack-design` 的链接章节为技术权威；M9 证据门禁先于 M10 潜在匹配与归因。
- 每个 issue 合并前运行全仓静态门禁和聚焦验证；新增门禁必须有自测试并更新路由。
- CI 使用合成或脱敏 fixtures；原始 Session、用户 prompt、文档正文和生产凭据不得进入仓库。
- 远端流程对象只关闭不删除；`pnpm flow:sync -- --retire-missing` 是唯一退休入口。
