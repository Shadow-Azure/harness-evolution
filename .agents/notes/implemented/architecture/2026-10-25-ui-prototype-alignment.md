# Agent Note: 前端壳层对齐交互原型

Status: implemented

[English](2026-10-25-ui-prototype-alignment.en.md) | 中文

## Problem

共享 Vue 壳曾使用暗色开发工具风格、`Harness Lens` 品牌、胶囊导航和开发态 API 状态胶囊。它与已确认的原型视觉基准及 D16 的“首版只做亮色”决策冲突；继续在错误骨架上新增页面会扩大返工和视觉分裂。

## Decision

- `plans/14-15-ui-prototype/harness-evolution.html` 是前端视觉验收基准，原型 `:root` 的亮色和业务状态 token 是唯一颜色源。
- 共享壳使用 `#f4f5f7` 页面、`#fafbfc` 顶栏、白色卡片、`Harness Evolution` 品牌、56px 顶栏和下划线式 Sessions/Errors/Evolution 导航；Session 分区使用蓝色，Evolution 使用紫色。
- 登录、强制改密、Loading/Empty/Error/NotFound 和当前占位页复用同一亮色令牌、字体栈和紧凑信息层级。领域页面仍由后续 milestone 交付，不在共享壳中伪造数据。
- 真实 Chrome E2E 直接读取 computed style，验证页面、顶栏、卡片和激活下划线颜色，并同时覆盖 390px 无横向溢出。
- 窄屏隐藏品牌文字时链接仍保留 `Harness Evolution` 可访问名称；演示环境角标保留可读文字，不降级为无语义色点。

## Alternatives considered

- 保留暗色开发工具风格：原型与 D16 已明确选择亮色，继续保留会使后续页面全部偏离验收基准；否决。
- 只替换颜色，不重做品牌与导航几何：会留下胶囊导航、错误品牌层级和 68px 顶栏，仍不满足原型；否决。
- 等业务页面实现时逐页纠正：会重复实现并放大视觉分裂，而且登录与共享三态已经继承错误基线；否决。

## Consequences

- 后续页面必须复用 `tokens.css` 中的 raw token 或语义映射，不能把颜色写进组件。
- Element Plus 仍只承担表单和消息控件；业务布局、导航、卡片、状态和三态由应用组件自研。
- 首版不提供暗色切换；令牌分层保留了未来扩展空间，但新增主题必须作为独立决策。
- 任何共享壳或认证页的视觉改动都要附真实浏览器 computed-style 与 390px 证据。
- 响应式视觉压缩不得删除状态语义；颜色、文字和可访问名称必须同时保持可辨认。
