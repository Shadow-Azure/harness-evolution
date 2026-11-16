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
const secret = "m8-05-session-latest-ten-signing-secret-with-sufficient-length";
const initialPassword = "m8-05-session-latest-ten-initial-password";
const replacementPassword = "m8-05-session-latest-ten-replacement-password";
const dataWorkspace = "ws-default";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminCookie = "";
let adminToken = "";
let otherWorkspaceId = "";
const otherRootId = "10000000-0000-4000-8000-000000000905";
const otherTitle = "其他空间待同步会话";

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

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource")
  );
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

async function login() {
  const first = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
  });
  const firstText = await first.text();
  assert.equal(first.status, 200, firstText);
  const firstBody = JSON.parse(firstText);
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${firstBody.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: initialPassword,
      newPassword: replacementPassword,
    }),
  });
  assert.equal(changed.status, 204);

  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: replacementPassword }),
  });
  const loginText = await login.text();
  assert.equal(login.status, 200, loginText);
  adminCookie = login.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1] ?? "";
  assert.ok(adminCookie, "login must set a refresh cookie");
  adminToken = JSON.parse(loginText).accessToken;
}

async function currentCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: replacementPassword }),
  });
  assert.equal(response.status, 200, await response.text());
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "login must set a refresh cookie");
  return cookie;
}

async function installBrowser(page) {
  const cookie = await currentCookie();
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

async function openSessionList(page, workspaceId = dataWorkspace) {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${workspaceId}/sessions`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const count = document.querySelector("[data-testid='session-browser-count']");
      const list = document.querySelector(".session-list");
      if (!count || !list || count.textContent.trim() === "加载中…") return null;
      const cards = document.querySelectorAll("[data-testid='session-card']").length;
      const empty = document.querySelector("[data-testid='session-list-empty']");
      if (cards === 0 && !empty) return null;
      return {
        path: location.pathname,
        search: location.search,
        count: count.textContent.trim(),
        cards,
      };
    })()`,
    "session list",
  );
}

async function setSearchValue(page, value) {
  await page.session.send("Runtime.evaluate", {
    expression: `(() => {
      const input = document.querySelector("[data-testid='search-input']");
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(input, ${JSON.stringify(value)});
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
      return input.value;
    })()`,
  });
}

async function pressEnter(page) {
  await page.session.send("Input.dispatchKeyEvent", {
    type: "rawKeyDown",
    key: "Enter",
    code: "Enter",
    windowsVirtualKeyCode: 13,
  });
  await page.session.send("Input.dispatchKeyEvent", {
    type: "char",
    key: "Enter",
    code: "Enter",
    text: "\r",
    unmodifiedText: "\r",
    windowsVirtualKeyCode: 13,
  });
  await page.session.send("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Enter",
    code: "Enter",
    windowsVirtualKeyCode: 13,
  });
}

async function click(page, selector) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      return true;
    })()`,
    `click ${selector}`,
  );
}

async function seedOtherWorkspace() {
  const session = await apiJson("/api/auth/session", adminToken);
  const created = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M8-05 其他空间",
      mark: "M805",
      quota: 10,
      spaceAdminIds: [session.user.id],
    }),
  });
  otherWorkspaceId = created.id;
  const credential = await apiJson(
    `/api/workspaces/${otherWorkspaceId}/credentials`,
    adminToken,
    { method: "POST" },
  );
  const response = await fetch(
    `${baseUrl}/api/workspaces/${otherWorkspaceId}/bad-cases`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${credential.credential}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        badCaseId: "M8-05-OTHER-01",
        sessionId: otherRootId,
        badCaseType: "self",
        objectName: "m8-05-other",
        objectType: "agent",
        objectVersion: "v1",
        title: otherTitle,
        reason: "m8-05 cross-workspace pending root",
        source: "e2e",
        createdAt: new Date().toISOString(),
      }),
    },
  );
  assert.equal(response.status, 201, await response.text());
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m8-05-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
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
      HE_LOGIN_RATE_LIMIT: "100",
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

  await login();
  await seedOtherWorkspace();
});

after(cleanupRuntime);

test("m8-05 session-latest-ten submits a root ID on Enter and restores the list", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installBrowser(page);
    const requests = [];
    page.session.on("Network.requestWillBeSent", (params) => {
      const url = new URL(params.request.url);
      if (url.pathname === `/api/workspaces/${dataWorkspace}/sessions`) {
        requests.push(url);
      }
    });

    const initial = await openSessionList(page);
    assert.equal(initial.cards, 4, JSON.stringify(initial));
    assert.equal(initial.count, "最新 4 / 总数 4", JSON.stringify(initial));
    assert.equal(initial.search, "");

    const details = await waitForDocument(
      page.session,
      `(() => {
        const input = document.querySelector("[data-testid='search-input']");
        const hint = document.querySelector(".search-hint");
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        if (!input || !hint || cards.length !== 4) return null;
        const ids = cards.map((card) => card.dataset.sessionId);
        const selected = cards.find((card) => card.dataset.selected === "true")?.dataset.sessionId;
        return {
          placeholder: input.getAttribute("placeholder"),
          hint: hint.textContent.trim(),
          ids,
          selected,
          path: location.pathname,
        };
      })()`,
      "session controls",
    );
    assert.equal(details.placeholder, "输入 root session ID，回车查询");
    assert.equal(details.hint, "Enter 精确查询 · 清空后回车恢复最新 10 个");
    assert.equal(details.selected, details.ids[0]);
    assert.equal(details.path, `/workspaces/${dataWorkspace}/sessions/${details.ids[0]}`);
    assert.equal(requests.at(-1)?.searchParams.get("limit"), "10");

    requests.length = 0;
    const targetId = details.ids.at(-1);
    assert.ok(targetId);
    await setSearchValue(page, targetId);
    await new Promise((resolve) => setTimeout(resolve, 350));
    assert.equal(requests.length, 0, "typing must not request the session list");

    await pressEnter(page);
    const hit = await waitForDocument(
      page.session,
      `(() => {
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        const selected = cards.find((card) => card.dataset.selected === "true");
        const count = document.querySelector("[data-testid='session-browser-count']")?.textContent.trim();
        if (cards.length !== 1 || selected?.dataset.sessionId !== ${JSON.stringify(targetId)} || count === "加载中…") return null;
        return {
          path: location.pathname,
          search: location.search,
          count,
        };
      })()`,
      "exact root ID hit",
    );
    assert.equal(hit.path, `/workspaces/${dataWorkspace}/sessions/${targetId}`);
    assert.equal(new URLSearchParams(hit.search).get("q"), targetId);
    assert.equal(hit.count, "命中 1 个");
    assert.equal(requests.length, 1);
    assert.equal(requests[0]?.searchParams.get("q"), targetId);
    assert.equal(requests[0]?.searchParams.get("limit"), "10");

    requests.length = 0;
    await setSearchValue(page, "");
    await pressEnter(page);
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        const selected = cards.find((card) => card.dataset.selected === "true");
        const count = document.querySelector("[data-testid='session-browser-count']")?.textContent.trim();
        if (cards.length !== 4 || selected?.dataset.sessionId !== ${JSON.stringify(details.ids[0])}) return null;
        return {
          path: location.pathname,
          search: location.search,
          count,
        };
      })()`,
      "latest ten restored",
    );
    assert.equal(restored.path, `/workspaces/${dataWorkspace}/sessions/${details.ids[0]}`);
    assert.equal(restored.search, "");
    assert.equal(restored.count, "最新 4 / 总数 4");
    assert.equal(requests.length, 1);
    assert.equal(requests[0]?.searchParams.get("q"), null);
    assert.equal(requests[0]?.searchParams.get("limit"), "10");

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m8-05 session-latest-ten isolates workspaces and shows pending sessions", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installBrowser(page);
    const first = await openSessionList(page);
    assert.equal(first.cards, 4, JSON.stringify(first));

    await setSearchValue(page, otherRootId);
    await pressEnter(page);
    const miss = await waitForDocument(
      page.session,
      `(() => {
        const count = document.querySelector("[data-testid='session-browser-count']");
        const empty = document.querySelector("[data-testid='session-overview-empty']");
        if (!count || !empty || count.textContent.trim() === "加载中…") return null;
        return {
          path: location.pathname,
          search: location.search,
          count: count.textContent.trim(),
          overview: empty.textContent.trim(),
          cards: document.querySelectorAll("[data-testid='session-card']").length,
        };
      })()`,
      "cross-workspace query miss",
    );
    assert.equal(miss.path, `/workspaces/${dataWorkspace}/sessions`);
    assert.equal(new URLSearchParams(miss.search).get("q"), otherRootId);
    assert.equal(miss.count, "命中 0 个");
    assert.equal(miss.cards, 0);
    assert.match(miss.overview, /未找到该 Session/);

    const other = await openSessionList(page, otherWorkspaceId);
    assert.equal(other.cards, 0, JSON.stringify(other));
    assert.equal(other.path, `/workspaces/${otherWorkspaceId}/sessions`);
    const pending = await waitForDocument(
      page.session,
      `(() => {
        const badge = document.querySelector("[data-testid='session-pending-badge']");
        const empty = document.querySelector("[data-testid='session-list-empty']");
        const count = document.querySelector("[data-testid='session-browser-count']");
        if (!badge || !empty || !count || count.textContent.trim() === "加载中…") return null;
        return {
          badge: badge.textContent.trim(),
          empty: empty.textContent.trim(),
          count: count.textContent.trim(),
          cards: document.querySelectorAll("[data-testid='session-card']").length,
        };
      })()`,
      "pending workspace state",
    );
    assert.equal(pending.badge, "1 个待同步");
    assert.equal(pending.count, "最新 0 / 总数 0");
    assert.equal(pending.cards, 0);
    assert.match(pending.empty, /暂无可展示的 Session/);
    assert.match(pending.empty, /1 个待同步/);

    await click(page, "[data-testid='session-pending-badge']");
    const explained = await waitForDocument(
      page.session,
      `(() => {
        const badge = document.querySelector("[data-testid='session-pending-badge']");
        const hint = document.querySelector("[data-testid='session-pending-hint']");
        if (!badge || !hint || badge.getAttribute("aria-expanded") !== "true") return null;
        return hint.textContent.trim();
      })()`,
      "pending explanation",
    );
    assert.match(explained, /轨迹尚未归一化/);

    await setSearchValue(page, "10000000-0000-4000-8000-000000000001");
    await pressEnter(page);
    const otherMiss = await waitForDocument(
      page.session,
      `(() => {
        const count = document.querySelector("[data-testid='session-browser-count']");
        if (!count || count.textContent.trim() !== "命中 0 个") return null;
        return {
          path: location.pathname,
          empty: document.querySelector("[data-testid='session-list-empty']")?.textContent.trim() ?? "",
        };
      })()`,
      "other workspace miss",
    );
    assert.equal(otherMiss.path, `/workspaces/${otherWorkspaceId}/sessions`);
    assert.match(otherMiss.empty, /未找到匹配/);

    await click(page, ".empty-action");
    const reset = await waitForDocument(
      page.session,
      `(() => {
        const badge = document.querySelector("[data-testid='session-pending-badge']");
        const count = document.querySelector("[data-testid='session-browser-count']");
        if (!badge || !count || count.textContent.trim() === "加载中…") return null;
        return {
          path: location.pathname,
          search: location.search,
          count: count.textContent.trim(),
          badge: badge.textContent.trim(),
        };
      })()`,
      "reset to latest ten",
    );
    assert.equal(reset.path, `/workspaces/${otherWorkspaceId}/sessions`);
    assert.equal(reset.search, "");
    assert.equal(reset.count, "最新 0 / 总数 0");
    assert.equal(reset.badge, "1 个待同步");

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
