# Agent Note: 跨交互校验错误采用前端统一解释层

Status: implemented

[English](2026-11-03-actionable-validation-errors.en.md) | 中文

## Problem

后端统一错误信封已经提供稳定 `code` 和脱敏 `details`，但不同页面分别展示英文 `request validation failed`、原始领域短语或只有“稍后重试”的提示，用户无法定位字段或选择下一步。

## Decision

前端新增共享 `formatApiError` 和 `formatValidationDetails`，由调用方按操作场景提供兜底；工具优先映射 422 字段路径与校验类型，其次映射网络、权限、服务、冲突等稳定错误码，绝不把未知英文短语或异常内容当作用户文案。

## Alternatives considered

让后端直接返回中文文案会让协议承担单一前端语言和 UI 措辞，难以按场景定制；只改各页面文案会继续复制映射规则并产生不一致。

## Consequences

登录、改密、同步处理、自进化向导和 run 重试现在共享同一条错误解释链；未知字段路径仍能得到通用检查建议，后端响应缺 `details` 时保留场景化兜底。进化对象配置的 git 诊断和字段级深提示继续由 issue `#185` 承接。
