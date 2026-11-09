import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("./prototype.html", import.meta.url), "utf8");
const design = readFileSync(new URL("./design.md", import.meta.url), "utf8");
const checks = [
  ["workspace switcher", 'data-testid="workspace-switcher"'],
  ["overview", 'data-testid="overview-page"'],
  ["object multi-select", 'data-testid="object-multiselect"'],
  ["overview chart", 'data-testid="bad-case-chart"'],
  ["bad case drill-down", 'data-testid="overview-case-row"'],
  ["latest ten Sessions", "sessions.slice(0,10)"],
  ["Enter exact Session search", 'data-testid="session-search"'],
  ["collapsible attribution list", 'data-testid="case-attribution-toggle"'],
  ["attribution pagination", "data-analysis-page"],
  ["problem description", 'data-testid="problem-description"'],
  ["evolution wizard", "function wizardModal()"],
  ["default potential policy", "默认潜在匹配策略"],
  ["custom potential policy", "使用自定义策略"],
  ["cache toggle", 'id="cacheToggle"'],
  ["workspace quota", "Bad case 数量上限"],
  ["workspace members", "添加空间成员"],
  ["workspace ingestion", "/api/workspaces/ws_ai_agent/bad-cases"],
  ["login without registration", 'data-testid="login-page"'],
];
for (const [name, marker] of checks) {
  assert.ok(html.includes(marker), `missing prototype capability: ${name}`);
  console.log(`✓ ${name}`);
}
for (const [name, marker] of [
  ["legacy route migration", "旧 `/sessions/**`"],
  ["workspace cache isolation", "query key 同样以 `workspaceId`"],
  ["object-level non-target result", "非该对象问题"],
  ["permission matrix", "## 3. 身份与权限"],
]) {
  assert.ok(design.includes(marker), `missing design decision: ${name}`);
  console.log(`✓ ${name}`);
}
console.log(`V2 prototype verification passed (${checks.length + 4} checks).`);
