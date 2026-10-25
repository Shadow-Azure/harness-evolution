# Agent Note: Agent 执行流纯布局边界

Status: implemented

[English](2026-10-26-agent-tree-layout.en.md) | 中文

## Problem

Session tree 已由后端返回扁平 Agent、触发事件与显式 bad-case anchor，但原型里的树几何依赖 React Flow、DOM 测量和 JSONL 行差。直接把这些逻辑搬进 Vue 组件会让布局结果依赖浏览器、重复后端口径，并把问题卡渲染与基础图能力耦合。

## Decision

`components/agent-tree/layout.ts` 只消费 `SessionTree`，输出与框架无关的节点、正交通道、分支竖段和 bad-case anchor 描述。布局先复制输入 Agent 与事件，父边修补不会改写调用方数据；重复 Agent 或 main 身份直接 fail-closed，不生成部分重复图。触发链的 `×N` 使用 assistant `messageOffset` 间隔，节点条宽下限由 JSONL 行数按比例计算，文本宽度由注入函数提供。兄弟触发仅在触发点 X 距离不超过 24px 时共用 trunk，超过八个子节点生成 collapse 节点。

问题卡在 m3-02 只计算 self-skill、self-agent、discovery、fallback 的锚点，不生成 finding 节点。最小 `AgentTree.vue` 是纯布局结果的 Vue Flow 薄渲染器，不抓取 Session 数据；开发环境专用的隐藏 `/agent-tree-demo` 用 `demo-nested` 核心四节点提供真实浏览器视觉回归，大图仅用于折叠与 trunk 测试，生产 Session 接线仍由 m3-03 完成。画布控制按钮复用 Vue Flow 的官方 `ControlButton` 与样式，并由本组件提供明确的放大、缩小和适应画布标签。Vue Flow 继续留在独立动态 chunk。

## Alternatives considered

- 在 Vue 组件内边测量边布局：结果依赖 DOM 初始化和字体时序，很难稳定单测。
- 沿用 JSONL 行差生成 `×N`：与规范化的 assistant message 口径不一致。
- m3-02 直接渲染问题卡：会让 owner 为 m4 的问题卡视觉与交互提前进入图核心，扩大失败面。

## Consequences

布局可输入乱序数组复现相同结果，单元测试不需要浏览器，开发演示路由负责真实画布回归；组件只负责渲染和折叠事件。坏边会通过稳定 diagnostics 暴露，真实问题卡仍需 m4 消费 anchor descriptor。首屏 bundle 不获得 Vue Flow，生产 Session 页面接线由 m3-03 完成。真实 Chrome E2E 串行执行，因为每个用例都启动独立的 API、Vite、SQLite 和 Chrome，并行会争用本地端口与浏览器资源。
