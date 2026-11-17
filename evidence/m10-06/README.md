# M10-06 GUI smoke evidence

This directory is an evidence-only branch for PR m10-06. It is not part of the
feature branch.

- `before-*.png`: baseline `origin/main` (aed175c) run detail captured with the
  same V2 fixture data.
- `*-after-*.png`: feature branch run detail at 1408×960.
- `prototype-*.png`: `plans/ui-prototype-v2/harness-evolution.html` at the
  corresponding steps (1408×960).
- `smoke-report.html` / `report-data.json`: generated smoke report.

The blocked attribution banner is the only visual delta: the baseline renders
“未知阶段”; the feature branch renders “归因（attribution）阶段”.
