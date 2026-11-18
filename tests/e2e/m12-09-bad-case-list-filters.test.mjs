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
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m12-09-smoke-initial-password";
const replacementPassword = "m12-09-smoke-replacement-password";
const secret = "m12-09-smoke-signing-secret-with-sufficient-length";
const screenshotDir = process.env.M12_09_SCREENSHOT_DIR ?? "";
const sessionId = "10000000-0000-4000-8000-000000000001";
const pageSize = 8;
const recentCount = 12;
const oldCount = 2;
const totalCount = recentCount + oldCount;
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let workspaceId = "";
let credential = "";
let adminToken = "";
let currentPassword = initialPassword;
let today = "";
let yesterday = "";
let oldDay = "";

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
    width: 1408,
    height: 900,
    deviceScaleFactor: 2,
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

async function openOverview(page, search = "") {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${workspaceId}/overview${search}`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const list = document.querySelector("[data-testid='ov-case-list']");
      const filters = document.querySelector("[data-testid='ov-case-filters']");
      const total = document.querySelector("[data-testid='ov-case-total']")
        ?.textContent?.trim() ?? "";
      if (!list || !filters || !/^共 \\d+ 条$/.test(total)) return null;
      return {
        search: location.search,
        rows: document.querySelectorAll("[data-testid='ov-case-row']").length,
        total,
        pager: document.querySelector("[data-testid='ov-pager']")
          ?.textContent?.trim() ?? "",
      };
    })()`,
    "overview list with filters",
  );
}

async function waitForCaseRows(page, count, total = null) {
  const totalCheck =
    total === null
      ? ""
      : `if (total !== "共 ${total} 条") return null;`;
  return await waitForDocument(
    page.session,
    `(() => {
      const rows = document.querySelectorAll("[data-testid='ov-case-row']");
      if (rows.length !== ${count}) return null;
      const total = document.querySelector("[data-testid='ov-case-total']")
        ?.textContent?.trim() ?? "";
      ${totalCheck}
      return {
        search: location.search,
        rows: rows.length,
        total,
        pager: document.querySelector("[data-testid='ov-pager']")
          ?.textContent?.trim() ?? "",
      };
    })()`,
    total === null ? `${count} bad-case rows` : `${count} rows with total ${total}`,
  );
}

async function screenshot(page, name, full = true) {
  if (!screenshotDir) return;
  await mkdir(screenshotDir, { recursive: true });
  await page.session.send("Page.enable");
  const contentHeight = await evaluate(
    page,
    `document.querySelector("[data-testid='overview-page']")?.scrollHeight ?? 0`,
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1408,
    height: full ? Math.max(900, Number(contentHeight) + 40) : 900,
    deviceScaleFactor: 2,
    mobile: false,
  });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
  });
  await writeFile(
    path.join(screenshotDir, name),
    Buffer.from(result.data, "base64"),
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1408,
    height: 900,
    deviceScaleFactor: 2,
    mobile: false,
  });
}

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource") ||
    entry.text.includes("Page entered Back-Forward Cache")
  );
}

function shanghaiDate(offsetDays = 0) {
  const now = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
  }).format(now);
}

async function seedWorkspace() {
  const session = await apiJson("/api/auth/session", adminToken);
  const created = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M12-09 列表筛选",
      mark: "M1209",
      quota: 60,
      spaceAdminIds: [session.user.id],
    }),
  });
  workspaceId = created.id;
  const createdCredential = await apiJson(
    `/api/workspaces/${workspaceId}/credentials`,
    adminToken,
    { method: "POST" },
  );
  credential = createdCredential.credential;

  today = shanghaiDate(0);
  yesterday = shanghaiDate(-1);
  oldDay = shanghaiDate(-120);
  const plan = Array.from({ length: recentCount }, (_, index) => ({
    day: index < recentCount / 2 ? today : yesterday,
    object: index < recentCount / 2 ? "alpha" : "beta",
    type: index % 2 === 0 ? "self" : "discovery",
  }));
  plan.push(
    { day: oldDay, object: "alpha", type: "self" },
    { day: oldDay, object: "beta", type: "discovery" },
  );
  assert.equal(plan.length, totalCount);

  for (const [index, item] of plan.entries()) {
    const suffix = String(index + 1).padStart(2, "0");
    const response = await fetch(
      `${baseUrl}/api/workspaces/${workspaceId}/bad-cases`,
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${credential}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          badCaseId: `M12-09-CASE-${suffix}`,
          sessionId,
          badCaseType: item.type,
          objectName: item.object,
          objectType: "agent",
          objectVersion: "v1",
          title: `M12-09 列表筛选案例 ${suffix}`,
          reason: `m12-09 list filter case ${suffix}`,
          source: "e2e",
          createdAt: `${item.day}T09:${suffix}:00+08:00`,
        }),
      },
    );
    assert.equal(response.status, 201, await response.text());
  }
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m12-09-e2e-"));
  const seedEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_LOGIN_RATE_LIMIT: "100",
    HE_PHASE: "demo",
  };
  const seed = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env: seedEnv,
    encoding: "utf8",
  });
  assert.equal(seed.status, 0, seed.stderr || seed.stdout);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...seedEnv,
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

  const auth = await loginAndRotatePassword();
  assert.equal(auth.accessToken.length > 0, true);
  adminToken = auth.accessToken;
  await seedWorkspace();
});

after(cleanup);

test("m12-09 list defaults to all time while the chart keeps its window", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const requests = [];
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      if (request.url.includes("/api/workspaces/")) requests.push(request.url);
    });
    await installBrowser(page, await loginCookie());
    await openOverview(page);
    const state = await waitForCaseRows(page, pageSize, totalCount);

    assert.equal(new URLSearchParams(state.search).get("range"), "90");
    assert.equal(state.rows, pageSize);
    assert.equal(state.total, `共 ${totalCount} 条`);

    const casesUrl = new URL(
      requests.find((url) => url.includes(`/workspaces/${workspaceId}/bad-cases`)),
    );
    assert.equal(casesUrl.searchParams.get("allTime"), "true");
    assert.equal(casesUrl.searchParams.has("from"), false);
    assert.equal(casesUrl.searchParams.has("range"), false);
    const summaryUrl = new URL(
      requests.find((url) => url.includes("/overview/summary")),
    );
    assert.equal(summaryUrl.searchParams.get("range"), "90");

    // The 120-day-old rows are only visible because the list is unrestricted;
    // the chart's default window cannot contain them.
    const server = await apiJson(
      `/api/workspaces/${workspaceId}/bad-cases?allTime=true&pageSize=50`,
      adminToken,
    );
    assert.equal(server.total, totalCount);
    assert.ok(server.items.some((item) => item.createdAt.startsWith(oldDay)));

    await screenshot(page, "after-overview-all-time.png");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-09 list filters combine, reset paging and survive a reload", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const requests = [];
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      if (request.url.includes(`/workspaces/${workspaceId}/bad-cases`)) {
        requests.push(request.url);
      }
    });
    await installBrowser(page, await loginCookie());
    await openOverview(page);

    await setControl(page, "[data-testid='ov-list-from']", yesterday);
    await setControl(page, "[data-testid='ov-list-to']", today);
    let state = await waitForCaseRows(page, pageSize, recentCount);
    assert.equal(state.total, `共 ${recentCount} 条`);

    await setControl(page, "[data-testid='ov-list-object']", "alpha");
    state = await waitForCaseRows(page, 6, 6);
    assert.equal(state.total, "共 6 条");

    await setControl(page, "[data-testid='ov-list-type']", "self");
    state = await waitForCaseRows(page, 3, 3);
    assert.equal(state.total, "共 3 条");
    let search = new URLSearchParams(state.search);
    assert.equal(search.get("lfrom"), yesterday);
    assert.equal(search.get("lto"), today);
    assert.equal(search.get("lobject"), "alpha");
    assert.equal(search.get("type"), "self");
    assert.equal(search.get("page"), null);

    const lastUrl = new URL(requests.at(-1));
    assert.equal(lastUrl.searchParams.get("from"), yesterday);
    assert.equal(lastUrl.searchParams.get("to"), today);
    assert.equal(lastUrl.searchParams.get("objects"), "alpha");
    assert.equal(lastUrl.searchParams.get("badCaseType"), "self");
    assert.equal(lastUrl.searchParams.get("page"), "1");
    assert.equal(lastUrl.searchParams.has("allTime"), false);

    await screenshot(page, "after-overview-filtered.png");

    await page.session.send("Page.reload");
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        const from = document.querySelector("[data-testid='ov-list-from']");
        const to = document.querySelector("[data-testid='ov-list-to']");
        const object = document.querySelector("[data-testid='ov-list-object']");
        const type = document.querySelector("[data-testid='ov-list-type']");
        if (!from || !to || !object || !type) return null;
        if (rows.length !== 3) return null;
        const search = new URLSearchParams(location.search);
        return {
          from: from.value,
          to: to.value,
          object: object.value,
          type: type.value,
          lfrom: search.get("lfrom"),
          lto: search.get("lto"),
          lobject: search.get("lobject"),
          filterType: search.get("type"),
        };
      })()`,
      "list filters restored after reload",
    );
    assert.deepEqual(restored, {
      from: yesterday,
      to: today,
      object: "alpha",
      type: "self",
      lfrom: yesterday,
      lto: today,
      lobject: "alpha",
      filterType: "self",
    });
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-09 invalid dates keep the previous result and explain the fix", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const requests = [];
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      if (request.url.includes(`/workspaces/${workspaceId}/bad-cases`)) {
        requests.push(request.url);
      }
    });
    await installBrowser(page, await loginCookie());
    await openOverview(page, "?lfrom=2026-01-01&lto=2026-01-31");
    await waitForDocument(
      page.session,
      `(() => {
        const total = document.querySelector("[data-testid='ov-case-total']")
          ?.textContent?.trim() ?? "";
        const empty = document.querySelector("[data-testid='ov-case-empty']");
        if (!empty || total !== "共 0 条") return null;
        return { total };
      })()`,
      "empty result for the old date window",
    );
    const before = requests.length;

    await setControl(page, "[data-testid='ov-list-from']", today);
    await setControl(page, "[data-testid='ov-list-to']", yesterday);
    const error = await waitForDocument(
      page.session,
      `(() => {
        const element = document.querySelector("[data-testid='ov-list-date-error']");
        if (!element) return null;
        return { text: element.textContent?.trim() ?? "" };
      })()`,
      "invalid list date error",
    );
    assert.ok(error.text.includes("开始日期不能晚于结束日期"));
    assert.equal(requests.length, before, "invalid dates must not refetch");
    await screenshot(page, "after-overview-invalid-date.png");
    const search = new URLSearchParams(
      await evaluate(page, "location.search"),
    );
    assert.equal(search.get("lfrom"), "2026-01-01");
    assert.equal(search.get("lto"), "2026-01-31");

    await setControl(page, "[data-testid='ov-list-from']", "");
    await setControl(page, "[data-testid='ov-list-to']", "");
    const cleared = await waitForCaseRows(page, pageSize, totalCount);
    assert.equal(cleared.total, `共 ${totalCount} 条`);
    const clearedUrl = new URL(requests.at(-1));
    assert.equal(clearedUrl.searchParams.get("allTime"), "true");
    assert.equal(clearedUrl.searchParams.has("from"), false);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-09 filter miss is distinct from an empty workspace and clears", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page, await loginCookie());
    await openOverview(page);

    await setControl(page, "[data-testid='ov-list-from']", today);
    await setControl(page, "[data-testid='ov-list-to']", today);
    await setControl(page, "[data-testid='ov-list-object']", "beta");
    const empty = await waitForDocument(
      page.session,
      `(() => {
        const element = document.querySelector("[data-testid='ov-case-empty']");
        if (!element) return null;
        const clear = document.querySelector("[data-testid='ov-case-empty-clear']");
        return {
          text: element.textContent?.trim() ?? "",
          hasClear: Boolean(clear),
        };
      })()`,
      "filtered empty state",
    );
    assert.ok(empty.text.includes("当前筛选没有命中 bad case"));
    assert.equal(empty.hasClear, true);
    await screenshot(page, "after-overview-empty.png");

    await click(page, "[data-testid='ov-case-empty-clear']");
    const cleared = await waitForCaseRows(page, pageSize, totalCount);
    assert.equal(cleared.total, `共 ${totalCount} 条`);
    const search = new URLSearchParams(cleared.search);
    assert.equal(search.get("lfrom"), null);
    assert.equal(search.get("lobject"), null);
    assert.equal(search.get("type"), null);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-09 paging keeps filters, a filter change resets to page one, and back restores", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page, await loginCookie());
    await openOverview(page, `?lfrom=${yesterday}&lto=${today}`);
    await waitForCaseRows(page, pageSize, recentCount);

    await click(page, "[data-testid='ov-page-next']");
    let state = await waitForCaseRows(page, recentCount - pageSize, recentCount);
    let search = new URLSearchParams(state.search);
    assert.equal(search.get("page"), "2");
    assert.equal(search.get("lfrom"), yesterday);
    assert.equal(search.get("lto"), today);
    assert.equal(state.pager.includes("第 2 / 2 页"), true);

    await setControl(page, "[data-testid='ov-list-type']", "discovery");
    state = await waitForCaseRows(page, 6, 6);
    search = new URLSearchParams(state.search);
    assert.equal(search.get("page"), null);
    assert.equal(search.get("lfrom"), yesterday);
    assert.equal(search.get("lto"), today);
    assert.equal(search.get("type"), "discovery");

    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${workspaceId}/overview?lfrom=${yesterday}&lto=${today}&lobject=beta`,
    });
    await waitForCaseRows(page, 6, 6);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${workspaceId}/overview`,
    });
    await waitForCaseRows(page, pageSize, totalCount);
    await evaluate(page, "history.back()");
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const search = new URLSearchParams(location.search);
        if (search.get("lfrom") !== ${JSON.stringify(yesterday)}) return null;
        if (search.get("lto") !== ${JSON.stringify(today)}) return null;
        if (search.get("lobject") !== "beta") return null;
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (rows.length !== 6) return null;
        return { rows: rows.length, search: location.search };
      })()`,
      "browser back restores list filters",
    );
    assert.equal(restored.rows, 6);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-09 list filters fit a 390px viewport without horizontal overflow", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 2,
      mobile: true,
    });
    await openOverview(page);
    const overflow = await evaluate(
      page,
      `document.documentElement.scrollWidth - document.documentElement.clientWidth`,
    );
    assert.ok(overflow <= 0, `unexpected horizontal overflow: ${overflow}`);
    await screenshot(page, "after-overview-390.png");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
