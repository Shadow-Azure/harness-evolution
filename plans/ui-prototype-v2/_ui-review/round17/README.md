# Round 17 UI review

范围：两个列表取消「整行可点跳转」，只保留 bad case ID 与归因报告 ID 的链接。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | bad case 列表与潜在 bad case 列表整行可点，误触就会离开当前页，也与「只有 ID 跳转」的约定冲突 | 去掉两处行上的 `data-v2-overview-case` 与共享的点击分支，行 `cursor` 改为 `default`、hover 提亮从 5% 降到 3% | `cases-list.png`、`targets-list.png` |
| 2 | 链接本身仍需要能跳转 | 保留表内 bad case ID 与归因报告 ID 链接（各自 `stopPropagation`、新标签打开），行为不变 | 同上 |

## 验证（CDP 实际点击）

| 操作 | 结果 |
|---|---|
| bad case 列表点「bad case」列 | URL 不变、仍停留总览，`cursor: default` |
| 潜在 bad case 列表点「进化对象」列 | URL 不变、仍停留总览，`cursor: default` |
| 点 bad case ID | 打开 Session 错误查看 → 错误详情（`?page=session&view=errors&…&dtab=desc&u=admin`） |
| 点归因报告 ID | 打开 Session 错误查看 → 归因分析，并预选对应对象 |

## 证据

- `cases-list.png` / `targets-list.png`：改动后的两张列表（1700 × 1000 视口）；行不再是点击目标，ID 与报告 ID 仍是链接。
