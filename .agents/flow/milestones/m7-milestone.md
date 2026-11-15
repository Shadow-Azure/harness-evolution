# M7 身份与空间边界

[English](m7-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m7
title: M7 身份与空间边界
status: done
github:
  number: 17
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/17
```

## 目标

建立唯一全局管理员、空间成员角色、鉴权接入缝与全链路空间隔离。

## 范围

身份、工作空间、成员权限、空间路由、空间管理与上报凭据。

## 验收

权限矩阵与不可见空间 404 可自动验证；前后端只从 auth/session 恢复用户和可用空间。

## 非目标

不实现知识库对象，不改变轨迹归一化的全局共享边界。
