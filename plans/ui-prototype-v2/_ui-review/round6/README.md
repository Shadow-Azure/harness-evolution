# Round 6 UI review

范围：进化对象配置弹窗的必填提示，以及登录页视觉基线路径的自引用。

## 修复项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 新增/编辑进化对象弹窗保存时会校验对象名称、仓库地址、子目录与基线分支/标签，但只有验证集/测试集两个字段标了 `*` | 四个同样参与校验的字段补上必填标记，表单提示与保存逻辑一致 | `before-target-required.png` → `after-target-required.png`、`after-target-validation.png` |
| 2 | 第 4 轮把登录页「视觉与交互基线沿用」改成当前 V2 文件自身，形成自引用，读者无法判断基线是哪一版 | 恢复为 V1 原型 `plans/14-15-ui-prototype/harness-evolution.html`；该文件与 V2 的「上一版」叙事一致 | `before-login-baseline.png` → `after-login-baseline.png` |

## 证据

- `before-*.png`：第 6 轮修复前。
- `after-*.png`：第 6 轮修复后。
- `after-target-validation.png`：空表单提交时顶部显示「请填写对象名称。」，与新增的必填标记对应。
- 浏览器视口：1280 × 800。
