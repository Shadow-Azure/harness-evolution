# Round 8 UI review

范围：潜在 bad case 列表的列调整，以及归因报告深链修复。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 「触发点」列与 Session 详情、执行流里的信息重复，还占一列宽度 | 删除该列 | `before-list.png` → `after-list.png` |
| 2 | 有归因报告的 bad case 看不出报告讲的是什么事，必须点进去才知道 | 在归因报告 ID 后新增「问题现象/描述」列，取 bad case 的描述；超长省略、hover 看全文，无报告的行显示 — | `after-list.png` |
| 3 | 点归因报告 ID 会跳到登录页 | 深链补上 `u=<当前用户>`；打开的是 Session 错误查看页、归因分析页签 | `after-deeplink.png` |
| 4 | 深链只按 case 定位，一个 case 有多条对象归因时，选中的不一定是点的那条 | 深链增加 `obj=<进化对象>`，错误详情按对象名预选归因 | `after-deeplink.png` |
| 5 | 列表里的归因报告 ID 是运行期合成值，点开后常是「暂无归因」 | 归因状态与报告 ID 改为读取该 bad case 现有的归因记录（按对象名匹配）；匹配不到即「未分析」 | `after-list.png` |

## 证据

- `before-list.png`：改动前（`56cf9a5`）。
- `after-list.png`：改动后，1440 × 1000 视口，滚动到列表。
- `after-deeplink.png`：点击「输出缺少来源校验」的归因报告 ID 后落地，停在归因分析页签，预选 `deep-research` 的归因。
