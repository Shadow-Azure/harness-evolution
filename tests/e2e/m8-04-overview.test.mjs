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
          sessionId:
            item.object === "m8-04-alpha"
              ? "m8-04-session-alpha"
              : "m8-04-session-beta",
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
        "上报来源",
        "空间额度",
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

test("m8-04 overview filters round-trip through the URL and reload", async () => {
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

    await click(page, "[data-testid='ov-range-7']");
    await waitForSearchParam(page, "range", "7");
    await click(page, "[data-testid='ov-grain-day']");
    await waitForSearchParam(page, "grain", "day");
    await chooseSource(page, "m8-04-alpha");
    state = await waitForCaseRows(page, 6);
    assert.equal(new URLSearchParams(state.search).get("range"), "7");
    assert.equal(new URLSearchParams(state.search).get("grain"), "day");
    assert.equal(new URLSearchParams(state.search).get("objects"), "m8-04-alpha");
    assert.equal(new URLSearchParams(state.search).get("page"), null);
    assert.ok(
      (await waitForDocument(
        page.session,
        `Boolean(document.querySelector("[data-testid='ov-chip-m8-04-alpha']"))`,
        "alpha chip",
      )),
    );

    await chooseSource(page, "m8-04-beta");
    state = await waitForCaseRows(page, 8);
    assert.equal(
      new URLSearchParams(state.search).get("objects"),
      "m8-04-alpha,m8-04-beta",
    );
    assert.equal(state.total, "共 11 条");

    await page.session.send("Page.reload");
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        const chips = document.querySelectorAll("[data-testid^='ov-chip-']");
        const stats = document.querySelector("[data-testid='ov-stat-badcases'] b")
          ?.textContent?.trim() ?? "";
        if (rows.length !== 8 || chips.length !== 2) return null;
        const search = new URLSearchParams(location.search);
        return {
          rows: rows.length,
          chips: chips.length,
          range: search.get("range"),
          grain: search.get("grain"),
          objects: search.get("objects"),
          stats,
        };
      })()`,
      "filters restored after reload",
    );
    assert.equal(restored.range, "7");
    assert.equal(restored.grain, "day");
    assert.equal(restored.objects, "m8-04-alpha,m8-04-beta");
    assert.equal(restored.stats, "11");

    await click(page, "[data-testid='ov-chip-m8-04-alpha'] button");
    state = await waitForCaseRows(page, 5);
    assert.equal(new URLSearchParams(state.search).get("objects"), "m8-04-beta");
    assert.equal(state.total, "共 5 条");

    await click(page, "[data-testid='ov-clear']");
    await waitForSearchParam(page, "range", "90");
    const cleared = await waitForDocument(
      page.session,
      `(() => {
        const rows = document.querySelectorAll("[data-testid='ov-case-row']");
        if (rows.length !== 8) return null;
        const search = new URLSearchParams(location.search);
        return {
          objects: search.get("objects"),
          range: search.get("range"),
          grain: search.get("grain"),
          total: document.querySelector("[data-testid='ov-case-total']")
            ?.textContent ?? "",
        };
      })()`,
      "cleared overview filters",
    );
    assert.equal(cleared.objects, null);
    assert.equal(cleared.range, "90");
    assert.equal(cleared.grain, "week");
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
    assert.equal(search.get("from"), day1);
    assert.equal(search.get("to"), day1);
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
      `/workspaces/${dataWorkspaceId}/sessions/m8-04-session-beta/errors?case=M8-04-CASE-09&tab=desc`,
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
      url: `${baseUrl}/workspaces/ws-default/overview?range=custom&from=2026-10-01&to=2026-10-31`,
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
        };
      })()`,
      "summary block error with live chart and list",
    );
    assert.equal(failed.statstrip, false);
    assert.equal(failed.rows, 8);
    assert.equal(failed.hasChart, true);
    await page.session.send("Fetch.disable");
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
