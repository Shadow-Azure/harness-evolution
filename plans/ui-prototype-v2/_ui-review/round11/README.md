# Round 11 UI review

范围：工作空间切换器从品牌旁移到右侧操作区。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 工作空间切换器紧贴品牌，与导航争横向空间；右侧顶栏（同步状态与用户菜单之间）留白 | 把 `#wsPicker` 移到 `.tn-right`，位于数据同步之后、用户菜单之前 | `before-topbar.png` → `after-topbar.png` |
| 2 | 弹层从左侧展开，移到右侧后会溢出视口 | 弹层改为右对齐展开（`right: 0`），宽度仍为 322px | `after-ws-open.png` |
| 3 | 摘要宽度收得过紧，工作空间名被截断成「Harness 核…」 | 摘要上限放宽到 240px、名称到 146px，1440 下完整显示 | `after-topbar.png` |
| 4 | 右侧集群在 1280 下可能拥挤 | 1280 下不出现横向溢出，导航副标题按既有规则退回 | `after-topbar-1280.png` |

## 证据

- `before-topbar.png`：改动前（`a55c4a9`），切换器在品牌与导航之间。
- `after-topbar.png` / `after-ws-open.png` / `after-topbar-1280.png`：1440 × 300 与 1280 × 300 视口。
