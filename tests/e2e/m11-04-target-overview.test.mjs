import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../support/runtime.mjs";

const root = process.cwd();
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m11-04-smoke-initial-password";
const replacementPassword = "m11-04-smoke-replacement-password";
const secret = "m11-04-smoke-signing-secret-with-sufficient-length";
const screenshotDir = process.env.M11_04_SCREENSHOT_DIR ?? "";
const workspaceId = "ws-default";
let api;
let web;
let dataDir;
let gitConfigPath;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let emptyWorkspaceId = "";
let authSession = null;
let currentPassword = initialPassword;

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

for (const [signal, exitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  process.once(signal, () => {
    void cleanup().finally(() => process.exit(exitCode));
  });
}

async function apiJson(pathname, token, init = {}) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...init,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    assert.fail(
      `${pathname} returned ${response.status}: ${await response.text()}`,
    );
  }
  return response.status === 204 ? null : await response.json();
}

async function loginAndRotatePassword() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
  });
  assert.equal(login.status, 200);
  const loginBody = await login.json();
  assert.ok(loginBody.accessToken);
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${loginBody.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: initialPassword,
      newPassword: replacementPassword,
    }),
  });
  assert.equal(changed.status, 204);

  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: `refresh_token=${
        login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1]
      }`,
    },
  });
  assert.equal(refreshed.status, 200);
  const access = await refreshed.json();
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  currentPassword = replacementPassword;
  return { accessToken: access.accessToken, cookie };
}

async function loginCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: currentPassword }),
  });
  assert.equal(response.status, 200);
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "login must set a refresh cookie");
  return cookie;
}

async function installBrowser(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    path: "/api/auth",
    httpOnly: true,
    sameSite: "Strict",
  });
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 980,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ??
        result.exceptionDetails.text,
    );
  }
  return result.result.value;
}

async function click(page, selector) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true, view: window }),
      );
      return true;
    })()`,
    `click ${selector}`,
  );
}

async function setControl(page, selector, value) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.value = ${JSON.stringify(value)};
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return element.value === ${JSON.stringify(value)};
    })()`,
    `set ${selector}`,
  );
}

async function navigateTargets(page, wid = workspaceId) {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${wid}/overview?tab=targets`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const stats = document.querySelector("[data-testid='ov-target-stats']");
      const tab = document.querySelector("[data-testid='ov-tab-targets']");
      if (!stats || !tab || !tab.classList.contains("active")) return null;
      const statTargets = document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim();
      const statSessions = document.querySelector("[data-testid='ov-target-stat-sessions']")?.textContent?.trim();
      if (statTargets !== "6" || statSessions !== "1") return null;
      if (document.querySelectorAll("[data-testid='ov-target-case-row']").length === 0) {
        return null;
      }
      return {
        search: location.search,
        targets: statTargets,
        sessions: statSessions,
        potential: document.querySelector("[data-testid='ov-target-stat-potential']")?.textContent?.trim(),
        attributed: document.querySelector("[data-testid='ov-target-stat-attributed']")?.textContent?.trim(),
        nonTarget: document.querySelector("[data-testid='ov-target-stat-nontarget']")?.textContent?.trim(),
        unanalyzed: document.querySelector("[data-testid='ov-target-stat-unanalyzed']")?.textContent?.trim(),
        sideItems: document.querySelectorAll("[data-testid^='ov-target-side-item-']").length,
        caseRows: document.querySelectorAll("[data-testid='ov-target-case-row']").length,
      };
    })()`,
    "target overview data",
  );
}

async function waitForUrlParam(page, key, value) {
  await waitForDocument(
    page.session,
    `new URLSearchParams(location.search).get(${JSON.stringify(key)}) === ${JSON.stringify(value)}`,
    `URL parameter ${key}=${value}`,
  );
}

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource")
  );
}

async function screenshot(
  page,
  name,
  { full = true, width = 1440, height = 980, deviceScaleFactor = 1 } = {},
) {
  if (!screenshotDir) return;
  await mkdir(screenshotDir, { recursive: true });
  await page.session.send("Page.enable");
  const contentHeight = await evaluate(
    page,
    `document.querySelector("[data-testid='overview-page']")?.scrollHeight ?? 0`,
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width,
    height: full ? Math.max(height, Number(contentHeight) + 70) : height,
    deviceScaleFactor,
    mobile: false,
  });
  await new Promise((resolve) => setTimeout(resolve, 200));
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
  });
  await writeFile(
    path.join(screenshotDir, name),
    Buffer.from(result.data, "base64"),
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 980,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m11-04-e2e-"));
  gitConfigPath = path.join(dataDir, "gitconfig");
  const originDir = path.join(dataDir, "target-origin.git");
  const workDir = path.join(dataDir, "target-work");
  const git = (args, cwd) => {
    const result = spawnSync("git", args, { cwd, encoding: "utf8" });
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  };
  git(["init", "--bare", "-b", "main", originDir], root);
  git(["clone", originDir, workDir], root);
  for (const name of ["synthetic-review", "extra-1", "extra-2", "extra-3", "extra-4", "extra-5", "retired"]) {
    await mkdir(path.join(workDir, "skills", name), { recursive: true });
    await writeFile(path.join(workDir, "skills", name, "SKILL.md"), `# ${name}\n`);
  }
  git(["add", "."], workDir);
  git(
    [
      "-c",
      "user.name=M11-04",
      "-c",
      "user.email=m11-04@example.invalid",
      "commit",
      "-m",
      "seed target content",
    ],
    workDir,
  );
  git(["tag", "main"], workDir);
  git(["tag", "synthetic-1"], workDir);
  git(["push", "origin", "refs/heads/main:refs/heads/main", "--tags"], workDir);
  await writeFile(
    gitConfigPath,
    `[url "file://${originDir}"]\n\tinsteadOf = https://example.invalid/example/skills.git\n` +
      `[url "file://${originDir}"]\n\tinsteadOf = https://example.invalid/m11-04.git\n`,
  );
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_LOGIN_RATE_LIMIT: "100",
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
    GIT_CONFIG_GLOBAL: gitConfigPath,
  };
  const seed = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    encoding: "utf8",
  });
  assert.equal(seed.status, 0, seed.stderr || seed.stdout);
  const targetSeed = spawnSync(
    python,
    [
      path.join(root, "tests/e2e/support/m11_04_target_overview_seed.py"),
      "--data-dir",
      dataDir,
    ],
    { cwd: root, env, encoding: "utf8" },
  );
  assert.equal(targetSeed.status, 0, targetSeed.stderr || targetSeed.stdout);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
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
  await waitFor(`http://127.0.0.1:${apiPort}/api/health`, api, () => apiLogs);

  web = spawn(
    pnpm,
    [
      "--filter",
      "@harness/web",
      "exec",
      "vite",
      "--force",
      "--host",
      "127.0.0.1",
      "--port",
      String(webPort),
      "--strictPort",
    ],
    {
      cwd: root,
      env: { ...process.env, HE_API_PROXY_URL: `http://127.0.0.1:${apiPort}` },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);

  const session = await loginAndRotatePassword();
  const me = await apiJson("/api/auth/session", session.accessToken);
  const created = await apiJson("/api/workspaces", session.accessToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M11-04 空空间",
      mark: "M1104",
      quota: 10,
      spaceAdminIds: [me.user.id],
    }),
  });
  emptyWorkspaceId = created.id;
  authSession = session;
});

after(cleanup);

test("m11-04 target overview renders, filters, paginates, and analyses one object", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: expectedLogEntry,
  });
  try {
    await installBrowser(page, await loginCookie());
    const ready = await navigateTargets(page);
    assert.equal(ready.targets, "6");
    assert.equal(ready.sessions, "1");
    assert.equal(ready.potential, "3");
    assert.equal(ready.attributed, "1");
    assert.equal(ready.nonTarget, "1");
    assert.equal(ready.unanalyzed, "1");
    assert.equal(ready.sideItems, 5);
    assert.equal(ready.caseRows, 3);
    const scrollable = await evaluate(
      page,
      `(() => {
        const pageRoot = document.querySelector("[data-testid='overview-page']");
        if (!pageRoot || pageRoot.scrollHeight <= pageRoot.clientHeight) return null;
        pageRoot.scrollTop = pageRoot.scrollHeight;
        return {
          scrollTop: pageRoot.scrollTop,
          detailVisible: document.querySelector("[data-testid='ov-target-detail']").getBoundingClientRect().top < innerHeight,
          listVisible: document.querySelector("[data-testid='ov-target-case-list']").getBoundingClientRect().top < innerHeight,
        };
      })()`,
    );
    assert.ok(scrollable && scrollable.scrollTop > 0, "overview page must scroll");
    assert.equal(scrollable.detailVisible, true);
    assert.equal(scrollable.listVisible, true);
    await evaluate(
      page,
      `document.querySelector("[data-testid='overview-page']").scrollTop = 0`,
    );
    await screenshot(page, "01-targets-overview.png", { full: false });
    await screenshot(page, "06-targets-overview-full.png");

    await click(page, "[data-testid='ov-target-side-next']");
    await waitForUrlParam(page, "tpage", "2");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length === 1`,
      "second target page",
    );
    await screenshot(page, "02-targets-side-page-2.png");
    await click(page, "[data-testid='ov-target-side-prev']");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length === 5`,
      "first target page",
    );

    await click(page, "[data-testid='ov-target-metric-unanalyzed']");
    await waitForUrlParam(page, "states", "attributed,nonTarget");
    await click(page, "[data-testid='ov-target-metric-unanalyzed']");
    await waitForDocument(
      page.session,
      `!new URLSearchParams(location.search).has("states")`,
      "all target states restored",
    );

    await click(page, "[data-bucket='2026-10-19']");
    await waitForUrlParam(page, "cfrom", "2026-10-19");
    await waitForUrlParam(page, "cto", "2026-10-25");
    await setControl(page, "[data-testid='ov-target-case-state']", "nonTarget");
    await waitForUrlParam(page, "cstate", "nonTarget");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='ov-target-case-row']").length === 1`,
      "one non-target case row",
    );
    await screenshot(page, "03-targets-filtered.png");
    await click(page, "[data-testid='ov-target-case-reset']");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='ov-target-case-row']").length === 3`,
      "reset case filters",
    );
    await setControl(page, "[data-testid='ov-target-case-from']", "2026-10-24");
    await setControl(page, "[data-testid='ov-target-case-to']", "2026-10-31");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='ov-target-case-row']").length === 2`,
      "two rows inside the list-only date window",
    );
    await click(page, "[data-testid='ov-target-case-reset']");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='ov-target-case-row']").length === 3`,
      "reset list-only date window",
    );

    await setControl(page, "[data-testid='ov-target-detail-from']", "2026-10-20");
    await waitForUrlParam(page, "dfrom", "2026-10-20");
    await setControl(page, "[data-testid='ov-target-detail-to']", "2026-10-31");
    await waitForUrlParam(page, "dto", "2026-10-31");
    await evaluate(
      page,
      `(() => {
        const details = document.querySelector("[data-testid='ov-target-detail-versions']");
        if (details) details.open = true;
        return true;
      })()`,
    );
    await click(page, "input[data-version='main']");
    await waitForUrlParam(page, "dversions", "main");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ov-target-detail-potential']")?.textContent?.trim() === "0"`,
      "independent version scope",
    );
    await click(page, "input[data-version='main']");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ov-target-detail-potential']")?.textContent?.trim() === "3"`,
      "restored version scope",
    );

    await click(page, "[data-testid='ov-tab-cases']");
    await waitForDocument(
      page.session,
      `location.search.includes("tab=cases") &&
       location.search.includes("range=90") &&
       document.querySelector("[data-testid='ov-case-list']") !== null`,
      "cases tab with the shared window",
    );
    await click(page, "[data-testid='ov-tab-targets']");
    await waitForDocument(
      page.session,
      `location.search.includes("tab=targets") &&
       new URLSearchParams(location.search).get("range") === "90" &&
       document.querySelector("[data-testid='ov-target-stats']") !== null`,
      "targets tab restores the shared window",
    );

    const rulesEntry = "[data-testid^='ov-target-side-rules-']";
    const targetId = await evaluate(page, `document.querySelector("${rulesEntry}").dataset.testid.replace("ov-target-side-rules-", "")`);
    const targetEntry = `[data-testid="ov-target-side-rules-${targetId}"]`;
    assert.equal(await evaluate(page, `(() => {
      const card = document.querySelector('[data-testid="ov-target-side-item-${targetId}"]');
      const edit = card.querySelector('[data-testid="ov-target-side-edit-${targetId}"]');
      const rule = card.querySelector(".rule-entry");
      return edit.getBoundingClientRect().bottom <= rule.getBoundingClientRect().top;
    })()`), true);
    await click(page, targetEntry);
    await click(page, ".candidate-layout .editor header button");
    await click(page, ".candidate-layout .el-select__wrapper");
    await click(page, ".candidate-source-menu .el-select-dropdown__item");
    await click(page, ".candidate-layout .types button");
    await waitForDocument(page.session, 'document.querySelector(".candidate-layout .reports")?.textContent.includes("条上报")', "per-source reports");
    await click(page, ".candidate-layout .editor header button");
    await click(page, ".el-dialog__footer .el-button--primary");
    await waitForDocument(page.session, `(() => {
      const error = document.querySelector(".el-dialog__footer [role=alert]");
      if (!error?.textContent.includes("请选择来源名称")) return false;
      const [red, green, blue] = getComputedStyle(error).color.match(/\\d+/g).map(Number);
      return red > green && red > blue;
    })()`, "incomplete source validation in red");
    await click(page, ".candidate-layout fieldset:last-of-type .el-select__wrapper");
    await waitForDocument(page.session, `(() => {
      const input = document.querySelector(".candidate-layout fieldset:last-of-type input[aria-controls]");
      const menu = document.getElementById(input?.getAttribute("aria-controls"));
      const option = menu?.querySelector(".el-select-dropdown__item");
      if (!option || !option.getBoundingClientRect().height) return false;
      option.click();
      return true;
    })()`, "choose the source on the second card");
    await waitForDocument(page.session, '!document.querySelector(".candidate-layout fieldset:last-of-type .types button").disabled', "second source selected");
    await click(page, ".el-dialog__footer .el-button--primary");
    await waitForDocument(page.session, '!document.querySelector(".candidate-layout")', "saved rules");
    const saved = await apiJson(`/api/workspaces/${workspaceId}/evolution/targets`, authSession.accessToken);
    const policy = saved.items.find((item) => item.id === targetId).candidatePolicy;
    assert.equal(policy.mode, "combined");
    assert.equal(policy.rules.length, 1);
    assert.ok(policy.rules[0].name);
    await waitForDocument(page.session, `document.querySelector('${targetEntry}').parentElement.textContent.includes("1 条")`, "unique source count on card");
    await click(page, targetEntry);
    await waitForDocument(page.session,
      `document.querySelector(".candidate-layout .reports header")?.textContent.includes(${JSON.stringify(policy.rules[0].name)})`,
      "saved source reopens in the report pane");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m11-04 target overview prompts for configuration when no target exists", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: expectedLogEntry,
  });
  try {
    await installBrowser(page, await loginCookie());
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${emptyWorkspaceId}/overview?tab=targets`,
    });
    await waitForDocument(
      page.session,
      `(() => {
        if (!document.querySelector("[data-testid='ov-target-side-empty']")) return null;
        if (!document.querySelector("[data-testid='ov-target-detail-empty']")) return null;
        return document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim();
      })()`,
      "empty target overview",
    );
    await screenshot(page, "04-targets-empty.png");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m11-04 target overview shows disabled objects and re-enables them", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: expectedLogEntry,
  });
  try {
    await installBrowser(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1500,
      height: 1200,
      deviceScaleFactor: 2,
      mobile: false,
    });
    await page.session.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-color-scheme", value: "light" }],
    });

    const ready = await navigateTargets(page);
    assert.equal(ready.targets, "6");
    assert.equal(ready.sideItems, 5);

    await click(page, "[data-testid='ov-target-side-next']");
    await waitForUrlParam(page, "tpage", "2");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length === 1`,
      "second target page",
    );
    await screenshot(page, "disabled-target-side-page2.png", {
      full: false,
      width: 1500,
      height: 1200,
      deviceScaleFactor: 2,
    });

    const disabled = await evaluate(
      page,
      `(() => {
        const row = document.querySelector("[data-testid^='ov-target-side-disabled-row-']");
        const group = document.querySelector("[data-testid='ov-target-side-disabled-group']");
        const stats = document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim();
        const detailTarget = document.querySelector("[data-testid='ov-target-detail-target']");
        const caseTarget = document.querySelector("[data-testid='ov-target-case-target']");
        return {
          exists: Boolean(row),
          text: row?.textContent ?? "",
          group: group?.textContent?.trim() ?? "",
          stats,
          enable: Boolean(row?.querySelector("[data-testid^='ov-target-side-enable-']")),
          selectable: Boolean(row?.querySelector(".select")),
          inDetail: detailTarget
            ? [...detailTarget.options].some((option) => option.value === "40000000-0000-4000-8000-000000000006")
            : null,
          inCases: caseTarget
            ? [...caseTarget.options].some((option) => option.value === "40000000-0000-4000-8000-000000000006")
            : null,
        };
      })()`,
    );
    assert.equal(disabled.exists, true, "disabled target must stay visible");
    assert.match(disabled.text, /m11-04-retired/);
    assert.match(disabled.text, /已停用/);
    assert.match(disabled.group, /已停用对象/);
    assert.equal(disabled.stats, "6");
    assert.equal(disabled.enable, true);
    assert.equal(disabled.selectable, false);
    assert.equal(disabled.inDetail, false);
    assert.equal(disabled.inCases, false);

    await click(page, "[data-testid^='ov-target-side-enable-']");
    const enabled = await waitForDocument(
      page.session,
      `(() => {
        const stats = document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim();
        if (stats === "7") return { ok: true, error: "" };
        const error = document.querySelector(".operation-error")?.textContent?.trim() ?? "";
        return error ? { ok: false, error } : null;
      })()`,
      "enabled target returns to the statistics",
    );
    assert.equal(enabled.ok, true, enabled.error);
    const restored = await evaluate(
      page,
      `(() => ({
        disabled: document.querySelector("[data-testid^='ov-target-side-disabled-row-']") !== null,
        group: document.querySelector("[data-testid='ov-target-side-disabled-group']") !== null,
        stats: document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim(),
      }))()`,
    );
    assert.equal(restored.disabled, false);
    assert.equal(restored.group, false);
    assert.equal(restored.stats, "7");
    await screenshot(page, "disabled-target-enabled-page1.png", {
      full: false,
      width: 1500,
      height: 1200,
      deviceScaleFactor: 2,
    });

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
