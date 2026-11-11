# Round 5 UI review

范围：登录页说明的可读性、成员权限文案的一致性，以及用户表格中的字段名暴露。

## 修复项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 登录页页脚在 1280/1408px 下把「SSO/OIDC 回调」拆成单字「调」独占一行 | 页脚显式拆成两条均衡行，回调与接入说明合到第二行 | `before-login-footer.png` → `after-login-footer.png` |
| 2 | 说明称其余账号演示「只读成员视图」，但登录账号列表刻意排除了唯一的只读成员王浩 | 改为「其余账号演示空间管理员与普通成员，只读成员可在用户菜单切换」，与现有身份切换入口一致 | `before-login-footer.png` → `after-login-footer.png` |
| 3 | 成员页副标题同时写「拥有全部操作权限」与「只能授予管理员以下」，且未说明只有全局管理员能任命空间管理员 | 改为「空间管理员可管理本空间成员、额度与上报凭据，但只能授予成员或只读成员角色」，任命规则保留在表下说明 | `before-member-subtitle.png` → `after-member-subtitle.png` |
| 4 | 聚类来源表、向导第 2/3 步表头直接显示 `object_name`，策略开关也写「同 object_name」 | 用户表格统一改为「对象」，开关改为「仅纳入同对象」；接入契约里的 JSON 字段名保持原样 | `before-object-name.png` → `after-object-name.png`、`after-object-name-wizard.png` |

## 证据

- `before-*.png`：第 5 轮修复前。
- `after-*.png`：第 5 轮修复后。
- `after-object-switch.png`：自定义策略开关的「仅纳入同对象」文案。
- 登录页在 1280 × 800 下对照；另以 1408 × 611 回归，页脚与登录按钮仍在首屏内。
- 成员页与聚类表在 1280 × 800 下对照。
