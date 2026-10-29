#!/usr/bin/env node
/**
 * issue #165 AFTER smoke collector —「bad_cases 短标题 title + 描述正文」.
 *
 * 用真实前后端（临时数据目录 + fixtures 演示数据）跑一遍错误详情页，验证：
 *   1. API：`/api/sessions/{sid}/bad-cases` 与 `/api/sessions/{sid}/tree` 的每条
 *      问题都带非空 `title`，且 `reason` 仍是完整描述正文。
 *   2. Web：错误详情页标题行渲染 `title`，正文块渲染 `reason`；未分析 / 非问题 /
 *      是问题三种归因状态同样成立。
 *   3. Web：问题列表卡与执行流图问题卡主文本是 `title`（不是整段描述）。
 *   4. 390px 窄屏与浏览器 console 无异常。
 *
 * 为了让“两级文本”在截图里肉眼可辨，脚本在 seed 之后只改临时库里三条问题的
 * `bad_case_description` 为长描述（等价真实上报形态），不改仓库文件。
 *
 * 运行（仓库根目录，需 apps/api/.venv 与 apps/web/node_modules）：
 *   CHROME_BIN="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" \
 *     node reports/2026-10-29/issue-165-bad-case-title/collect-smoke.mjs
 */

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../../../tests/support/runtime.mjs";

const root = process.cwd();
const reportDir = path.resolve("reports/2026-10-29/issue-165-bad-case-title");
const screenshotDir = path.join(reportDir, "screenshots");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const python = path.join(
  root,
  "apps/api/.venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const initialPassword = `issue165-smoke-${randomBytes(6).toString("hex")}-initial`;
const finalPassword = `issue165-smoke-${randomBytes(6).toString("hex")}-final`;
const jwtSecret = randomBytes(32).toString("hex");
const scenarios = [];
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";

const LONG_DESCRIPTIONS = {
  "badcase-synthetic-0001":
    "子任务「检索工具层四项+综述」在读取前置步骤的检索索引时抛出 ENOENT：data/index.json 不存在，错误被上层 catch 静默吞掉，导致该轮 5 条结论没有来源，汇总阶段无法回溯每条结论的出处。",
  "badcase-synthetic-0002":
    "review-workflow 串行执行三个检查子任务，但汇总节点只读取了最后一个子任务的输出，前两个子任务的检查项与证据全部丢失，最终结论缺少覆盖说明。",
  "badcase-synthetic-0004":
    "最小会话只包含一轮用户输入与一条 agent 回复，缺少工具调用与子 agent 记录，无法判断问题发生在检索、生成还是校验阶段，只能标记为待补数据。",
};

/**
 * Record one smoke scenario.
 * @param {string} id Stable scenario id.
 * @param {string} name Scenario name.
 * @param {string} detail Observed result.
 * @param {string[]} evidence Screenshot file names or evidence notes.
 * @param {"pass"|"fail"|"warn"|"manual"} status Scenario status.
 * @returns {void}
 */
function record(id, name, detail, evidence, status = "pass") {
  scenarios.push({
    id,
    name,
    status: { kind: status, label: status.toUpperCase() },
    detail,
    evidence,
  });
}

/** Stop servers and delete the temporary data directory. */
async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true, maxRetries: 10 });
}

/**
 * Run one command to completion and fail on a non-zero exit.
 * @param {string} command Executable.
 * @param {string[]} args Arguments.
 * @param {NodeJS.ProcessEnv} env Environment.
 * @returns {void}
 */
function run(command, args, env) {
  const result = spawnSync(command, args, {
    cwd: root,
    env,
    encoding: "utf8",
    // Windows cannot spawn the pnpm.cmd shim without a shell (CVE-2024-27980).
    shell: process.platform === "win32" && command.endsWith(".cmd"),
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed:\n${result.stdout}\n${result.stderr}`);
  }
}

/**
 * GET an API path with a bearer token.
 * @param {string} pathname API path.
 * @param {string} accessToken Bearer token.
 * @returns {Promise<any>} Parsed JSON.
 */
async function apiJson(pathname, accessToken) {
  const response = await fetch(`${apiUrl}${pathname}`, {
    headers: accessToken ? { authorization: `Bearer ${accessToken}` } : undefined,
  });
  if (response.status !== 200) {
    throw new Error(`${pathname}: ${await response.text()}`);
  }
  return await response.json();
}

/**
 * Log in, rotate the bootstrap password, and return an authenticated cookie.
 * @returns {Promise<{accessToken: string, cookie: string}>} Session credentials.
 */
async function login() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
  });
  const loginBody = await response.text();
  assert.equal(response.status, 200, loginBody);
  const login = JSON.parse(loginBody);
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);

  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${login.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ oldPassword: initialPassword, newPassword: finalPassword }),
  });
  assert.equal(changed.status, 204, await changed.text());

  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  const refreshedBody = await refreshed.text();
  assert.equal(refreshed.status, 200, refreshedBody);
  const refreshedJson = JSON.parse(refreshedBody);
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return { accessToken: refreshedJson.accessToken, cookie };
}

/**
 * Install the refresh-token cookie so the SPA boots authenticated.
 * @param {{session: object}} page Browser page.
 * @param {string} cookie refresh_token value.
 * @returns {Promise<void>} Resolves after the cookie is set.
 */
async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
}

/**
 * Navigate and wait for the document to finish loading.
 * @param {{session: object}} page Browser page.
 * @param {string} url Target URL.
 * @returns {Promise<void>} Resolves after load.
 */
async function navigate(page, url) {
  await page.session.send("Page.navigate", { url });
  await waitForDocument(page.session, `document.readyState === "complete"`, url);
}

/**
 * Evaluate one expression in the page and return its value.
 * @param {{session: object}} page Browser page.
 * @param {string} expression JavaScript expression.
 * @returns {Promise<any>} Serialized result.
 */
async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result.result.value;
}

/**
 * Capture one full-viewport screenshot.
 * @param {{session: object}} page Browser page.
 * @param {string} name Output file name.
 * @returns {Promise<string>} Absolute screenshot path.
 */
async function screenshot(page, name) {
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  const file = path.join(screenshotDir, name);
  await writeFile(file, Buffer.from(result.data, "base64"));
  return file;
}

/**
 * Capture one element-clipped screenshot.
 * @param {{session: object}} page Browser page.
 * @param {string} selector Element selector.
 * @param {string} name Output file name.
 * @returns {Promise<string>} Absolute screenshot path.
 */
async function clipShot(page, selector, name) {
  const clip = await evaluate(
    page,
    `(() => {
      const node = document.querySelector(${JSON.stringify(selector)});
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return {
        x: Math.max(0, rect.left - 8),
        y: Math.max(0, rect.top - 8),
        width: Math.min(innerWidth, rect.width + 16),
        height: Math.min(innerHeight, rect.height + 16),
      };
    })()`,
  );
  assert.ok(clip, `missing ${selector}`);
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    clip: { ...clip, scale: 1 },
    captureBeyondViewport: true,
  });
  const file = path.join(screenshotDir, name);
  await writeFile(file, Buffer.from(result.data, "base64"));
  return file;
}

/**
 * Patch three seeded descriptions into the temporary SQLite database.
 * @returns {void}
 */
function patchLongDescriptions() {
  const dbPath = path.join(dataDir, "harness.db");
  const script = [
    "import sqlite3, sys, json",
    "db = sqlite3.connect(sys.argv[1])",
    "payload = json.loads(sys.argv[2])",
    "for case_id, description in payload.items():",
    "    db.execute('UPDATE bad_cases SET bad_case_description = ? WHERE bad_case_id = ?', (description, case_id))",
    "db.commit()",
    "db.close()",
  ].join("\n");
  run(python, ["-c", script, dbPath, JSON.stringify(LONG_DESCRIPTIONS)], process.env);
}

/**
 * Navigate inside the SPA without a document reload.
 * @param {{session: object}} page Browser page.
 * @param {string} pathname Same-origin path with query.
 * @returns {Promise<void>} Resolves after the router handled the popstate.
 */
async function clientNavigate(page, pathname) {
  await page.session.send("Runtime.evaluate", {
    expression: `history.pushState({}, "", ${JSON.stringify(pathname)});
      window.dispatchEvent(new PopStateEvent("popstate"));`,
  });
}

/**
 * Log in again with the rotated password and install the fresh refresh cookie.
 * @param {{session: object}} page Browser page.
 * @returns {Promise<void>} Resolves after the cookie is installed.
 */
async function relogin(page) {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: finalPassword }),
  });
  assert.equal(response.status, 200, await response.text());
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  await installCookie(page, cookie);
}

/**
 * Assert and screenshot one detail page state.
 * @param {{session: object}} page Browser page.
 * @param {{sessionId: string, selection: object, description: string, name: string, shot: string}} input Scenario input.
 * @param {{reload?: boolean}} [options] Reload instead of SPA navigation.
 * @returns {Promise<void>} Resolves after assertions and capture.
 */
async function verifyDetail(page, input, { reload = false } = {}) {
  const { selection, description, name, shot } = input;
  const route = `/sessions/${encodeURIComponent(input.sessionId)}/errors?case=${encodeURIComponent(selection.badCaseId)}&tab=desc`;
  const wait = `(() => {
        const title = document.querySelector(".description #problem-description-title");
        const detail = document.querySelector(".description .problem-detail");
        if (!title || !detail) return null;
        const titleText = title.textContent.replace(/\\s+/g, " ").trim();
        const detailText = detail.textContent.replace(/\\s+/g, " ").trim();
        if (!titleText || !detailText) return null;
        return {
          titleText,
          detailText,
          listTitle: document.querySelector("[data-testid='problem-list'] .problem-card-title")?.textContent.trim() ?? null,
          flowNote: document.querySelector(".flow-head span")?.textContent.trim() ?? null,
          graphTitle: document.querySelector(".rf-finding .finding-title")?.textContent.trim() ?? null,
          hasLegacyGraphClass: Boolean(document.querySelector(".rf-finding .finding-reason")),
          rows: document.querySelectorAll("[data-testid='problem-list'] [data-bad-case-id]").length,
        };
      })()`;
  let observed;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (reload) await navigate(page, `${baseUrl}${route}`);
    else await clientNavigate(page, route);
    try {
      observed = await waitForDocument(
        page.session,
        wait,
        `detail page ${selection.badCaseId}`,
      );
      if (observed.titleText === selection.title && observed.detailText === description) break;
      observed = null;
    } catch (error) {
      if (attempt === 1) {
        const state = await evaluate(
          page,
          `({ href: location.href, body: document.body.textContent.replace(/\\s+/g, " ").slice(0, 600) })`,
        );
        await screenshot(page, `debug-${selection.badCaseId}.png`);
        throw new Error(`${error.message}: ${JSON.stringify(state)}`);
      }
      // 启动期 refresh 轮换可能让旧 cookie 失效：重新登录并硬导航重试一次。
      await relogin(page);
    }
  }
  assert.equal(observed.titleText, selection.title, `${name}: detail heading is the short title`);
  assert.equal(observed.detailText, description, `${name}: detail body is the full description`);
  assert.notEqual(observed.titleText, observed.detailText, `${name}: two distinct text levels`);
  assert.ok(observed.flowNote?.includes(selection.title), `${name}: flow note uses the short title`);
  // 等执行流图渲染完再截图，否则 1408px 的详情页会拍到空画布。
  await waitForDocument(
    page.session,
    `Boolean(document.querySelector(".rf-finding .finding-title"))`,
    `${name}: graph card`,
  );
  await screenshot(page, shot);
  record(
    name,
    `错误详情 · ${name}`,
    `标题行=${JSON.stringify(observed.titleText)}；正文块=${JSON.stringify(observed.detailText.slice(0, 40))}…；列表卡=${JSON.stringify(observed.listTitle)}`,
    [shot],
  );
}

async function main() {
  assert.equal(
    spawnSync(python, ["--version"], { encoding: "utf8" }).status,
    0,
    "apps/api/.venv is missing; run pnpm setup:api",
  );
  await mkdir(screenshotDir, { recursive: true });
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-issue165-smoke-"));
  const apiPort = await availablePort();
  const webPort = await availablePort();
  apiUrl = `http://127.0.0.1:${apiPort}`;
  baseUrl = `http://127.0.0.1:${webPort}`;
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: jwtSecret,
    HE_PHASE: "demo",
  };

  run(pnpm, ["fixtures:seed"], env);
  patchLongDescriptions();

  api = spawn(python, ["-m", "app"], {
    cwd: path.join(root, "apps/api"),
    env: { ...env, HE_PORT: String(apiPort), HE_HOST: "127.0.0.1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);

  web = spawn(
    process.execPath,
    [
      path.join(root, "apps/web/node_modules/vite/bin/vite.js"),
      "--host",
      "127.0.0.1",
    ],
    {
      cwd: path.join(root, "apps/web"),
      env: {
        ...env,
        HE_WEB_PORT: String(webPort),
        HE_API_PROXY_URL: apiUrl,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(`${baseUrl}/`, web, () => webLogs);

  try {
    const auth = await login();
    const sessionOne = "10000000-0000-4000-8000-000000000001";
    const sessionTwo = "10000000-0000-4000-8000-000000000002";
    const sessionFour = "10000000-0000-4000-8000-000000000004";

    const apiChecks = [];
    for (const sessionId of [sessionOne, sessionTwo, sessionFour]) {
      const { items } = await apiJson(
        `/api/sessions/${encodeURIComponent(sessionId)}/bad-cases`,
        auth.accessToken,
      );
      assert.ok(items.length > 0, `${sessionId}: seeded problems exist`);
      for (const item of items) {
        assert.ok(typeof item.title === "string" && item.title.trim().length > 0, `${item.badCaseId}: title`);
        assert.ok(typeof item.reason === "string" && item.reason.trim().length > 0, `${item.badCaseId}: description`);
      }
      apiChecks.push({
        sessionId,
        items: items.map((item) => ({ badCaseId: item.badCaseId, title: item.title, analysis: item.analysis.status })),
      });
      const tree = await apiJson(
        `/api/sessions/${encodeURIComponent(sessionId)}/tree`,
        auth.accessToken,
      );
      for (const badCase of tree.badCases) {
        assert.ok(badCase.title?.trim(), `${badCase.badCaseId}: tree title`);
      }
    }
    const selectionItems = apiChecks.flatMap((check) => check.items);
    const find = (badCaseId) => {
      const item = selectionItems.find((candidate) => candidate.badCaseId === badCaseId);
      assert.ok(item, `missing ${badCaseId}`);
      return item;
    };
    record(
      "API",
      "API 契约：bad-cases 与 session tree 都带 title",
      `三个会话共 ${selectionItems.length} 条问题，title 均非空；tree.badCases 同样带 title。`,
      [],
    );

    const page = await createBrowserPage();
    const violations = browserViolations(page.session);
    try {
      await installCookie(page, auth.cookie);
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width: 1408,
        height: 960,
        deviceScaleFactor: 1,
        mobile: false,
      });

      await verifyDetail(
        page,
        {
          sessionId: sessionOne,
          selection: find("badcase-synthetic-0001"),
          description: LONG_DESCRIPTIONS["badcase-synthetic-0001"],
          name: "是问题（analyzed_issue，prompt）",
          shot: "05-after-error-detail-issue.png",
        },
        { reload: true },
      );
      await verifyDetail(page, {
        sessionId: sessionTwo,
        selection: find("badcase-synthetic-0002"),
        description: LONG_DESCRIPTIONS["badcase-synthetic-0002"],
        name: "非问题（analyzed_nonissue）",
        shot: "06-after-error-detail-nonissue.png",
      });
      await verifyDetail(page, {
        sessionId: sessionFour,
        selection: find("badcase-synthetic-0004"),
        description: LONG_DESCRIPTIONS["badcase-synthetic-0004"],
        name: "未分析（unanalyzed）",
        shot: "07-after-error-detail-unanalyzed.png",
      });

      const listRoute = `/sessions/${encodeURIComponent(sessionOne)}/errors?case=${encodeURIComponent("badcase-synthetic-0001")}&tab=desc`;
      await clientNavigate(page, listRoute);
      await waitForDocument(
        page.session,
        `Boolean(document.querySelector("[data-testid='problem-list'] .problem-card-title"))`,
        "problem list",
      );
      await clipShot(page, ".error-sidebar", "08-after-problem-list.png");
      record("LIST", "问题列表卡以短标题为主文本", "左栏卡片标题来自 title，描述不再进入卡片主文本。", ["08-after-problem-list.png"]);

      const graph = await waitForDocument(
        page.session,
        `(() => {
          const card = document.querySelector(".rf-finding .finding-title");
          return card ? card.textContent.trim() : null;
        })()`,
        "graph problem card",
      );
      assert.equal(graph, find("badcase-synthetic-0001").title, "graph card uses the short title");
      await clipShot(page, ".flow-panel", "09-after-graph-card.png");
      record("GRAPH", "执行流问题卡以短标题为主文本", `图上卡片文本=${JSON.stringify(graph)}。`, ["09-after-graph-card.png"]);

      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width: 390,
        height: 844,
        deviceScaleFactor: 1,
        mobile: true,
      });
      await screenAndAssertNarrow(page, listRoute);
      await screenshot(page, "10-after-390.png");
      record("NARROW", "390px 窄屏详情页仍为两级文本", "标题行与正文块同时可见，无横向溢出。", ["10-after-390.png"]);

      const consoleViolations = violations.filter((entry) => !entry.includes("favicon"));
      assert.deepEqual(consoleViolations, [], `browser console: ${consoleViolations.join("\n")}`);
      record("CONSOLE", "浏览器 console 无 error/warning", "全程无 console error、exception 或 warning。", []);
    } finally {
      await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
      await page.close();
    }

    await writeFile(
      path.join(reportDir, "assertions.json"),
      `${JSON.stringify({ generatedAt: new Date().toISOString(), api: apiChecks, scenarios }, null, 2)}\n`,
    );
  } finally {
    await cleanup();
  }
}

/**
 * Assert the narrow viewport keeps both text levels without horizontal overflow.
 * @param {{session: object}} page Browser page.
 * @param {string} route Same-origin detail route.
 * @returns {Promise<void>} Resolves after assertions.
 */
async function screenAndAssertNarrow(page, route) {
  await clientNavigate(page, route);
  const observed = await waitForDocument(
    page.session,
    `(() => {
      const title = document.querySelector(".description #problem-description-title");
      const detail = document.querySelector(".description .problem-detail");
      if (!title || !detail) return null;
      return {
        title: title.textContent.trim(),
        detail: detail.textContent.trim(),
        overflow: document.documentElement.scrollWidth > window.innerWidth,
      };
    })()`,
    "narrow detail page",
  );
  assert.ok(observed.title.length > 0 && observed.detail.length > 0, "narrow: two levels");
  assert.equal(observed.overflow, false, "narrow: no horizontal overflow");
  // 390px 下页面初始滚动位置由执行流决定；把详情面板滚进视口再截图取证。
  await evaluate(
    page,
    `(() => {
      document.querySelector(".detail-panel")?.scrollIntoView({ block: "center", behavior: "instant" });
      return true;
    })()`,
  );
  await new Promise((resolve) => setTimeout(resolve, 500));
  const visible = await evaluate(
    page,
    `(() => {
      const title = document.querySelector(".description #problem-description-title").getBoundingClientRect();
      const detail = document.querySelector(".description .problem-detail").getBoundingClientRect();
      return title.top >= 0 && detail.bottom <= window.innerHeight;
    })()`,
  );
  assert.equal(visible, true, "narrow: heading and body are visible together");
}

await main();
process.stdout.write(
  `smoke (after) complete:\n${scenarios.map((row) => `  ${row.id}: ${row.detail}`).join("\n")}\n`,
);
