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
const secret = "m7-08-workspace-shell-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let currentAdminPassword = "m7-08-workspace-shell-initial-password";
let passwordRevision = 0;

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

async function loginAccessToken() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: currentAdminPassword,
    }),
  });
  assert.equal(response.status, 200);
  return await response.json();
}

async function loginCookie() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: currentAdminPassword,
    }),
  });
  assert.equal(login.status, 200);
  const body = await login.json();
  passwordRevision += 1;
  const replacement = `m7-08-workspace-shell-replacement-password-${passwordRevision}`;
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${body.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: currentAdminPassword,
      newPassword: replacement,
    }),
  });
  assert.equal(changed.status, 204);
  currentAdminPassword = replacement;
  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: `refresh_token=${
        login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1]
      }`,
    },
  });
  assert.equal(refreshed.status, 200);
  return refreshed.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
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

async function installBrowser(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
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

async function openPickerAndSwitch(page, workspaceId) {
  await waitForDocument(
    page.session,
    `(() => {
      const picker = document.querySelector("[data-testid='workspace-picker']");
      if (!picker) return null;
      picker.open = true;
      const option = document.querySelector(
        "[data-testid='workspace-option-${workspaceId}']",
      );
      if (!option) return null;
      option.click();
      return true;
    })()`,
    `workspace option ${workspaceId}`,
  );
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m7-08-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: "m7-08-workspace-shell-initial-password",
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
});

after(cleanupRuntime);

test("m7-08 workspace-shell requires login before a workspace route", async () => {
  const page = await createBrowserPage();
  try {
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/ws-default/sessions`,
    });
    const state = await waitForDocument(
      page.session,
      `(() => {
        if (location.pathname !== "/login") return null;
        return {
          path: location.pathname,
          redirect: new URLSearchParams(location.search).get("redirect"),
          hasForm: Boolean(document.querySelector('input[name="username"]')),
        };
      })()`,
      "login redirect for an anonymous workspace route",
    );

    assert.equal(state.path, "/login");
    assert.equal(state.redirect, "/workspaces/ws-default/sessions");
    assert.equal(state.hasForm, true);
  } finally {
    await page.close();
  }
});

test("m7-08 workspace-shell switches spaces and never reuses the old cache", async () => {
  const chat = await loginCookie();
  const login = await loginAccessToken();
  const accessToken = login.accessToken;
  const session = await apiJson("/api/auth/session", accessToken);
  assert.ok(session.workspaces.some((workspace) => workspace.id === "ws-default"));
  const adminId = session.user.id;
  const extraWorkspace = await apiJson("/api/workspaces", accessToken, {
    method: "POST",
    body: JSON.stringify({
      name: "E2E 空空间",
      mark: "E2E",
      quota: 10,
      spaceAdminIds: [adminId],
    }),
  });

  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.text.includes("Download the Vue Devtools extension") ||
        entry.text.includes("Failed to load resource"),
    });
    await installBrowser(page, chat);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/ws-default/sessions`,
    });
    const initial = await waitForDocument(
      page.session,
      `(() => {
        const cards = document.querySelectorAll("[data-testid='session-card']");
        const picker = document.querySelector("[data-testid='workspace-picker']");
        if (cards.length === 0 || !picker) return null;
        return {
          path: location.pathname,
          cards: cards.length,
          picker: picker.textContent,
        };
      })()`,
      "default workspace session cards",
    );
    assert.ok(
      initial.path.startsWith("/workspaces/ws-default/sessions"),
      initial.path,
    );
    assert.match(initial.picker, /默认空间/);

    await openPickerAndSwitch(page, extraWorkspace.id);
    await waitForDocument(
      page.session,
      `location.pathname === "/workspaces/${extraWorkspace.id}/sessions" &&
        document.body.innerText.includes("该工作空间还没有上报 bad case")`,
      "empty workspace session list",
    );
    const emptyState = await waitForDocument(
      page.session,
      `(() => {
        const cards = document.querySelectorAll("[data-testid='session-card']");
        if (cards.length !== 0) return null;
        return { path: location.pathname, text: document.body.innerText };
      })()`,
      "no stale session cards after switching",
    );
    assert.equal(emptyState.path, `/workspaces/${extraWorkspace.id}/sessions`);
    assert.ok(!emptyState.text.includes("示例会话四"));

    await openPickerAndSwitch(page, "ws-default");
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const cards = document.querySelectorAll("[data-testid='session-card']");
        if (!location.pathname.startsWith("/workspaces/ws-default/")) return null;
        if (cards.length === 0) return null;
        return { path: location.pathname, cards: cards.length };
      })()`,
      "default workspace session cards after switching back",
    );
    assert.ok(
      restored.path.startsWith("/workspaces/ws-default/sessions"),
      restored.path,
    );
    assert.equal(restored.cards, initial.cards);

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m7-08 workspace-shell redirects a legacy deep link exactly once", async () => {
  const cookie = await loginCookie();
  const login = await loginAccessToken();
  const sessions = await apiJson(
    "/api/workspaces/ws-default/sessions",
    login.accessToken,
  );
  const sessionId = sessions.items[0]?.id;
  assert.ok(sessionId, "expected one seeded session");

  const page = await createBrowserPage();
  try {
    await installBrowser(page, cookie);
    await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `try {
        localStorage.setItem("harness.lastWorkspaceId", "ws-default");
      } catch {}`,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/sessions/${encodeURIComponent(sessionId)}/errors`,
    });
    const redirected = await waitForDocument(
      page.session,
      `(() => {
        const expected = "/workspaces/ws-default/sessions/${encodeURIComponent(sessionId)}/errors";
        if (location.pathname !== expected) return null;
        return {
          path: location.pathname,
          replaced: history.state?.replaced,
          position: history.state?.position,
        };
      })()`,
      "legacy deep link workspace redirect",
    );

    assert.equal(
      redirected.path,
      `/workspaces/ws-default/sessions/${encodeURIComponent(sessionId)}/errors`,
    );
    // The browser's about:blank is position 0; the app entry is 1. A push
    // redirect (instead of replace) would add a second app entry.
    assert.equal(redirected.replaced, true);
    assert.ok(redirected.position <= 1, String(redirected.position));

    await new Promise((resolve) => setTimeout(resolve, 500));
    const stable = await page.session.send("Runtime.evaluate", {
      expression: `location.pathname`,
      returnByValue: true,
    });
    assert.equal(
      stable.result.value,
      `/workspaces/ws-default/sessions/${encodeURIComponent(sessionId)}/errors`,
    );
  } finally {
    await page.close();
  }
});

test("m7-08 workspace-shell routes an invisible workspace to the chooser", async () => {
  const cookie = await loginCookie();
  const page = await createBrowserPage();
  try {
    await installBrowser(page, cookie);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/not-a-visible-workspace/sessions`,
    });
    const chooser = await waitForDocument(
      page.session,
      `(() => {
        if (location.pathname !== "/workspaces") return null;
        const cards = document.querySelectorAll(
          "[data-testid^='workspace-card-']",
        ).length;
        if (cards < 1) return null;
        return {
          path: location.pathname,
          reason: new URLSearchParams(location.search).get("reason"),
          cards,
          text: document.body.innerText,
        };
      })()`,
      "workspace chooser for an invisible workspace",
    );

    assert.equal(chooser.path, "/workspaces");
    assert.equal(chooser.reason, "forbidden");
    assert.ok(chooser.cards >= 1);
    assert.match(chooser.text, /没有该空间的访问权限/);
  } finally {
    await page.close();
  }
});
