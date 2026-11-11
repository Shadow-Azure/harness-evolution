# Round 9 UI review

范围：bad case 列表新增可点击的 ID 列。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | bad case 的 ID 只作为标题下的副文本，不能单独点击，也没法把某条 case 直接指给别人 | 列表最前面新增「ID」列，ID 是可点击链接，直接打开 Session 错误查看 → 错误详情的对应 bad case（停在问题描述页签） | `before-list.png` → `after-list.png` |
| 2 | 标题列同时显示 ID 与标题，新增 ID 列后重复 | 标题列只保留标题，去掉重复的 ID 副文本，行高同时收紧 | `after-list.png` |
| 3 | 空态行仍写 `colspan="7"` | 随列数改为 8 | — |

## 证据

- `before-list.png`：改动前（`56627b6`）。
- `after-list.png`：改动后，1440 × 1000 视口，滚动到列表。
- `after-id-landing.png`：点击 `BC-HC-014` 后落地，Session 错误查看 → 错误详情，选中 #2 输出缺少来源校验。
