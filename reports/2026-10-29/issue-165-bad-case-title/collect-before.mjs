#!/usr/bin/env node
/**
 * issue #165 BEFORE evidence collector —「bad_cases 缺短标题 title」.
 *
 * 目的：用可复现脚本采集问题现场的两组对照证据。
 *   1. 原型错误详情页（plans/14-15-ui-prototype/harness-evolution.html）：
 *      深链打开某个问题后，`.err-detail` 内是两级文本——`.ed-head .ed-title`
 *      短标题 + `.ed-detail` 描述正文。
 *   2. 当前 Web（Vite dev + FastAPI）：`/sessions/{sid}/errors?case=...&tab=desc`
 *      把 `bad_cases.reason` 这整段长文本直接渲染成 `.problem-title` 标题，
 *      没有正文段落层级。
 *
 * 为什么固定 pre-fix 快照：
 *   issue #165 的实现会重命名 `bad_cases.reason`、给 DTO 加 `title`，而实现改动
 *   可能与本脚本在同一工作树里并行发生。为了让 BEFORE 证据稳定、可复现，脚本用
 *   `git archive` 把 `ISSUE165_BEFORE_REV`（默认 f37010d，即 #165 实现前的提交）
 *   的 `apps/api`、`apps/web`、`fixtures/m2-synthetic` 归档到临时目录再运行；
 *   工作树源码只读、不 stash、不 checkout。API/Web 的 node_modules / .venv 通过
 *   目录联接复用已安装依赖，不改仓库文件。
 *
 * 运行方式（仓库根目录）：
 *   pnpm install                 # 首次
 *   pnpm setup:api               # 首次，apps/api/.venv
 *   node reports/2026-10-29/issue-165-bad-case-title/collect-before.mjs
 *   # 可选：ISSUE165_BEFORE_REV=<sha> 覆盖快照提交；CHROME_BIN=<chrome> 指定浏览器
 *
 * 依赖：
 *   - git、tar（Windows 10+ 自带 bsdtar）。
 *   - Chrome：默认找 `C:\Program Files\Google\Chrome\Application\chrome.exe`，
 *     或设置 `CHROME_BIN` 指向 Chrome/Chromium。
 *   - 端口：API、Web、CDP 端口都由脚本动态申请，不占用固定端口。
 *   - 等价命令：脚本内直接调用 `python -m app.cli seed`（= `pnpm fixtures:seed`）
 *     与 `node apps/web/node_modules/vite/bin/vite.js`（= `pnpm dev:web`）；
 *     Windows + Node 22 无法在不开 shell 的情况下 spawn `pnpm.cmd`，直接调入口
 *     还能避免 shell 包装进程导致清理残留子进程。
 *
 * 数据隔离与说明：
 *   - 使用临时目录作为 `HE_DATA_DIR`，seed 只写入临时 SQLite，不触碰仓库 data/。
 *   - fixtures 自带的 `reason` 是演示短句；真实上报的 `bad_cases.reason` 是长描述。
 *     为呈现 issue 描述的「长文本被当标题」现场，脚本在 seed 之后、API 启动之前，
 *     只对临时库里一条 bad_case 的 `reason` 写入一段与原型 `.ed-detail` 同量级的
 *     长描述（等价于真实数据形态）。不改仓库文件、不改应用源码、不改 fixtures。
 *   - 全过程不落任何密钥；密码/JWT secret 均按次随机生成，只存在于本进程内存。
 */

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const reportDir = path.resolve("reports/2026-10-29/issue-165-bad-case-title");
const screenshotDir = path.join(reportDir, "screenshots");
const prototypePath = path.join(
  root,
  "plans/14-15-ui-prototype/harness-evolution.html",
);
const apiDir = path.join(root, "apps/api");
const webDir = path.join(root, "apps/web");
const defaultChrome = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
// #165 实现前的提交：bad_cases 仍只有 reason，错误详情页把 reason 当标题。
const beforeRev = process.env.ISSUE165_BEFORE_REV ?? "f37010d";

// runtime.mjs 在模块求值时就读取 CHROME_BIN，因此先确定浏览器可执行文件，
// 再用动态 import 加载 CDP 辅助模块。
if (!process.env.CHROME_BIN && existsSync(defaultChrome)) {
  process.env.CHROME_BIN = defaultChrome;
}
const {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
} = await import("../../../tests/support/runtime.mjs");

const prototypeSessionId = "050b81ba-9621-4992-84fe-106ae46eb36b";
const prototypeIssueId = "I-050b-01";
const prototypeUrl =
  `${pathToFileURL(prototypePath).href}?page=session&view=errors` +
  `&sid=${prototypeSessionId}&issue=${prototypeIssueId}&dtab=desc`;

// 真实 bad_cases.reason 的形态：一段说明“何时、何处、抛了什么、影响什么”的长描述。
// 该文本只写入临时库，用于还原真实数据下的渲染现场。
const LONG_REASON =
  "子任务「检索工具层四项+综述」在读取前置步骤的检索索引时抛出 ENOENT：" +
  "data/index.json 不存在，错误被上层 catch 静默吞掉，导致该轮 5 条结论没有来源，" +
  "汇总阶段无法回溯每条结论的出处。";

const initialPassword = `issue165-smoke-${randomBytes(6).toString("hex")}-initial`;
const finalPassword = `issue165-smoke-${randomBytes(6).toString("hex")}-final`;
const jwtSecret = randomBytes(32).toString("hex");
const python = path.join(apiDir, ".venv", "Scripts", "python.exe");

const observed = {
  beforeRev,
  prototype: {
    url: prototypeUrl,
    selectors: {
      panel: ".err-detail",
      title: ".err-detail .ed-head .ed-title",
      detail: ".err-detail .ed-detail",
    },
  },
  current: {
    selectors: {
      workspace: "[data-testid='errors-workspace']",
      problemList: ".error-sidebar",
      panel: ".detail-panel",
      title: ".description #problem-description-title.problem-title",
    },
  },
};

let api;
let web;
let dataDir;
let beforeDir;
let apiUrl;
let baseUrl;
let apiLogs = "";
let webLogs = "";

/** @param {string} id @param {string} message */
function log(id, message) {
  process.stdout.write(`[${id}] ${message}\n`);
}

/**
 * Run a command to completion and return its exit code plus combined output.
 * @param {string} file Executable.
 * @param {string[]} args Arguments.
 * @param {{cwd?: string, env?: NodeJS.ProcessEnv}} [options] Spawn options.
 * @returns {Promise<{code: number|null, output: string}>} Exit code and output.
 */
async function runTool(file, args, options = {}) {
  const child = spawn(file, args, {
    cwd: options.cwd ?? root,
    env: options.env ?? process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  capture(child, (chunk) => {
    output += chunk;
  });
  const code = await new Promise((resolve) => child.once("exit", resolve));
  return { code, output };
}

/**
 * Evaluate one expression in the page and return its serializable value.
 * @param {object} page Browser page from createBrowserPage.
 * @param {string} expression JavaScript expression.
 * @returns {Promise<any>} Result value.
 */
async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(
      `Runtime.evaluate failed: ${result.exceptionDetails.text} ` +
        `${result.exceptionDetails.exception?.description ?? ""}`,
    );
  }
  return result.result.value;
}

/**
 * Poll an expression until it returns a truthy value, with diagnostics on timeout.
 * @param {object} page Browser page.
 * @param {string} expression JavaScript expression.
 * @param {string} label Human readable wait reason.
 * @param {number} [timeoutMs] Upper bound.
 * @returns {Promise<any>} First truthy value.
 */
async function waitForExpression(page, expression, label, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    last = await evaluate(page, expression);
    if (last) return last;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const state = await evaluate(
    page,
    `({
      href: location.href,
      readyState: document.readyState,
      bodyText: (document.body?.textContent ?? "").trim().slice(0, 600),
      errors: [...document.querySelectorAll(".error-state, .err-empty")].map((n) => n.textContent.trim()),
    })`,
  ).catch(() => null);
  throw new Error(
    `timed out waiting for ${label}: ${JSON.stringify({ expression, last, state })}`,
  );
}

/**
 * Capture the current viewport (or a clip) through CDP and write a PNG.
 * @param {object} page Browser page.
 * @param {string} filename Output file name inside screenshots/.
 * @param {{clip?: {x:number,y:number,width:number,height:number,scale:number}, captureBeyondViewport?: boolean}} [options]
 * @returns {Promise<string>} Absolute file path.
 */
async function screenshot(page, filename, options = {}) {
  const target = path.join(screenshotDir, filename);
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: options.captureBeyondViewport ?? false,
    ...(options.clip ? { clip: options.clip } : {}),
  });
  await writeFile(target, data, "base64");
  return target;
}

/**
 * Compute a clip rect for one element in page coordinates (window is not scrolled).
 * @param {object} page Browser page.
 * @param {string} selector CSS selector.
 * @param {number} [scale] Clip scale factor.
 * @returns {Promise<{x:number,y:number,width:number,height:number,scale:number}>} Clip.
 */
async function clipOf(page, selector, scale = 2) {
  const rect = await evaluate(
    page,
    `(() => {
      const node = document.querySelector(${JSON.stringify(selector)});
      if (!node) return null;
      const r = node.getBoundingClientRect();
      return {
        x: r.left + window.scrollX,
        y: r.top + window.scrollY,
        width: r.width,
        height: r.height,
      };
    })()`,
  );
  assert.ok(rect, `missing ${selector}`);
  return {
    x: Math.max(0, Math.round(rect.x)),
    y: Math.max(0, Math.round(rect.y)),
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
    scale,
  };
}

/**
 * Install the refresh-token cookie so the SPA boots authenticated.
 * @param {object} page Browser page.
 * @param {string} cookie refresh_token value.
 * @returns {Promise<void>} Resolves after the cookie is set.
 */
async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.clearBrowserCookies");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
}

/**
 * Login, rotate the bootstrap password, and return an authenticated cookie.
 * @returns {Promise<{accessToken: string, cookie: string}>} Session credentials.
 */
async function loginSession() {
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
    body: JSON.stringify({
      oldPassword: initialPassword,
      newPassword: finalPassword,
    }),
  });
  assert.equal(changed.status, 204, await changed.text());

  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  const refreshedBody = await refreshed.text();
  assert.equal(refreshed.status, 200, refreshedBody);
  const access = JSON.parse(refreshedBody);
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return { accessToken: access.accessToken, cookie };
}

/**
 * GET a JSON API path with the access token.
 * @param {string} pathname API path.
 * @param {string} accessToken Bearer token.
 * @returns {Promise<any>} Parsed JSON.
 */
async function apiJson(pathname, accessToken) {
  const response = await fetch(`${apiUrl}${pathname}`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  if (response.status !== 200) {
    assert.fail(`${pathname}: ${await response.text()}`);
  }
  return response.json();
}

/**
 * Unpack the pinned pre-fix revision and wire installed dependencies into it.
 * @returns {Promise<void>} Resolves when the staging tree is runnable.
 */
async function prepareSnapshot() {
  beforeDir = await mkdtemp(path.join(tmpdir(), "harness-issue165-before-"));
  const archive = path.join(beforeDir, "before.tar");
  const archived = await runTool("git", [
    "-C",
    root,
    "archive",
    "--format=tar",
    "--output",
    archive,
    beforeRev,
    "apps/api",
    "apps/web",
    "fixtures/m2-synthetic",
    "tsconfig.base.json",
  ]);
  assert.equal(archived.code, 0, archived.output);
  const extracted = await runTool("tar", ["-xf", archive, "-C", beforeDir]);
  assert.equal(extracted.code, 0, extracted.output);
  await rm(archive, { force: true });

  const stagedApi = path.join(beforeDir, "apps/api");
  const stagedWeb = path.join(beforeDir, "apps/web");
  const stagedManifest = path.join(
    beforeDir,
    "fixtures/m2-synthetic/corpus.json",
  );
  assert.equal(existsSync(path.join(stagedApi, "app/main.py")), true);
  assert.equal(existsSync(stagedManifest), true);
  assert.equal(existsSync(path.join(stagedWeb, "vite.config.ts")), true);

  // 复用工作树已安装的依赖（web 的 node_modules 目录联接；API 用原 venv 的 python）。
  await symlink(
    path.join(webDir, "node_modules"),
    path.join(stagedWeb, "node_modules"),
    "junction",
  );

  // Vite 的依赖缓存写到临时目录，避免和可能并行运行的 dev server 争用 .vite 缓存；
  // fs.allow 追加仓库根，允许 serve 经目录联接解析到仓库的 workspace 包。
  await writeFile(
    path.join(stagedWeb, "vite.collector.config.ts"),
    [
      'import { fileURLToPath } from "node:url";',
      "",
      'import base from "./vite.config.ts";',
      "",
      "const stagedRoot = fileURLToPath(new URL(\"./\", import.meta.url));",
      "",
      "export default {",
      "  ...base,",
      "  cacheDir: fileURLToPath(new URL(\"./.vite-cache/\", import.meta.url)),",
      "  server: {",
      "    ...base.server,",
      "    fs: { allow: [stagedRoot, process.env.ISSUE165_REPO_ROOT].filter(Boolean) },",
      "  },",
      "};",
      "",
    ].join("\n"),
  );
  log(
    "snapshot",
    `${beforeRev} -> ${beforeDir} (apps/api, apps/web, fixtures/m2-synthetic)`,
  );
}

/**
 * Rewrite one bad case's reason in the isolated SQLite DB (post-seed, pre-API).
 * @param {string} badCaseId Bad case id.
 * @param {string} reason New reason text.
 * @returns {Promise<void>} Resolves after commit.
 */
async function overrideReason(badCaseId, reason) {
  const database = path.join(dataDir, "harness.db");
  assert.equal(existsSync(database), true, `missing ${database}`);
  const result = await runTool(python, [
    "-c",
    "import sqlite3, sys\n" +
      "conn = sqlite3.connect(sys.argv[1])\n" +
      "cur = conn.execute('update bad_cases set reason = ? where bad_case_id = ?', (sys.argv[2], sys.argv[3]))\n" +
      "assert cur.rowcount == 1, 'bad case not found'\n" +
      "conn.commit()\n" +
      "conn.close()\n",
    database,
    reason,
    badCaseId,
  ]);
  assert.equal(result.code, 0, result.output);
}

/**
 * Seed the temp data dir, adjust the long reason, and start API + Web.
 * @returns {Promise<void>} Resolves when both servers answer.
 */
async function startServices() {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-issue165-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: jwtSecret,
    HE_PHASE: "demo",
  };
  const stagedApi = path.join(beforeDir, "apps/api");
  const stagedWeb = path.join(beforeDir, "apps/web");
  const stagedManifest = path.join(
    beforeDir,
    "fixtures/m2-synthetic/corpus.json",
  );

  const seed = await runTool(
    python,
    ["-m", "app.cli", "seed", "--manifest", stagedManifest],
    { cwd: stagedApi, env },
  );
  assert.equal(seed.code, 0, seed.output);
  log("seed", `fixtures seeded into ${dataDir}`);

  await overrideReason("badcase-synthetic-0001", LONG_REASON);
  log("seed", "badcase-synthetic-0001.reason 已换成真实形态长描述（仅临时库）");

  const apiPort = await availablePort();
  const webPort = await availablePort();
  apiUrl = `http://127.0.0.1:${apiPort}`;
  baseUrl = `http://127.0.0.1:${webPort}`;

  api = spawn(python, ["-m", "app"], {
    cwd: stagedApi,
    env: {
      ...env,
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_PORT: String(apiPort),
      HE_SYNC_INTERVAL_SECONDS: "0",
      PYTHONUNBUFFERED: "1",
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);
  log("api", apiUrl);

  web = spawn(
    process.execPath,
    [
      path.join(stagedWeb, "node_modules/vite/bin/vite.js"),
      "--config",
      "vite.collector.config.ts",
      "--force",
      "--host",
      "127.0.0.1",
      "--port",
      String(webPort),
      "--strictPort",
    ],
    {
      cwd: stagedWeb,
      env: {
        ...process.env,
        HE_API_PROXY_URL: apiUrl,
        ISSUE165_REPO_ROOT: root,
      },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);
  log("web", baseUrl);
}

/**
 * Pick the seeded session/bad case used for the current-app screenshots.
 * @param {string} accessToken Bearer token.
 * @returns {Promise<{sessionId: string, badCaseId: string, reason: string, sessionTitle: string}>} Selection.
 */
async function pickProblem(accessToken) {
  const sessions = await apiJson("/api/sessions", accessToken);
  assert.ok(Array.isArray(sessions.items) && sessions.items.length > 0);
  /** @type {{sessionId: string, badCaseId: string, reason: string, sessionTitle: string} | null} */
  let chosen = null;
  for (const session of sessions.items) {
    const cases = await apiJson(
      `/api/sessions/${encodeURIComponent(session.id)}/bad-cases`,
      accessToken,
    );
    for (const item of cases.items) {
      // pre-#165 DTO 只有 reason，没有 title；若这里出现 title，说明快照不是 BEFORE。
      assert.equal(
        Object.hasOwn(item, "title"),
        false,
        `expected pre-#165 API without title, got ${JSON.stringify(item)}`,
      );
      if (item.badCaseId === "badcase-synthetic-0001") {
        chosen = {
          sessionId: session.id,
          badCaseId: item.badCaseId,
          reason: item.reason,
          sessionTitle: session.title ?? session.shortTitle ?? "",
        };
      }
    }
  }
  assert.ok(chosen, "seeded bad case badcase-synthetic-0001 not found");
  assert.equal(chosen.reason, LONG_REASON, "reason override did not reach the API");
  return chosen;
}

/**
 * Screenshot the prototype deep link: full viewport + .err-detail close-up.
 * @returns {Promise<object>} Observed prototype texts and styles.
 */
async function capturePrototype() {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: prototypeUrl });
    const levels = await waitForExpression(
      page,
      `(() => {
        const panel = document.querySelector(".err-detail");
        const title = panel?.querySelector(".ed-head .ed-title");
        const detail = panel?.querySelector(".ed-detail");
        if (!panel || !title || !detail) return null;
        const titleText = title.textContent.replace(/\\s+/g, " ").trim();
        const detailText = detail.textContent.replace(/\\s+/g, " ").trim();
        if (!titleText || !detailText) return null;
        return { titleText, detailText };
      })()`,
      "prototype .ed-title + .ed-detail",
      60_000,
    );
    log("prototype", `title=${JSON.stringify(levels.titleText)}`);
    log("prototype", `detail=${JSON.stringify(levels.detailText)}`);

    const styles = await evaluate(
      page,
      `(() => {
        const panel = document.querySelector(".err-detail");
        const title = panel.querySelector(".ed-head .ed-title");
        const detail = panel.querySelector(".ed-detail");
        const rect = panel.getBoundingClientRect();
        const titleRect = title.getBoundingClientRect();
        const detailRect = detail.getBoundingClientRect();
        const titleStyle = getComputedStyle(title);
        const detailStyle = getComputedStyle(detail);
        const cards = [...document.querySelectorAll(".err-list .err-card")];
        return {
          cards: cards.length,
          activeCardTitle: cards.find((card) => card.classList.contains("active"))
            ?.querySelector(".err-card-title")?.textContent.trim() ?? null,
          panel: { top: rect.top, bottom: rect.bottom, width: rect.width },
          title: {
            text: title.textContent.trim(),
            fontSize: titleStyle.fontSize,
            fontWeight: titleStyle.fontWeight,
            top: titleRect.top,
            bottom: titleRect.bottom,
          },
          detail: {
            text: detail.textContent.trim(),
            fontSize: detailStyle.fontSize,
            fontWeight: detailStyle.fontWeight,
            color: detailStyle.color,
            top: detailRect.top,
            bottom: detailRect.bottom,
          },
          mainScrollTop: document.querySelector(".err-main")?.scrollTop,
          documentScrollTop: window.scrollY,
        };
      })()`,
    );
    observed.prototype.levels = styles;

    // 视口高度按 .err-detail 完整可见来定，宽度固定 1408。
    const viewportHeight = Math.min(
      1600,
      Math.max(960, Math.ceil(styles.panel.bottom) + 24),
    );
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: viewportHeight,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await new Promise((resolve) => setTimeout(resolve, 400));
    const fitted = await evaluate(
      page,
      `(() => {
        const panel = document.querySelector(".err-detail").getBoundingClientRect();
        return {
          innerWidth: window.innerWidth,
          innerHeight: window.innerHeight,
          panelTop: panel.top,
          panelBottom: panel.bottom,
          visible: panel.top >= 0 && panel.bottom <= window.innerHeight,
        };
      })()`,
    );
    assert.equal(fitted.innerWidth, 1408);
    assert.equal(
      fitted.visible,
      true,
      `prototype .err-detail not fully visible: ${JSON.stringify(fitted)}`,
    );
    observed.prototype.viewport = fitted;
    const fullPath = await screenshot(page, "01-prototype-error-detail.png");
    log("shot", fullPath);

    const panelClip = await clipOf(page, ".err-detail", 2);
    observed.prototype.panelClip = panelClip;
    const panelPath = await screenshot(page, "02-prototype-ed-panel.png", {
      clip: panelClip,
      captureBeyondViewport: true,
    });
    log("shot", panelPath);

    observed.prototype.consoleViolations = violations;
    return observed.prototype;
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
}

/**
 * Screenshot the current app: errors detail with selected problem + left list.
 * @param {{sessionId: string, badCaseId: string}} problem Chosen seeded problem.
 * @param {{accessToken: string, cookie: string}} auth Logged-in session.
 * @returns {Promise<object>} Observed current-app texts and measurements.
 */
async function captureCurrentApp(problem, auth) {
  const route = `/sessions/${encodeURIComponent(problem.sessionId)}/errors` +
    `?case=${encodeURIComponent(problem.badCaseId)}&tab=desc`;
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
    // 一次硬导航直接落到深链：先访问 /sessions 再跳深链会触发两次启动期
    // refresh，而 refresh token 每次轮换，第二次请求会用已被轮换掉的 cookie
    // 拿到 401，把页面踢回 /login。深链本身走的是同一条刷新恢复路径。
    await page.session.send("Page.navigate", { url: `${baseUrl}${route}` });
    try {
      await waitForExpression(
        page,
        `Boolean(document.querySelector(".shell"))`,
        "authenticated shell",
        30_000,
      );
    } catch (error) {
      throw new Error(
        `${error.message}\nconsole violations:\n${violations.join("\n")}\nvite output (tail):\n${webLogs.slice(-4_000)}`,
      );
    }
    const heading = await waitForExpression(
      page,
      `(() => {
        const workspace = document.querySelector("[data-testid='errors-workspace']");
        const panel = document.querySelector(".detail-panel");
        const title = panel?.querySelector(".description #problem-description-title");
        if (!workspace || !panel || !title) return null;
        const text = title.textContent.replace(/\\s+/g, " ").trim();
        if (!text) return null;
        return {
          titleText: text,
          titleCount: panel.querySelectorAll(".problem-title").length,
          descriptionText: panel.querySelector(".description")?.textContent
            .replace(/\\s+/g, " ").trim(),
          bodyCandidates: [...panel.querySelectorAll(
            ".description > p, .description .problem-detail, .description .ed-detail",
          )].map((node) => node.textContent.trim()),
          rows: document.querySelectorAll(
            "[data-testid='problem-list'] [data-bad-case-id]",
          ).length,
          hasDetailPanelClass: panel.classList.contains("detail-panel"),
        };
      })()`,
      "current problem description heading",
      30_000,
    );
    assert.equal(
      new URLSearchParams(await evaluate(page, "location.search")).get("case"),
      problem.badCaseId,
    );
    assert.equal(heading.titleText, LONG_REASON);
    assert.equal(heading.titleCount, 1);
    assert.deepEqual(heading.bodyCandidates, []);
    const reasonOccurrences = heading.descriptionText.split(LONG_REASON).length - 1;
    assert.equal(reasonOccurrences, 1);

    const headingMetrics = await evaluate(
      page,
      `(() => {
        const title = document.querySelector(".description #problem-description-title");
        const style = getComputedStyle(title);
        const rect = title.getBoundingClientRect();
        const lineHeight = Number.parseFloat(style.lineHeight);
        const lines = Math.round(rect.height / (Number.isFinite(lineHeight) ? lineHeight : rect.height));
        return {
          text: title.textContent.trim(),
          fontSize: style.fontSize,
          fontWeight: style.fontWeight,
          lineHeight: style.lineHeight,
          lines,
          width: rect.width,
          height: rect.height,
        };
      })()`,
    );

    await evaluate(
      page,
      `(() => {
        const panel = document.querySelector(".detail-panel");
        panel.scrollIntoView({ block: "center", behavior: "instant" });
        return true;
      })()`,
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    const detailPath = await screenshot(page, "03-current-error-detail.png");
    log("shot", detailPath);

    const sidebarClip = await clipOf(page, ".error-sidebar", 2);
    const listPath = await screenshot(page, "04-current-problem-list.png", {
      clip: sidebarClip,
      captureBeyondViewport: true,
    });
    log("shot", listPath);

    observed.current.url = `${baseUrl}${route}`;
    observed.current.sessionId = problem.sessionId;
    observed.current.badCaseId = problem.badCaseId;
    observed.current.sessionTitle = problem.sessionTitle;
    observed.current.heading = headingMetrics;
    observed.current.headingText = heading.titleText;
    observed.current.bodyText = null;
    observed.current.reasonOccurrencesInDescription = reasonOccurrences;
    observed.current.listRows = heading.rows;
    observed.current.sidebarClip = sidebarClip;
    observed.current.consoleViolations = violations;
    return observed.current;
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
}

/** Stop servers and delete the temp data dir + staging snapshot. */
async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) {
    await rm(dataDir, { recursive: true, force: true, maxRetries: 10 });
  }
  if (beforeDir) {
    await rm(beforeDir, { recursive: true, force: true, maxRetries: 10 });
  }
}

async function main() {
  assert.equal(existsSync(prototypePath), true, `missing ${prototypePath}`);
  assert.equal(existsSync(python), true, `missing ${python}`);
  assert.equal(
    existsSync(path.join(webDir, "node_modules/vite/bin/vite.js")),
    true,
    "missing apps/web/node_modules; run pnpm install",
  );
  await mkdir(screenshotDir, { recursive: true });

  await prepareSnapshot();
  await startServices();
  try {
    const auth = await loginSession();
    const problem = await pickProblem(auth.accessToken);
    log("problem", `${problem.sessionId} / ${problem.badCaseId}`);
    observed.current.fixtureReasonWasShort =
      "fixtures reason 原为短句；本脚本在临时库把该条 reason 覆盖为长描述以呈现真实数据形态";
    await capturePrototype();
    await captureCurrentApp(problem, auth);

    await writeFile(
      path.join(reportDir, "observations.json"),
      `${JSON.stringify(
        {
          generatedAt: new Date().toISOString(),
          beforeRev,
          longReason: LONG_REASON,
          prototype: observed.prototype,
          current: observed.current,
        },
        null,
        2,
      )}\n`,
    );

    process.stdout.write(
      [
        "",
        "OBSERVED",
        `  prototype title : ${JSON.stringify(observed.prototype.levels.title.text)}`,
        `  prototype detail: ${JSON.stringify(observed.prototype.levels.detail.text)}`,
        `  current heading : ${JSON.stringify(observed.current.headingText)}`,
        "  current body    : (absent)",
        `  session id      : ${observed.current.sessionId}`,
        `  bad case id     : ${observed.current.badCaseId}`,
        "",
      ].join("\n"),
    );
  } finally {
    await cleanup();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error}\n`);
  process.exitCode = 1;
});
