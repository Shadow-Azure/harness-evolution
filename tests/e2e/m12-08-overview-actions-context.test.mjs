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
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const captureDir = process.env.HE_M12_08_CAPTURE_DIR;
const secret = "m12-08-overview-context-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminPassword = "m12-08-overview-initial-password";
let adminToken = "";
let adminId = "";
let viewerPassword = "m12-08-viewer-final-password";
let dataWorkspaceId = "";
let day0 = "";
let day1 = "";
let workspaceMemberCount = 0;
const caseCount = 7;

async function cleanupRuntime() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

for (const [signal, exitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  process.once(signal, () => {
    void cleanupRuntime().finally(() => process.exit(exitCode));
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

function shanghaiDate(offsetDays = 0) {
  const now = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
  }).format(now);
}

async function login(username, password) {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "login must set a refresh cookie");
  return { body, cookie };
}

async function changePassword(token, oldPassword, newPassword) {
  const response = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ oldPassword, newPassword }),
  });
  if (response.status !== 204) {
    assert.fail(
      `change-password returned ${response.status}: ${await response.text()}`,
    );
  }
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
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function nextFrame(page) {
  await page.session.send("Runtime.evaluate", {
    expression:
      "new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
    awaitPromise: true,
  });
}

async function captureScreenshot(page, name, { full = false } = {}) {
  if (!captureDir) return;
  await mkdir(captureDir, { recursive: true });
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: full,
  });
  await writeFile(path.join(captureDir, name), Buffer.from(data, "base64"));
}

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource")
  );
}

async function openOverview(page, query = "") {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview${query}`,
  });
  await waitForOverviewRows(page, caseCount);
  return await waitForDocument(
    page.session,
    `(() => {
      const context = document.querySelector("[data-testid='ov-context']");
      const chart = document.querySelector("[data-testid='ov-chart-card']");
      if (!context || !chart) return null;
      return { search: location.search };
    })()`,
    "overview context and chart",
  );
}

async function waitForOverviewRows(page, count) {
  return await waitForDocument(
    page.session,
    `(() => {
      const rows = document.querySelectorAll("[data-testid='ov-case-row']");
      const total = document.querySelector("[data-testid='ov-case-total']");
      if (!total || rows.length !== ${count}) return null;
      return {
        rows: rows.length,
        search: location.search,
        total: total.textContent.trim(),
      };
    })()`,
    `${count} bad-case rows`,
  );
}

async function click(page, selector) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.click();
      return true;
    })()`,
    `click ${selector}`,
  );
}

function clean(value) {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

async function seedOverviewData() {
  const first = await login("admin", adminPassword);
  const replacement = "m12-08-overview-replacement-password";
  await changePassword(first.body.accessToken, adminPassword, replacement);
  adminPassword = replacement;
  const second = await login("admin", adminPassword);
  adminToken = second.body.accessToken;

  const session = await apiJson("/api/auth/session", adminToken);
  adminId = session.user.id;
  assert.equal(session.user.mustChangePassword, false);

  const created = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M12-08 总览",
      mark: "M1208",
      quota: 40,
      spaceAdminIds: [adminId],
    }),
  });
  dataWorkspaceId = created.id;

  const viewer = await apiJson("/api/users", adminToken, {
    method: "POST",
    body: JSON.stringify({
      username: "m12-08-viewer",
      displayName: "只读成员",
      password: "m12-08-viewer-initial-password",
      role: "member",
    }),
  });
  const viewerLogin = await login("m12-08-viewer", "m12-08-viewer-initial-password");
  await changePassword(
    viewerLogin.body.accessToken,
    "m12-08-viewer-initial-password",
    viewerPassword,
  );
  await apiJson(`/api/workspaces/${dataWorkspaceId}/members`, adminToken, {
    method: "POST",
    body: JSON.stringify({ userId: viewer.id, role: "viewer" }),
  });

  const refreshed = await apiJson("/api/auth/session", adminToken);
  const workspace = refreshed.workspaces.find(
    (item) => item.id === dataWorkspaceId,
  );
  assert.ok(workspace, "created workspace must be visible in the session");
  workspaceMemberCount = workspace.memberCount;
  assert.equal(workspaceMemberCount, 2);

  const credential = await apiJson(
    `/api/workspaces/${dataWorkspaceId}/credentials`,
    adminToken,
    { method: "POST" },
  );
  assert.ok(credential.credential);

  day0 = shanghaiDate(0);
  day1 = shanghaiDate(-1);
  const plan = [
    { day: day0, object: "m12-08-alpha", type: "self" },
    { day: day0, object: "m12-08-alpha", type: "self" },
    { day: day0, object: "m12-08-beta", type: "self" },
    { day: day0, object: "m12-08-beta", type: "discovery" },
    { day: day1, object: "m12-08-alpha", type: "self" },
    { day: day1, object: "m12-08-alpha", type: "discovery" },
    { day: day1, object: "m12-08-beta", type: "self" },
  ];
  assert.equal(plan.length, caseCount);
  for (const [index, item] of plan.entries()) {
    const suffix = String(index + 1).padStart(2, "0");
    const response = await fetch(
      `${baseUrl}/api/workspaces/${dataWorkspaceId}/bad-cases`,
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${credential.credential}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          badCaseId: `M12-08-CASE-${suffix}`,
          sessionId: "10000000-0000-4000-8000-000000000001",
          badCaseType: item.type,
          objectName: item.object,
          objectType: "agent",
          objectVersion: "v1",
          title: `M12-08 案例 ${suffix}`,
          reason: `m12-08 overview actions and context ${suffix}`,
          source: "e2e",
          createdAt: `${item.day}T09:${suffix}:00+08:00`,
        }),
      },
    );
    assert.equal(response.status, 201, await response.text());
  }
}

async function viewerCookie() {
  const session = await login("m12-08-viewer", viewerPassword);
  return session.cookie;
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m12-08-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: "m12-08-overview-initial-password",
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_LOGIN_RATE_LIMIT: "100",
    HE_PHASE: "demo",
  };
  const seed = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env: baseEnv,
    encoding: "utf8",
  });
  assert.equal(seed.status, 0, seed.stderr || seed.stdout);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...baseEnv,
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
  await seedOverviewData();
});

after(cleanupRuntime);

test("m12-08 overview exposes admin actions and operational context", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const adminCookie = await login("admin", adminPassword);
    await installBrowser(page, adminCookie.cookie);
    await openOverview(page, "?range=7&grain=day");

    const state = await waitForDocument(
      page.session,
      `(() => {
        const ingest = document.querySelector("[data-testid='ov-action-ingest']");
        const launch = document.querySelector("[data-testid='ov-action-launch']");
        const context = document.querySelector("[data-testid='ov-context']");
        if (!ingest || !launch || !context) return null;
        const text = (selector) =>
          document.querySelector(selector)?.textContent ?? "";
        return {
          href: ingest.getAttribute("href"),
          readonly: Boolean(
            document.querySelector("[data-testid='ov-readonly-actions']"),
          ),
          quota: text("[data-testid='ov-context-quota-used']"),
          percent: text("[data-testid='ov-context-quota-percent']"),
          remaining: text("[data-testid='ov-context-quota-remaining']"),
          endpoint: text("[data-testid='ov-context-endpoint']"),
          endpointFits: (() => {
            const code = document.querySelector(
              "[data-testid='ov-context-endpoint'] code",
            );
            return Boolean(code) && code.scrollWidth <= code.clientWidth + 1;
          })(),
          adminCount: text("[data-testid='ov-context-admin-count']"),
          memberCount: text("[data-testid='ov-context-member-count']"),
          role: text("[data-testid='ov-context-role']"),
          sources: text("[data-testid='ov-context-sources']"),
        };
      })()`,
      "admin actions and operational context",
    );

    assert.equal(state.href, `/workspaces/${dataWorkspaceId}/admin?tab=ingest`);
    assert.equal(state.readonly, false);
    assert.equal(clean(state.quota), "7 / 40");
    assert.equal(clean(state.percent), "18% 已使用");
    assert.equal(clean(state.remaining), "剩余 33");
    assert.ok(
      clean(state.endpoint).includes(
        `${baseUrl}/api/workspaces/${dataWorkspaceId}/bad-cases`,
      ),
      state.endpoint,
    );
    assert.equal(state.endpointFits, true);
    assert.equal(clean(state.adminCount), "1 人");
    assert.equal(clean(state.memberCount), `${workspaceMemberCount} 人`);
    assert.equal(clean(state.role), "全局管理员");
    assert.equal(clean(state.sources), "2 个");
    if (captureDir) {
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width: 1408,
        height: 788,
        deviceScaleFactor: 2,
        mobile: false,
      });
      await page.session.send("Page.navigate", {
        url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview`,
      });
      await waitForOverviewRows(page, caseCount);
      await waitForDocument(
        page.session,
        `Boolean(document.querySelector("[data-testid='ov-matrix-toggle']"))`,
        "matrix entry before capture",
      );
      await nextFrame(page);
      await captureScreenshot(page, "after-overview-admin.png");
    }
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-08 overview entry points reuse the admin page and wizard and keep filters on back", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const adminCookie = await login("admin", adminPassword);
    await installBrowser(page, adminCookie.cookie);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview?range=7&grain=day&objects=m12-08-alpha&lobject=m12-08-alpha`,
    });
    await waitForOverviewRows(page, 4);
    const before = await waitForDocument(
      page.session,
      `({ search: location.search, rows: document.querySelectorAll("[data-testid='ov-case-row']").length })`,
      "overview filter baseline",
    );

    await click(page, "[data-testid='ov-action-ingest']");
    const admin = await waitForDocument(
      page.session,
      `(() => {
        if (!location.pathname.endsWith("/admin")) return null;
        const search = new URLSearchParams(location.search);
        if (search.get("tab") !== "ingest") return null;
        if (!document.querySelector("[data-testid='workspace-admin-page']")) return null;
        if (!document.querySelector("[data-testid='ingest-tab']")) return null;
        return { path: location.pathname, search: location.search };
      })()`,
      "workspace admin ingest tab",
    );
    assert.equal(admin.path, `/workspaces/${dataWorkspaceId}/admin`);

    await page.session.send("Runtime.evaluate", {
      expression: "history.back()",
    });
    const restored = await waitForDocument(
      page.session,
      `(() => {
        if (!location.pathname.endsWith("/overview")) return null;
        const search = new URLSearchParams(location.search);
        if (search.get("range") !== "7") return null;
        if (search.get("grain") !== "day") return null;
        if (search.get("objects") !== "m12-08-alpha") return null;
        if (search.get("lobject") !== "m12-08-alpha") return null;
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (rows.length !== 4) return null;
        return { search: location.search, rows: rows.length };
      })()`,
      "overview filters restored after back",
    );
    assert.equal(restored.search, before.search);
    assert.equal(restored.rows, before.rows);

    await click(page, "[data-testid='ov-action-launch']");
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='launch-wizard']"))`,
      "launch wizard",
    );
    await click(page, "[aria-label='关闭向导']");
    await waitForDocument(
      page.session,
      `(() => {
        if (document.querySelector("[data-testid='launch-wizard']")) return null;
        if (!location.pathname.endsWith("/overview")) return null;
        if (new URLSearchParams(location.search).get("objects") !== "m12-08-alpha") {
          return null;
        }
        return true;
      })()`,
      "wizard closed without losing overview filters",
    );
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-08 read-only member sees no write actions but keeps the overview", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page, await viewerCookie());
    await openOverview(page, "?range=7&grain=day");

    const state = await waitForDocument(
      page.session,
      `(() => {
        const readonly = document.querySelector("[data-testid='ov-readonly-actions']");
        const context = document.querySelector("[data-testid='ov-context']");
        if (!readonly || !context) return null;
        return {
          ingest: Boolean(document.querySelector("[data-testid='ov-action-ingest']")),
          launch: Boolean(document.querySelector("[data-testid='ov-action-launch']")),
          ingestLink: Boolean(
            document.querySelector("[data-testid='ov-context-ingest-link']"),
          ),
          readonly: readonly.textContent ?? "",
          role: document.querySelector("[data-testid='ov-context-role']")
            ?.textContent ?? "",
          rows: document.querySelectorAll("[data-testid='ov-case-row']").length,
        };
      })()`,
      "read-only overview",
    );

    assert.equal(state.ingest, false);
    assert.equal(state.launch, false);
    assert.equal(state.ingestLink, false);
    assert.match(clean(state.readonly), /只读访问/);
    assert.equal(clean(state.role), "只读成员");
    assert.equal(state.rows, caseCount);
    if (captureDir) {
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width: 1408,
        height: 788,
        deviceScaleFactor: 2,
        mobile: false,
      });
      await page.session.send("Page.navigate", {
        url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview`,
      });
      await waitForOverviewRows(page, caseCount);
      await waitForDocument(
        page.session,
        `Boolean(document.querySelector("[data-testid='ov-readonly-actions']"))`,
        "read-only notice before capture",
      );
      await nextFrame(page);
      await captureScreenshot(page, "after-overview-viewer.png");
    }
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-08 source × time matrix shows counts inside the active window", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const adminCookie = await login("admin", adminPassword);
    await installBrowser(page, adminCookie.cookie);
    await openOverview(page, "?range=7&grain=day");

    await click(page, "[data-testid='ov-matrix-toggle']");
    const matrix = await waitForDocument(
      page.session,
      `(() => {
        const rows = document.querySelectorAll("[data-testid='ov-matrix-row']");
        const alpha = document.querySelector("[data-testid='ov-matrix-row'][data-object='m12-08-alpha']");
        const beta = document.querySelector("[data-testid='ov-matrix-row'][data-object='m12-08-beta']");
        if (rows.length !== 2 || !alpha || !beta) return null;
        const cell = (row, bucket) => {
          const element = row.querySelector("td[data-bucket='" + bucket + "']");
          return element ? element.textContent.replace(/\\s+/g, " ").trim() : null;
        };
        const total = (row) =>
          row.querySelector("td.total")?.textContent
            ?.replace(/\\s+/g, " ")
            .trim() ?? null;
        const alphaToday = cell(alpha, ${JSON.stringify(day0)});
        const alphaYesterday = cell(alpha, ${JSON.stringify(day1)});
        const betaToday = cell(beta, ${JSON.stringify(day0)});
        if (!alphaToday || !alphaYesterday || !betaToday) return null;
        return {
          rows: rows.length,
          alphaToday,
          alphaYesterday,
          alphaTotal: total(alpha),
          betaToday,
          betaTotal: total(beta),
        };
      })()`,
      "source × time matrix",
    );

    assert.equal(matrix.rows, 2);
    assert.equal(matrix.alphaToday, "自身 2 / 前置 0");
    assert.equal(matrix.alphaYesterday, "自身 1 / 前置 1");
    assert.equal(matrix.alphaTotal, "3 / 1");
    assert.equal(matrix.betaToday, "自身 1 / 前置 1");
    assert.equal(matrix.betaTotal, "2 / 1");
    const matrixLayout = await waitForDocument(
      page.session,
      `(() => {
        const card = document.querySelector("[data-testid='ov-chart-card']");
        const nums = [...document.querySelectorAll(".source-bars .num")];
        const scroll = document.querySelector("[data-testid='ov-matrix-scroll']");
        if (!card || nums.length === 0 || !scroll) return null;
        const cardBox = card.getBoundingClientRect();
        return {
          cardRight: cardBox.right,
          maxNumberRight: Math.max(
            ...nums.map((node) => node.getBoundingClientRect().right),
          ),
        };
      })()`,
      "matrix layout bounds",
    );
    assert.ok(
      matrixLayout.maxNumberRight <= matrixLayout.cardRight + 1,
      `source bars must stay inside the chart card: ${JSON.stringify(matrixLayout)}`,
    );
    if (captureDir) {
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width: 1408,
        height: 788,
        deviceScaleFactor: 2,
        mobile: false,
      });
      await page.session.send("Runtime.evaluate", {
        expression:
          "document.querySelector(\"[data-testid='ov-source-matrix']\")?.scrollIntoView({ block: 'center' })",
      });
      await nextFrame(page);
      await captureScreenshot(page, "after-overview-matrix.png");
    }
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-08 overview keeps a two-column desktop and stacks trend, list, context on narrow screens", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const adminCookie = await login("admin", adminPassword);
    await installBrowser(page, adminCookie.cookie);

    const measure = async (width, height, mobile) => {
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile,
      });
      await openOverview(page, "?range=7&grain=day");
      return await waitForDocument(
        page.session,
        `(() => {
          const chart = document.querySelector("[data-testid='ov-chart-card']");
          const side = document.querySelector("[data-testid='ov-context']");
          const list = document.querySelector("[data-testid='ov-case-list']");
          if (!chart || !side || !list) return null;
          const box = (element) => {
            const rect = element.getBoundingClientRect();
            return {
              left: rect.left,
              right: rect.right,
              top: rect.top,
              bottom: rect.bottom,
              width: rect.width,
            };
          };
          const result = {
            chart: box(chart),
            side: box(side),
            list: box(list),
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
          };
          if (![result.chart, result.side, result.list].every((box) => box.width > 0)) {
            return null;
          }
          return result;
        })()`,
        `${width}px overview layout`,
      );
    };

    const desktop = await measure(1440, 900, false);
    if (captureDir) await captureScreenshot(page, "after-overview-1440.png");
    assert.ok(
      desktop.side.left >= desktop.chart.right - 1,
      `context must sit beside the trend: ${JSON.stringify(desktop)}`,
    );
    assert.ok(
      desktop.list.top >= desktop.chart.bottom - 1,
      `list must start below the trend row: ${JSON.stringify(desktop)}`,
    );
    assert.equal(desktop.scrollWidth, desktop.clientWidth);

    const tablet = await measure(1024, 900, false);
    if (captureDir) await captureScreenshot(page, "after-overview-1024.png");
    assert.ok(
      tablet.chart.top < tablet.list.top && tablet.list.top < tablet.side.top,
      `narrow order must be trend, list, context: ${JSON.stringify(tablet)}`,
    );
    assert.ok(
      tablet.side.top >= tablet.list.bottom - 1,
      `context must follow the list: ${JSON.stringify(tablet)}`,
    );
    assert.equal(tablet.scrollWidth, tablet.clientWidth);

    const mobile = await measure(390, 844, true);
    await click(page, "[data-testid='ov-matrix-toggle']");
    const mobileMatrix = await waitForDocument(
      page.session,
      `(() => {
        const scroll = document.querySelector("[data-testid='ov-matrix-scroll']");
        if (!scroll || scroll.scrollWidth <= scroll.clientWidth) return null;
        return {
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "mobile matrix internal scroll",
    );
    assert.equal(mobileMatrix.pageScrollWidth, mobileMatrix.pageClientWidth);
    if (captureDir) {
      await captureScreenshot(page, "after-overview-390-full.png", {
        full: true,
      });
    }
    assert.ok(
      mobile.chart.top < mobile.list.top && mobile.list.top < mobile.side.top,
      `mobile order must be trend, list, context: ${JSON.stringify(mobile)}`,
    );
    assert.ok(
      mobile.side.top >= mobile.list.bottom - 1,
      `mobile context must follow the list: ${JSON.stringify(mobile)}`,
    );
    assert.equal(mobile.scrollWidth, mobile.clientWidth);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
