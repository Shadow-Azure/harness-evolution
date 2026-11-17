# M12 真实接入与算法兑现

[English](m12-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m12
title: M12 真实接入与算法兑现
status: planned
github:
  number: 20
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/20
```

## 目标

在 V2 主体交付后，兑现真实上游、可插拔对象归因、真实评测、聚类升级和平台质量欠账。

## 范围

真实轨迹上游、外部契约、归因报告 V2、对象级 Attribution Skill、Session 上下文、Agent 执行器、质量门禁、调度观测、真实 patch/评测、聚类算法、Windows 门禁和对象配置诊断。

## 验收

选定对象与 revision 可在真实 Session 上通过默认或对象绑定 Skill 逐 Badcase 生成可复现报告；Agent 执行器在内网不可用时有契约桩，真实接入须经过影子质量门禁；真实数据与外部执行服务替代其余占位实现；平台质量欠账有自动化证据；旧 M6 迁移 issue 均可回链新入口。

## 非目标

不改变 M7–M11 已定义的多归因、PotentialMatcher 与七步运行边界，不让归因 Agent 自动替换用户选定对象，也不恢复被裁撤的时间线页面。
