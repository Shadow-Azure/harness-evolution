# Round 8 UI review

范围：空间管理与进化对象配置中的危险操作，改为先确认、再执行。

## 修复项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 「移除成员」点击即删除，成员列表立即少一行并提示已移除，误点无法撤销 | 先弹出确认框，说明会失去空间访问权限、历史上报与运行记录保留；确认后才移除 | `before-member-remove.png` → `after-member-confirm.png` → `after-member-cancel.png` / `after-member-confirmed.png` |
| 2 | 「重新生成凭据」点击即轮换，旧凭据立即失效，接入方可能当场断流 | 先确认「旧凭据会立即失效，已接入的调用方需要更新 Authorization」；取消时凭据不变 | `before-token.png` / `before-token-rotated.png` → `after-token-confirm.png` → `after-token-confirmed.png` |
| 3 | 进化对象侧卡的「移除」点击即删除，统计、趋势与启动向导同时少一个对象 | 先确认「移除后不再出现在统计、趋势与启动向导中；已有运行记录保留」 | `before-target-remove.png` → `after-target-confirm.png` → `after-target-cancel.png` / `after-target-confirmed.png` |

## 验证结果

- 成员移除：取消后王浩仍在列表；确认后王浩消失并提示「成员已移除」。
- 凭据重置：取消后 curl 示例中的凭据保持 `he_ws_hc_7f3c9a2e5b81d40c`；确认后变为 `he_ws_ss_c605du2bl8w`，并提示「凭据已重新生成，旧凭据立即失效」。
- 进化对象移除：取消后 deep-research 仍在右侧列表；确认后列表由 3 个变为 2 个，统计数字同步下降，并提示「已移除 deep-research」。
- 验证过程中发现确认弹窗按钮未加入文档级点击选择器，导致点击无响应；已补 `[data-v2-confirm]` / `[data-v2-confirm-cancel]` 并复测通过。
- 浏览器控制台无 error / warn。
- 浏览器视口：1280 × 800。

## 证据

- `before-*.png`：第 8 轮修复前，危险操作即时生效。
- `after-*-confirm.png`：确认弹窗。
- `after-*-cancel.png`：取消后状态不变。
- `after-*-confirmed.png`：确认后操作生效。
