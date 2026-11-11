# Round 10 UI review

范围：统一「bad case ID → 问题描述页签、归因报告 ID → 归因分析页签」的跳转约定。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 自进化运行详情里「来源 bad case」表的 ID 链接显式传了 `attr`，点 bad case ID 会落到归因分析页签 | 该表改回默认深链（`dtab=desc`），点 ID 落到问题描述；归因报告 ID 仍走 `dtab=attr` | `before-case-id.png` → `after-case-id.png` |
| 2 | 归因报告 ID 的深链没带对象，落地后选中的是第一条归因 | 深链补 `obj=<进化对象>`，错误详情按对象名预选对应归因 | 见第 8 轮 |
| 3 | 列表行本身也可点击，点 ID 时可能同时触发整行跳转 | `evCaseLink` 统一加 `stopPropagation` | — |

## 证据

- `before-case-id.png`：改动前（`9c480e9`），从自进化运行详情点「来源 bad case」的 ID，落在归因分析页签。
- `after-case-id.png`：改动后，同一个 ID 落到问题描述页签。
