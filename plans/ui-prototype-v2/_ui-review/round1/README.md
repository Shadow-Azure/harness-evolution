# Round 1 UI review

范围：`harness-evolution.html` 的总览、进化对象、Session 与空间管理页。

## 修复项

| # | 问题 | 修复 | 对照截图 |
|---|---|---|---|
| 1 | 顶栏四个入口在词中间折行 | 导航项不收缩、单行，收紧内边距，1340px 以下隐藏副标题 | `../round1/after-nav.png` |
| 2 | 家族树滚轮缩放而不是滚动页面 | 关闭 `zoomOnScroll`、放开 `preventingScroll`，`minZoom` 提到 0.5 | `session-full.png` → `after-session.png` |
| 3 | 浅灰辅助文字对比度不足 | `--text-faint` 改为 `#66707c`，放大图表刻度与对象计数 | `overview-full.png` → `after-overview.png` |
| 4 | Session 页底部 44px 空带 | `.shell` 高度改为 `calc(100vh - 56px)` | `session-full.png` → `after-session.png` |
| 5 | Session 详情头按钮被长 ID 挤到第二行 | 首列可收缩，会话 ID 超长省略，操作组不收缩 | `session-full.png` → `after-session.png` |
| 6 | 总览来源汇总数字溢出卡片 | 第三列 92px → 120px，字号提到 10.5px | `overview-full.png` → `after-overview.png` |
| 7 | 进化对象右卡分页悬在卡片中段 | 侧卡改为纵向 flex，列表滚动，分页贴底 | `targets-full.png` → `after-targets.png` |

## 证据

- `*-full.png`：修复前整页截图。
- `after-*.png`：修复后整页截图。
- `analysis-*.png`：分析 subagent 保存的局部证据。
- `baseline/` 与 `round0-overview-before.png`：本轮开始前建立的基线。

浏览器视口：1408 × 611（DPR 2）。本地服务：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory plans/ui-prototype-v2
```
