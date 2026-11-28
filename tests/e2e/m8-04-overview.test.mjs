import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
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
const secret = "m8-04-overview-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminPassword = "m8-04-overview-initial-password";
let adminToken = "";
let adminId = "";
let dataWorkspaceId = "";
let emptyWorkspaceId = "";
let day0 = "";
let day1 = "";
let day2 = "";
const caseCount = 11;

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

function shiftDate(day, offsetDays) {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + offsetDays))
    .toISOString()
    .slice(0, 10);
}

function weekStart(day) {
  const [year, month, date] = day.split("-").map(Number);
  const weekday = (new Date(Date.UTC(year, month - 1, date)).getUTCDay() + 6) % 7;
  return shiftDate(day, -weekday);
}

async function loginCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: adminPassword }),
  });
  assert.equal(response.status, 200);
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "login must set a refresh cookie");
  return cookie;
}

async function installBrowser(page) {
  const cookie = await loginCookie();
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
    deviceScaleFactor: 1,
    mobile: false,
  });
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
  await waitForDocument(
    page.session,
    `(() => {
      const rows = document.querySelectorAll("[data-testid='ov-case-row']");
      const total = document.querySelector("[data-testid='ov-case-total']");
      if (!total) return null;
      return { path: location.pathname, search: location.search, rows: rows.length };
    })()`,
    "overview page data",
  );
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

async function chooseSource(page, objectName) {
  await waitForDocument(
    page.session,
    `(() => {
      const details = document.querySelector("[data-testid='ov-source-select']");
      if (!details) return null;
      details.open = true;
      const checkbox = document.querySelector(
        "[data-object='${objectName}']",
      );
      if (!checkbox) return null;
      if (!checkbox.checked) checkbox.click();
      return checkbox.checked;
    })()`,
    `choose source ${objectName}`,
  );
}

async function waitForSearchParam(page, key, value) {
  await waitForDocument(
    page.session,
    `new URLSearchParams(location.search).get(${JSON.stringify(key)}) === ${JSON.stringify(value)}`,
    `URL parameter ${key}=${value}`,
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

async function waitForCaseRows(page, count) {
  return await waitForDocument(
    page.session,
    `(() => {
      const rows = document.querySelectorAll("[data-testid='ov-case-row']");
      if (rows.length !== ${count}) return null;
      return {
        rows: rows.length,
        search: location.search,
        total: document.querySelector("[data-testid='ov-case-total']")?.textContent ?? "",
      };
    })()`,
    `${count} bad-case rows`,
  );
}

async function seedOverviewData() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: adminPassword }),
  });
  assert.equal(login.status, 200);
  const loginBody = await login.json();
  assert.ok(loginBody.accessToken);
  const replacement = "m8-04-overview-replacement-password";
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${loginBody.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: adminPassword,
      newPassword: replacement,
    }),
  });
  assert.equal(changed.status, 204);
  adminPassword = replacement;
  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: `refresh_token=${
        login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1]
      }`,
    },
  });
  assert.equal(refreshed.status, 200);
  const refreshedBody = await refreshed.json();
  adminToken = refreshedBody.accessToken;

  const session = await apiJson("/api/auth/session", adminToken);
  adminId = session.user.id;
  assert.equal(session.user.mustChangePassword, false);

  const created = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M8-04 总览",
      mark: "M804",
      quota: 40,
      spaceAdminIds: [adminId],
    }),
  });
  dataWorkspaceId = created.id;
  const empty = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M8-04 空空间",
      mark: "M8E",
      quota: 10,
      spaceAdminIds: [adminId],
    }),
  });
  emptyWorkspaceId = empty.id;

  const credential = await apiJson(
    `/api/workspaces/${dataWorkspaceId}/credentials`,
    adminToken,
    { method: "POST" },
  );
  assert.ok(credential.credential);

  day0 = shanghaiDate(0);
  day1 = shanghaiDate(-1);
  day2 = shanghaiDate(-2);
  const plan = [
    ...Array.from({ length: 6 }, (_, index) => ({
      day: day0,
      object: index < 4 ? "m8-04-alpha" : "m8-04-beta",
      type: index < 5 ? "self" : "discovery",
    })),
    ...Array.from({ length: 5 }, (_, index) => ({
      day: day1,
      object: index < 2 ? "m8-04-alpha" : "m8-04-beta",
      type: index < 2 ? "discovery" : index === 2 ? "self" : "discovery",
    })),
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
          badCaseId: `M8-04-CASE-${suffix}`,
          // Point at a normalized corpus Session so the overview rows stay
          // ready; the trace-state journey lives in m12-07.
          sessionId: "10000000-0000-4000-8000-000000000001",
          badCaseType: item.type,
          objectName: item.object,
          objectType: "agent",
          objectVersion: "v1",
          title: `M8-04 案例 ${suffix}`,
          reason: `m8-04 overview e2e case ${suffix}`,
          source: "e2e",
          createdAt: `${item.day}T09:${suffix}:00+08:00`,
        }),
      },
    );
    assert.equal(response.status, 201, await response.text());
  }
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m8-04-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: "m8-04-overview-initial-password",
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

test("m8-04 overview lands on the workspace overview by default", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/ws-default`,
    });
    const landing = await waitForDocument(
      page.session,
      `(() => {
        const stats = document.querySelector("[data-testid='ov-statstrip']");
        const nav = document.querySelector("#tn-overview");
        if (location.pathname !== "/workspaces/ws-default/overview") return null;
        if (!stats || !nav) return null;
        const cells = [...stats.querySelectorAll(".ss")].map((cell) => ({
          value: cell.querySelector("b")?.textContent?.trim() ?? "",
          label: cell.querySelector("span")?.textContent?.trim() ?? "",
        }));
        if (cells.length !== 6) return null;
        if (!cells.every((cell) => /^\\d+(\\s\\/\\s\\d+)?$/.test(cell.value))) {
          return null;
        }
        return {
          path: location.pathname,
          search: location.search,
          cells,
          navActive: nav.classList.contains("active"),
          hasChart: Boolean(document.querySelector("[data-testid='ov-chart-card']")),
          hasList: Boolean(document.querySelector("[data-testid='ov-case-list']")),
        };
      })()`,
      "default workspace overview landing",
    );

    assert.equal(landing.path, "/workspaces/ws-default/overview");
    const search = new URLSearchParams(landing.search);
    assert.equal(search.get("tab"), "cases");
    assert.equal(search.get("range"), "90");
    assert.equal(search.get("grain"), "week");
    assert.equal(landing.cells.length, 6);
    assert.ok(landing.cells.every((cell) => /^\d+(\s\/\s\d+)?$/.test(cell.value)));
    assert.deepEqual(
      landing.cells.map((cell) => cell.label),
      [
        "bad case 总数",
        "自身存在问题",
        "发现前置步骤问题",
        "关联 Session",
        "来源数",
        "额度",
      ],
    );
    assert.equal(landing.navActive, true);
    assert.equal(landing.hasChart, true);
    assert.equal(landing.hasList, true);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview global filters stay independent from the list filters", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await openOverview(page);

    let state = await waitForCaseRows(page, 8);
    assert.equal(state.search.includes("range=90"), true);
    await click(page, "[data-testid='ov-page-next']");
    state = await waitForCaseRows(page, 3);
    assert.equal(new URLSearchParams(state.search).get("page"), "2");
    assert.equal(state.total, "共 11 条");

    // The chart's range, grain and source keep their own context: none of them
    // narrows the list or resets its page.
    await click(page, "[data-testid='ov-range-7']");
    await waitForSearchParam(page, "range", "7");
    await click(page, "[data-testid='ov-grain-day']");
    await waitForSearchParam(page, "grain", "day");
    await chooseSource(page, "m8-04-alpha");
    await waitForSearchParam(page, "objects", "m8-04-alpha");
    state = await waitForCaseRows(page, 3);
    assert.equal(new URLSearchParams(state.search).get("page"), "2");
    assert.equal(state.total, "共 11 条");

    await click(page, "[data-testid='ov-page-prev']");
    state = await waitForCaseRows(page, 8);
    assert.equal(new URLSearchParams(state.search).get("page"), null);

    // The list's own controls narrow it, reset the page and keep the global
    // objects filter in the URL.
    await setControl(page, "[data-testid='ov-list-object']", "m8-04-alpha");
    state = await waitForCaseRows(page, 6);
    assert.equal(
      new URLSearchParams(state.search).get("lobject"),
      "m8-04-alpha",
    );
    assert.equal(state.total, "共 6 条");
    await setControl(page, "[data-testid='ov-list-type']", "self");
    state = await waitForCaseRows(page, 4);
    assert.equal(new URLSearchParams(state.search).get("type"), "self");
    assert.equal(state.total, "共 4 条");

    await page.session.send("Page.reload");
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        const search = new URLSearchParams(location.search);
        const object = document.querySelector("[data-testid='ov-list-object']");
        const type = document.querySelector("[data-testid='ov-list-type']");
        if (rows.length !== 4 || !object || !type) return null;
        return {
          rows: rows.length,
          range: search.get("range"),
          grain: search.get("grain"),
          objects: search.get("objects"),
          lobject: search.get("lobject"),
          type: search.get("type"),
        };
      })()`,
      "list filters restored after reload",
    );
    assert.equal(restored.range, "7");
    assert.equal(restored.grain, "day");
    assert.equal(restored.objects, "m8-04-alpha");
    assert.equal(restored.lobject, "m8-04-alpha");
    assert.equal(restored.type, "self");

    // Resetting the list leaves the chart context alone, and clearing the chart
    // leaves the (already empty) list alone.
    await click(page, "[data-testid='ov-list-reset']");
    state = await waitForCaseRows(page, 8);
    assert.equal(state.total, "共 11 条");
    assert.equal(new URLSearchParams(state.search).get("lobject"), null);
    assert.equal(new URLSearchParams(state.search).get("type"), null);
    assert.equal(new URLSearchParams(state.search).get("objects"), "m8-04-alpha");

    await click(page, "[data-testid='ov-clear']");
    await waitForSearchParam(page, "range", "90");
    const cleared = await waitForCaseRows(page, 8);
    assert.equal(new URLSearchParams(cleared.search).get("objects"), null);
    assert.equal(new URLSearchParams(cleared.search).get("range"), "90");
    assert.equal(new URLSearchParams(cleared.search).get("grain"), "week");
    assert.equal(cleared.total, "共 11 条");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview bucket click and case deep link target the right rows", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview?range=custom&from=${day2}&to=${day0}&grain=day`,
    });
    await waitForCaseRows(page, 8);
    await click(
      page,
      `[data-bucket='${day1}']`,
    );
    const filtered = await waitForCaseRows(page, 5);
    const search = new URLSearchParams(filtered.search);
    assert.equal(search.get("range"), "custom");
    assert.equal(search.get("from"), day2);
    assert.equal(search.get("to"), day0);
    assert.equal(search.get("lfrom"), day1);
    assert.equal(search.get("lto"), day1);
    assert.equal(filtered.total, "共 5 条");

    const deepLink = await waitForDocument(
      page.session,
      `(() => {
        const link = document.querySelector(
          "[data-testid='ov-case-link-M8-04-CASE-09']",
        );
        if (!link) return null;
        return {
          href: link.getAttribute("href"),
          target: link.getAttribute("target"),
          rel: link.getAttribute("rel"),
        };
      })()`,
      "case deep link",
    );
    assert.equal(
      deepLink.href,
      `/workspaces/${dataWorkspaceId}/sessions/10000000-0000-4000-8000-000000000001/errors?case=M8-04-CASE-09&tab=desc`,
    );
    assert.equal(deepLink.target, "_blank");
    assert.equal(deepLink.rel, "noopener");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview deep link opens the seeded case description tab", async () => {
  const page = await createBrowserPage();
  try {
    await installBrowser(page);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/ws-default/overview?lfrom=2026-10-01&lto=2026-10-31`,
    });
    const link = await waitForDocument(
      page.session,
      `(() => {
        const anchor = document.querySelector(
          "[data-testid='ov-case-link-badcase-synthetic-0001']",
        );
        if (!anchor) return null;
        return { href: anchor.getAttribute("href") };
      })()`,
      "seeded overview case link",
    );
    assert.equal(
      link.href,
      "/workspaces/ws-default/sessions/10000000-0000-4000-8000-000000000001/errors?case=badcase-synthetic-0001&tab=desc",
    );

    await page.session.send("Page.navigate", { url: `${baseUrl}${link.href}` });
    const description = await waitForDocument(
      page.session,
      `(() => {
        const descTab = document.querySelector("#desc-tab");
        const detail = document.querySelector("[data-testid='problem-detail']");
        if (!descTab || !detail) return null;
        return {
          selected: descTab.getAttribute("aria-selected"),
          tab: new URLSearchParams(location.search).get("tab"),
          caseId: new URLSearchParams(location.search).get("case"),
          text: detail.textContent.trim(),
        };
      })()`,
      "case description tab from the overview deep link",
    );
    assert.equal(description.selected, "true");
    assert.equal(description.tab, "desc");
    assert.equal(description.caseId, "badcase-synthetic-0001");
    assert.match(description.text, /检查结论缺少目标文件/);
  } finally {
    await page.close();
  }
});

test("m8-04 overview renders an empty workspace and a block-level error state", async () => {
  const page = await createBrowserPage();
  try {
    await installBrowser(page);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${emptyWorkspaceId}/overview`,
    });
    const empty = await waitForDocument(
      page.session,
      `(() => {
        const chart = document.querySelector("[data-testid='ov-chart-empty']");
        const list = document.querySelector("[data-testid='ov-case-empty']");
        const stats = document.querySelector("[data-testid='ov-stat-badcases'] b");
        if (!chart || !list || !stats) return null;
        return {
          chart: chart.textContent,
          list: list.textContent,
          stats: stats.textContent.trim(),
        };
      })()`,
      "empty workspace overview",
    );
    assert.match(empty.chart, /当前条件下没有 bad case/);
    assert.match(empty.list, /这个空间还没有 bad case/);
    assert.equal(empty.stats, "0");

    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await page.session.send("Fetch.enable", {
      patterns: [{ urlPattern: "*overview/summary*", requestStage: "Request" }],
    });
    page.session.on("Fetch.requestPaused", (event) => {
      void page.session.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: 500,
        responseHeaders: [
          { name: "content-type", value: "application/json" },
        ],
        body: Buffer.from(
          JSON.stringify({
            error: {
              code: "INTERNAL",
              message: "simulated overview failure",
              details: {},
            },
          }),
        ).toString("base64"),
      });
    });
    await openOverview(page, "?range=7");
    const failed = await waitForDocument(
      page.session,
      `(() => {
        const text = document.body.innerText;
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (!text.includes("总览统计加载失败")) return null;
        return {
          statstrip: Boolean(document.querySelector("[data-testid='ov-statstrip']")),
          rows: rows.length,
          hasChart: Boolean(document.querySelector("[data-testid='ov-chart']")),
          realCode: text.includes("INTERNAL"),
          pseudoCode: text.includes("OVERVIEW_SUMMARY_UNAVAILABLE"),
        };
      })()`,
      "summary block error with live chart and list",
    );
    assert.equal(failed.statstrip, false);
    assert.equal(failed.rows, 8);
    assert.equal(failed.hasChart, true);
    assert.equal(failed.realCode, true);
    assert.equal(failed.pseudoCode, false);
    await page.session.send("Fetch.disable");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview filters a downgraded week bucket to the whole week", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    const monday = weekStart(day0);
    const sunday = shiftDate(monday, 6);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview?range=custom&from=2026-01-01&to=${day0}&grain=day`,
    });
    await waitForCaseRows(page, 8);

    const chart = await waitForDocument(
      page.session,
      `(() => {
        const hint = document.querySelector("[data-testid='ov-chart-card'] .hint")
          ?.textContent ?? "";
        const badge = document.querySelector("[data-testid='ov-grain-downgraded']")
          ?.textContent?.trim() ?? "";
        const bucket = document.querySelector("[data-bucket='${monday}']");
        if (!bucket || !hint.includes("按周聚合")) return null;
        return { badge, hint };
      })()`,
      "week downgrade chart",
    );
    assert.match(chart.badge, /已按周展示/);

    const expected =
      (day0 >= monday && day0 <= sunday ? 6 : 0) +
      (day1 >= monday && day1 <= sunday ? 5 : 0);
    assert.ok(expected > 0, `${monday}..${sunday} must contain seeded days`);

    // The list is paginated at eight rows, so the week bucket's window total and
    // its first page can differ once both seeded days fall in the same week.
    const visibleRows = Math.min(expected, 8);
    await click(page, `[data-bucket='${monday}']`);
    const filtered = await waitForDocument(
      page.session,
      `(() => {
        const search = new URLSearchParams(location.search);
        if (search.get("lfrom") !== ${JSON.stringify(monday)}) return null;
        if (search.get("lto") !== ${JSON.stringify(sunday)}) return null;
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (rows.length !== ${visibleRows}) return null;
        return {
          rows: rows.length,
          range: search.get("range"),
          grain: search.get("grain"),
          from: search.get("from"),
          to: search.get("to"),
          lfrom: search.get("lfrom"),
          lto: search.get("lto"),
          total: document.querySelector("[data-testid='ov-case-total']")
            ?.textContent ?? "",
        };
      })()`,
      "downgraded week bucket window",
    );
    assert.equal(filtered.range, "custom");
    assert.equal(filtered.grain, "day");
    assert.equal(filtered.from, "2026-01-01");
    assert.equal(filtered.to, day0);
    assert.equal(filtered.lfrom, monday);
    assert.equal(filtered.lto, sunday);
    assert.equal(filtered.rows, visibleRows);
    assert.equal(filtered.total, `共 ${expected} 条`);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview switches workspace with default filters and restores them on back", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    const requests = [];
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      if (request.url.includes("/api/workspaces/")) requests.push(request.url);
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview?range=7&objects=m8-04-alpha&lobject=m8-04-alpha&type=self`,
    });
    await waitForCaseRows(page, 4);
    requests.length = 0;

    await waitForDocument(
      page.session,
      `(() => {
        const picker = document.querySelector("[data-testid='workspace-picker']");
        if (!picker) return null;
        picker.open = true;
        return true;
      })()`,
      "workspace picker",
    );
    await click(page, `[data-testid='workspace-option-${emptyWorkspaceId}']`);
    const switched = await waitForDocument(
      page.session,
      `(() => {
        if (!location.pathname.includes(${JSON.stringify(emptyWorkspaceId)})) return null;
        const search = new URLSearchParams(location.search);
        if (search.get("range") !== "90" || search.get("grain") !== "week") return null;
        if (search.get("objects") || search.get("type") || search.get("page")) return null;
        return { path: location.pathname, search: location.search };
      })()`,
      "workspace switch with default filters",
    );
    assert.equal(
      switched.path,
      `/workspaces/${emptyWorkspaceId}/overview`,
    );

    const foreign = requests.filter((url) =>
      url.includes(`/workspaces/${emptyWorkspaceId}/`),
    );
    const summaryForeign = foreign.filter((url) => !url.includes("/bad-cases"));
    assert.ok(summaryForeign.length > 0, "new workspace must fetch overview data");
    for (const url of summaryForeign) {
      const parsed = new URL(url);
      assert.equal(parsed.searchParams.get("range"), "90");
      assert.equal(parsed.searchParams.has("objects"), false);
      assert.equal(parsed.searchParams.has("badCaseType"), false);
      assert.equal(parsed.searchParams.has("type"), false);
    }
    const caseForeign = foreign.filter((url) => url.includes("/bad-cases"));
    assert.ok(caseForeign.length > 0, "new workspace must fetch its list");
    for (const url of caseForeign) {
      const parsed = new URL(url);
      assert.equal(parsed.searchParams.get("allTime"), "true");
      assert.equal(parsed.searchParams.has("range"), false);
      assert.equal(parsed.searchParams.has("objects"), false);
      assert.equal(parsed.searchParams.has("badCaseType"), false);
    }

    await page.session.send("Runtime.evaluate", {
      expression: "history.back()",
    });
    const restored = await waitForDocument(
      page.session,
      `(() => {
        if (!location.pathname.includes(${JSON.stringify(dataWorkspaceId)})) return null;
        const search = new URLSearchParams(location.search);
        if (search.get("range") !== "7") return null;
        if (search.get("objects") !== "m8-04-alpha") return null;
        if (search.get("lobject") !== "m8-04-alpha") return null;
        if (search.get("type") !== "self") return null;
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (rows.length !== 4) return null;
        return { rows: rows.length, search: location.search };
      })()`,
      "browser back restores previous workspace filters",
    );
    assert.equal(restored.rows, 4);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview clamps an out-of-range page to the last page", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${dataWorkspaceId}/overview?page=99`,
    });
    const clamped = await waitForDocument(
      page.session,
      `(() => {
        const search = new URLSearchParams(location.search);
        if (search.get("page") !== "2") return null;
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (rows.length !== 3) return null;
        const pager = document.querySelector("[data-testid='ov-pager']")
          ?.textContent ?? "";
        if (!pager.includes("第 2 / 2 页")) return null;
        return {
          rows: rows.length,
          page: search.get("page"),
          body: document.body.innerText,
        };
      })()`,
      "clamped overview page",
    );
    assert.equal(clamped.rows, 3);
    assert.equal(clamped.page, "2");
    assert.ok(!clamped.body.includes("这个空间还没有 bad case"));
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview keeps four nav items on one line at 1440px", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await openOverview(page);
    await waitForCaseRows(page, 8);

    const nav = await waitForDocument(
      page.session,
      `(() => {
        const items = [...document.querySelectorAll("nav .tn-item")];
        if (items.length !== 4) return null;
        const measured = items.map((item) => {
          const range = document.createRange();
          range.selectNodeContents(item);
          const rect = range.getBoundingClientRect();
          const style = getComputedStyle(item);
          const sub = item.querySelector(".tn-sub");
          return {
            text: item.textContent.trim(),
            contentHeight: rect.height,
            fontSize: parseFloat(style.fontSize),
            whiteSpace: style.whiteSpace,
            subText: sub?.textContent?.trim() ?? "",
            subDisplay: sub ? getComputedStyle(sub).display : "none",
          };
        });
        return {
          items: measured,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "1440px single-line navigation",
    );
    assert.ok(nav.items[0].text.startsWith("总览"));
    assert.equal(nav.items[0].subText, "bad case 趋势");
    for (const item of nav.items) {
      assert.equal(item.whiteSpace, "nowrap", JSON.stringify(item));
      assert.equal(item.subDisplay, "none", JSON.stringify(item));
      assert.ok(
        item.contentHeight <= item.fontSize * 1.6,
        `nav item wrapped: ${JSON.stringify(item)}`,
      );
    }
    assert.equal(nav.scrollWidth, nav.clientWidth);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview fits 390px without horizontal overflow", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await openOverview(page);
    await waitForCaseRows(page, 8);
    const layout = await waitForDocument(
      page.session,
      `(() => {
        const filterbar = document.querySelector("[data-testid='ov-filterbar']");
        if (!filterbar) return null;
        return {
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          filterHeight: filterbar.getBoundingClientRect().height,
          bodyScrollWidth: document.body.scrollWidth,
        };
      })()`,
      "mobile overview layout",
    );

    assert.equal(layout.scrollWidth, layout.clientWidth);
    assert.equal(layout.bodyScrollWidth, layout.clientWidth);
    assert.ok(layout.filterHeight > 40, String(layout.filterHeight));
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 overview scrollbar sits at the window's right edge", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1500,
      height: 837,
      deviceScaleFactor: 2,
      mobile: false,
    });
    await openOverview(page);
    await waitForCaseRows(page, 8);
    // The scroll container must span the whole workspace main so the classic
    // scrollbar is painted at the window edge instead of the 1180px column.
    const geometry = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='overview-page']");
        const grid = root?.querySelector(".ov-grid");
        const main = document.querySelector("main.workspace-main");
        if (!root || !grid || !main) return null;
        const rect = root.getBoundingClientRect();
        const gridRect = grid.getBoundingClientRect();
        return {
          innerWidth,
          rightEdge: rect.right,
          containerWidth: rect.width,
          cardWidth: gridRect.width,
          scrollHeight: root.scrollHeight,
          clientHeight: root.clientHeight,
          rootScrollWidth: root.scrollWidth,
          rootClientWidth: root.clientWidth,
          documentScrollWidth: document.documentElement.scrollWidth,
          documentClientWidth: document.documentElement.clientWidth,
          bodyScrollWidth: document.body.scrollWidth,
          overflowY: getComputedStyle(root).overflowY,
          mainOverflow: getComputedStyle(main).overflow,
        };
      })()`,
      "overview scroll geometry",
    );

    assert.equal(geometry.overflowY, "auto", JSON.stringify(geometry));
    assert.equal(geometry.mainOverflow, "hidden", JSON.stringify(geometry));
    assert.ok(
      Math.abs(geometry.rightEdge - geometry.innerWidth) <= 1,
      `scroll container right edge ${geometry.rightEdge} must equal window width ${geometry.innerWidth}`,
    );
    assert.ok(
      geometry.scrollHeight > geometry.clientHeight,
      "overview content must overflow so the scrollbar is observable",
    );
    assert.ok(
      geometry.cardWidth > 1000 && geometry.cardWidth <= 1140,
      `card column must stay inside the 1180px content column: ${geometry.cardWidth}`,
    );
    assert.equal(geometry.rootScrollWidth, geometry.rootClientWidth);
    assert.equal(geometry.documentScrollWidth, geometry.documentClientWidth);
    assert.equal(geometry.bodyScrollWidth, geometry.documentClientWidth);

    const scrolled = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='overview-page']");
        root.scrollTop = root.scrollHeight;
        const list = document.querySelector("[data-testid='ov-case-list']");
        return {
          scrollTop: root.scrollTop,
          listVisible: Boolean(list) && list.getBoundingClientRect().top < innerHeight,
        };
      })()`,
      "overview scrolled to the list bottom",
    );
    assert.ok(scrolled.scrollTop > 0, "overview must scroll to the list bottom");
    assert.equal(scrolled.listVisible, true, "the list must be reachable by scrolling");

    for (const [width, height] of [
      [1024, 900],
      [640, 900],
    ]) {
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile: width <= 640,
      });
      const responsive = await waitForDocument(
        page.session,
        `(() => {
          const root = document.querySelector("[data-testid='overview-page']");
          if (!root) return null;
          const rect = root.getBoundingClientRect();
          if (Math.abs(rect.right - innerWidth) > 1) return null;
          return {
            rightEdge: rect.right,
            innerWidth,
            documentScrollWidth: document.documentElement.scrollWidth,
            documentClientWidth: document.documentElement.clientWidth,
          };
        })()`,
        `${width}px overview right edge`,
      );
      assert.equal(responsive.documentScrollWidth, responsive.documentClientWidth);
    }
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-04 defaults quick ranges to day for 7 days and week for 30/90", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await openOverview(page);

    await click(page, "[data-testid='ov-range-7']");
    const seven = await waitForDocument(
      page.session,
      `(() => {
        const search = new URLSearchParams(location.search);
        if (search.get("range") !== "7" || search.get("grain") !== "day") return null;
        const hint = document.querySelector("[data-testid='ov-chart-card'] .hint")
          ?.textContent ?? "";
        const buckets = document.querySelectorAll("[data-bucket]");
        if (!hint.includes("按日聚合") || buckets.length !== 7) return null;
        const day0Bucket = document.querySelector("[data-bucket='${day0}']");
        if (!day0Bucket) return null;
        const label = day0Bucket.getAttribute("aria-label") ?? "";
        const counts = label.match(/自身存在问题 (\\d+)，发现前置步骤问题 (\\d+)/);
        const day0Total = counts ? Number(counts[1]) + Number(counts[2]) : null;
        if (day0Total !== 6) return null;
        return { day0Total };
      })()`,
      "7-day range defaults to day grain with the current-day count",
    );
    assert.equal(seven.day0Total, 6);

    await click(page, "[data-testid='ov-range-30']");
    const thirty = await waitForDocument(
      page.session,
      `(() => {
        const search = new URLSearchParams(location.search);
        if (search.get("range") !== "30" || search.get("grain") !== "week") return null;
        const hint = document.querySelector("[data-testid='ov-chart-card'] .hint")
          ?.textContent ?? "";
        return hint.includes("按周聚合") ? { grain: search.get("grain") } : null;
      })()`,
      "30-day range keeps week grain",
    );
    assert.equal(thirty.grain, "week");

    await click(page, "[data-testid='ov-range-90']");
    const ninety = await waitForDocument(
      page.session,
      `(() => {
        const search = new URLSearchParams(location.search);
        if (search.get("range") !== "90" || search.get("grain") !== "week") return null;
        const hint = document.querySelector("[data-testid='ov-chart-card'] .hint")
          ?.textContent ?? "";
        return hint.includes("按周聚合") ? { grain: search.get("grain") } : null;
      })()`,
      "90-day range keeps week grain",
    );
    assert.equal(ninety.grain, "week");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

/**
 * Create a workspace with three synthetic bad-case pages for the paging scroll
 * regression. The shared `dataWorkspaceId` keeps its eleven cases for the other
 * tests in this file, so this scenario needs its own space.
 * @returns {Promise<string>} Created workspace id.
 */
async function seedPagingWorkspace() {
  const created = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M8-04 三页翻页",
      mark: "M8PG",
      quota: 80,
      spaceAdminIds: [adminId],
    }),
  });
  const credential = await apiJson(
    `/api/workspaces/${created.id}/credentials`,
    adminToken,
    { method: "POST" },
  );
  const day = shanghaiDate(0);
  for (let index = 0; index < 20; index += 1) {
    const suffix = String(index + 1).padStart(2, "0");
    const response = await fetch(
      `${baseUrl}/api/workspaces/${created.id}/bad-cases`,
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${credential.credential}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          badCaseId: `M8-04-PAGE-${suffix}`,
          sessionId: "10000000-0000-4000-8000-000000000001",
          badCaseType: index % 2 === 0 ? "self" : "discovery",
          objectName: index % 2 === 0 ? "m8-04-alpha" : "m8-04-beta",
          objectType: "agent",
          objectVersion: "v1",
          title: `M8-04 翻页案例 ${suffix}`,
          reason: `m8-04 paging e2e case ${suffix}`,
          source: "e2e",
          createdAt: `${day}T09:${suffix}:00+08:00`,
        }),
      },
    );
    assert.equal(response.status, 201, await response.text());
  }
  return created.id;
}

/**
 * Read the list scroll position and the loading markers from the live page.
 * @param {object} page Browser page from createBrowserPage.
 * @returns {Promise<object>} Snapshot of scroll geometry and list state.
 */
async function pagingSnapshot(page) {
  const result = await page.session.send("Runtime.evaluate", {
    expression: `(() => {
      const root = document.querySelector("[data-testid='overview-page']");
      const list = document.querySelector("[data-testid='ov-case-list']");
      const pager = document.querySelector("[data-testid='ov-pager']");
      if (!root || !list) return null;
      return {
        scrollTop: Math.round(root.scrollTop),
        maxScroll: Math.round(root.scrollHeight - root.clientHeight),
        rows: document.querySelectorAll("[data-testid='ov-case-row']").length,
        skeleton: Boolean(document.querySelector("[data-testid='ov-case-loading']")),
        loading: Boolean(document.querySelector("[data-testid='ov-case-loading-hint']")),
        busy: list.getAttribute("aria-busy"),
        pager: pager?.textContent?.replace(/\\s+/g, " ").trim() ?? "",
        marker: window.__m804PagingMarker ?? null,
        search: location.search,
      };
    })()`,
    returnByValue: true,
  });
  return result.result.value;
}

test("m8-04 overview paging keeps the list position on uncached and cached pages", async () => {
  const pagingWorkspaceId = await seedPagingWorkspace();
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await installBrowser(page);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1500,
      height: 837,
      deviceScaleFactor: 1,
      mobile: false,
    });

    // Pause the list endpoint so the loading state is observable. A queued
    // request can be delayed once, and the retry path can be failed once.
    let delayNextList = 0;
    let failListAttempts = 0;
    await page.session.send("Fetch.enable", {
      patterns: [{ urlPattern: "*bad-cases*", requestStage: "Request" }],
    });
    page.session.on("Fetch.requestPaused", async ({ requestId, request }) => {
      const url = new URL(request.url);
      if (request.method !== "GET" || !url.pathname.endsWith("/bad-cases")) {
        await page.session
          .send("Fetch.continueRequest", { requestId })
          .catch(() => {});
        return;
      }
      if (failListAttempts > 0) {
        failListAttempts -= 1;
        await page.session
          .send("Fetch.fulfillRequest", {
            requestId,
            responseCode: 500,
            responseHeaders: [
              { name: "content-type", value: "application/json" },
            ],
            body: Buffer.from(
              JSON.stringify({
                error: {
                  code: "INTERNAL",
                  message: "injected overview list failure",
                  details: {},
                },
              }),
            ).toString("base64"),
          })
          .catch(() => {});
        return;
      }
      const delay = delayNextList;
      delayNextList = 0;
      if (delay > 0) {
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
      await page.session
        .send("Fetch.continueRequest", { requestId })
        .catch(() => {});
    });

    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${pagingWorkspaceId}/overview`,
    });
    await waitForCaseRows(page, 8);

    // Park the list at the bottom, as the reporting person did, and remember a
    // marker that only survives if the document is never reloaded.
    const baseline = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='overview-page']");
        if (!root) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 8) return null;
        root.scrollTop = root.scrollHeight;
        window.__m804PagingMarker = "kept";
        return {
          scrollTop: Math.round(root.scrollTop),
          maxScroll: Math.round(root.scrollHeight - root.clientHeight),
        };
      })()`,
      "paging baseline at the list bottom",
    );
    assert.ok(baseline.scrollTop > 0, "baseline must sit below the page top");
    assert.equal(baseline.scrollTop, baseline.maxScroll);

    // First request for page 2: the previous rows and the pager must stay on
    // screen while the delayed request is in flight.
    delayNextList = 900;
    await click(page, "[data-testid='ov-page-next']");
    const during = await waitForDocument(
      page.session,
      `(() => {
        const list = document.querySelector("[data-testid='ov-case-list']");
        const pager = document.querySelector("[data-testid='ov-pager']");
        const root = document.querySelector("[data-testid='overview-page']");
        if (!list || !pager || !root) return null;
        if (list.getAttribute("aria-busy") !== "true") return null;
        if (!document.querySelector("[data-testid='ov-case-loading-hint']")) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 8) return null;
        const pagerText = pager.textContent.replace(/\\s+/g, " ").trim();
        if (!pagerText.includes("第 2 / 3 页")) return null;
        return {
          scrollTop: Math.round(root.scrollTop),
          marker: window.__m804PagingMarker ?? null,
        };
      })()`,
      "page 2 loading keeps rows, pager and scroll position",
    );
    assert.equal(during.scrollTop, baseline.scrollTop);
    assert.equal(during.marker, "kept");

    const pageTwo = await waitForDocument(
      page.session,
      `(() => {
        const list = document.querySelector("[data-testid='ov-case-list']");
        const root = document.querySelector("[data-testid='overview-page']");
        const pager = document.querySelector("[data-testid='ov-pager']");
        if (!list || !root || !pager) return null;
        if (list.getAttribute("aria-busy") === "true") return null;
        const pagerText = pager.textContent.replace(/\\s+/g, " ").trim();
        if (!pagerText.includes("第 2 / 3 页")) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 8) return null;
        if (new URLSearchParams(location.search).get("page") !== "2") return null;
        return { scrollTop: Math.round(root.scrollTop), marker: window.__m804PagingMarker ?? null };
      })()`,
      "page 2 loaded in place",
    );
    assert.equal(pageTwo.scrollTop, baseline.scrollTop);
    assert.equal(pageTwo.marker, "kept");

    // Cache-hit path: returning to page 1 and paging forward again must also
    // keep the position, with no skeleton and no document reload.
    await click(page, "[data-testid='ov-page-prev']");
    await waitForDocument(
      page.session,
      `(() => {
        const pager = document.querySelector("[data-testid='ov-pager']");
        if (!pager || !pager.textContent.includes("第 1 / 3 页")) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 8) return null;
        return true;
      })()`,
      "cached page 1 restored",
    );
    const cachedOne = await pagingSnapshot(page);
    assert.equal(cachedOne.scrollTop, baseline.scrollTop);
    assert.equal(cachedOne.marker, "kept");

    await click(page, "[data-testid='ov-page-next']");
    const cachedTwo = await waitForDocument(
      page.session,
      `(() => {
        const pager = document.querySelector("[data-testid='ov-pager']");
        const list = document.querySelector("[data-testid='ov-case-list']");
        const root = document.querySelector("[data-testid='overview-page']");
        if (!pager || !list || !root) return null;
        if (!pager.textContent.includes("第 2 / 3 页")) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 8) return null;
        return {
          scrollTop: Math.round(root.scrollTop),
          skeleton: Boolean(document.querySelector("[data-testid='ov-case-loading']")),
          marker: window.__m804PagingMarker ?? null,
        };
      })()`,
      "cached page 2 restored",
    );
    assert.equal(cachedTwo.skeleton, false);
    assert.equal(cachedTwo.scrollTop, baseline.scrollTop);
    assert.equal(cachedTwo.marker, "kept");

    // Failure retry: page 3 is still uncached, so inject one 500 and recover
    // through the block-level retry.
    // The query client retries 5xx twice, so fail every attempt before the
    // explicit block-level retry.
    failListAttempts = 3;
    await click(page, "[data-testid='ov-page-next']");
    const failed = await waitForDocument(
      page.session,
      `(() => {
        const error = document.querySelector("[data-testid='ov-case-error']");
        if (!error) return null;
        return { text: error.textContent?.trim() ?? "" };
      })()`,
      "page 3 list error",
    );
    assert.ok(failed.text.includes("INTERNAL"));
    await click(page, "[data-testid='ov-case-error'] button");

    const lastPage = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='overview-page']");
        const pager = document.querySelector("[data-testid='ov-pager']");
        if (!root || !pager) return null;
        if (!pager.textContent.includes("第 3 / 3 页")) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 4) return null;
        if (new URLSearchParams(location.search).get("page") !== "3") return null;
        return {
          scrollTop: Math.round(root.scrollTop),
          marker: window.__m804PagingMarker ?? null,
        };
      })()`,
      "short last page recovered after retry",
    );
    assert.ok(lastPage.scrollTop > 0, "the short last page must not jump to the top");
    assert.equal(lastPage.marker, "kept");

    // Rapid paging: delay page 2, immediately ask for page 3, and confirm the
    // late page-2 response cannot replace the page-3 rows.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${pagingWorkspaceId}/overview`,
    });
    await waitForCaseRows(page, 8);
    await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='overview-page']");
        if (!root) return null;
        root.scrollTop = root.scrollHeight;
        window.__m804PagingMarker = "kept";
        return true;
      })()`,
      "rapid paging baseline",
    );
    delayNextList = 900;
    await click(page, "[data-testid='ov-page-next']");
    await waitForSearchParam(page, "page", "2");
    await click(page, "[data-testid='ov-page-next']");
    const rapid = await waitForDocument(
      page.session,
      `(() => {
        const pager = document.querySelector("[data-testid='ov-pager']");
        const root = document.querySelector("[data-testid='overview-page']");
        if (!pager || !root) return null;
        if (!pager.textContent.includes("第 3 / 3 页")) return null;
        if (document.querySelectorAll("[data-testid='ov-case-row']").length !== 4) return null;
        return {
          scrollTop: Math.round(root.scrollTop),
          marker: window.__m804PagingMarker ?? null,
        };
      })()`,
      "rapid paging settles on page 3",
    );
    assert.ok(rapid.scrollTop > 0);
    assert.equal(rapid.marker, "kept");
    // Wait past the delayed page-2 response: it must stay in its own cache key.
    await new Promise((resolve) => setTimeout(resolve, 1200));
    const settled = await pagingSnapshot(page);
    assert.equal(settled.rows, 4);
    assert.equal(new URLSearchParams(settled.search).get("page"), "3");
    assert.equal(settled.marker, "kept");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
