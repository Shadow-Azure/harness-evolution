import assert from "node:assert/strict";
import { spawn } from "node:child_process";
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
let api;
let web;
let apiLogs = "";
let webLogs = "";
let dataDir;
let baseUrl;
let currentAdminPassword = "m1-shell-initial-password";
let passwordRevision = 0;

async function browserRefreshCookie() {
  const password = currentAdminPassword;
  passwordRevision += 1;
  const replacement = `m1-shell-replacement-password-${passwordRevision}`;
  let response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password }),
  });
  assert.equal(response.status, 200);
  let login = await response.json();
  let refreshCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(refreshCookie);

  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${login.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: password,
      newPassword: replacement,
    }),
  });
  assert.equal(changed.status, 204);

  response = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${refreshCookie}` },
  });
  assert.equal(response.status, 200);
  login = await response.json();
  refreshCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(refreshCookie);
  assert.match(login.accessToken, /\S/);
  currentAdminPassword = replacement;
  return refreshCookie;
}

before(async () => {
  const apiPort = await availablePort();
  const webPort = await availablePort();
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-e2e-"));
  baseUrl = `http://127.0.0.1:${webPort}`;

  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...process.env,
      HE_ADMIN_PASSWORD: "m1-shell-initial-password",
      HE_ADMIN_USERNAME: "admin",
      HE_DATA_DIR: dataDir,
      HE_DB_DIALECT: "sqlite",
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_JWT_SECRET: "m1-shell-e2e-signing-secret-with-sufficient-length",
      HE_PHASE: "demo",
      HE_PORT: String(apiPort),
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
      env: {
        ...process.env,
        HE_API_PROXY_URL: `http://127.0.0.1:${apiPort}`,
      },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);
});

after(async () => {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
});

test("m1-shell exposes three destinations, demo state, and clean responsive rendering", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const refreshCookie = await browserRefreshCookie();
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: refreshCookie,
      url: `${baseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const initial = await waitForDocument(
      page.session,
      `(() => {
        const nav = document.querySelector("nav");
        if (!nav || !document.querySelector("[data-testid='demo-badge']")) return null;
        return {
          path: location.pathname,
          links: [...nav.querySelectorAll("a")].map((link) => link.textContent.trim()),
          badge: document.querySelector("[data-testid='demo-badge']").textContent.trim(),
          hasEmpty: document.body.textContent.includes("暂无会话"),
        };
      })()`,
      "authenticated M1 shell",
    );
    assert.equal(initial.path, "/sessions");
    assert.deepEqual(initial.links, ["Sessions", "Errors", "Evolution"]);
    assert.equal(initial.badge, "演示数据");
    assert.equal(initial.hasEmpty, true);

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector('nav a[href="/errors"]').click()`,
    });
    const errorsPage = await waitForDocument(
      page.session,
      `location.pathname === "/errors" && document.body.textContent.includes("暂无问题")`,
      "errors placeholder",
    );
    assert.equal(errorsPage, true);

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector('nav a[href="/evolution"]').click()`,
    });
    const evolutionPage = await waitForDocument(
      page.session,
      `location.pathname === "/evolution" &&
        document.body.textContent.includes("暂无自进化运行") &&
        Boolean(document.querySelector(".canvas"))`,
      "evolution placeholder",
    );
    assert.equal(evolutionPage, true);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const shell = await waitForDocument(
      page.session,
      `(() => {
        if (!document.querySelector(".shell")) return null;
        const menu = document.querySelector(".user-menu");
        return {
          path: location.pathname,
          hasMenu: Boolean(menu),
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          menuRight: menu?.getBoundingClientRect().right ?? null,
          text: document.body.textContent.slice(0, 240),
        };
      })()`,
      "responsive M1 shell",
    );
    assert.equal(shell.path, "/evolution", JSON.stringify(shell));
    assert.equal(shell.hasMenu, true, JSON.stringify(shell));
    const layout = shell;
    assert.ok(layout.scrollWidth <= layout.clientWidth, JSON.stringify(layout));
    assert.ok(layout.menuRight <= layout.clientWidth, JSON.stringify(layout));
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
});

test("m1-shell presents a 409 as a styled message without replacing the page", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const refreshCookie = await browserRefreshCookie();
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: refreshCookie,
      url: `${baseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });

    await page.session.send("Fetch.enable", {
      patterns: [{ urlPattern: "*://*/api/health", requestStage: "Request" }],
    });
    await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `window.__e2eErrors = [];
        window.addEventListener("error", (event) => window.__e2eErrors.push(String(event.error || event.message)));
        window.addEventListener("unhandledrejection", (event) => window.__e2eErrors.push(String(event.reason)));`,
    });
    const interceptedRequests = [];
    page.session.on("Fetch.requestPaused", (event) => {
      interceptedRequests.push(event.request.url);
      void page.session.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: 409,
        responseHeaders: [
          { name: "content-type", value: "application/json" },
          { name: "access-control-allow-origin", value: baseUrl },
        ],
        body: Buffer.from(
          JSON.stringify({
            error: {
              code: "RUN_BUSY",
              details: {},
              message: "已有任务正在运行",
            },
          }),
        ).toString("base64"),
      });
    });

    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const conflict = await waitForDocument(
      page.session,
      `(() => {
        const message = document.querySelector(".el-message");
        if (!message || !document.querySelector(".shell")) return null;
        return {
          href: location.href,
          html: document.documentElement.outerHTML.slice(0, 1200),
          runtimeErrors: window.__e2eErrors ?? [],
          message: message?.textContent.trim() ?? null,
          body: document.body.textContent.slice(0, 500),
          hasNav: Boolean(document.querySelector("nav")),
          hasPage: document.body.textContent.includes("Session 浏览器"),
          hasErrorState: Boolean(document.querySelector(".error-state")),
          position: message ? getComputedStyle(message).position : null,
        };
      })()`,
      "non-blocking 409 message",
    );

    assert.equal(
      conflict.message,
      "已有任务正在运行",
      `${JSON.stringify(conflict)}\n\nIntercepted:\n${interceptedRequests.join("\n")}\n\nBrowser:\n${violations.join("\n")}\n\nVite:\n${webLogs}`,
    );
    assert.equal(conflict.hasNav, true, JSON.stringify(conflict));
    assert.equal(conflict.hasPage, true, JSON.stringify(conflict));
    assert.equal(conflict.hasErrorState, false, JSON.stringify(conflict));
    assert.equal(conflict.position, "fixed", JSON.stringify(conflict));
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});
