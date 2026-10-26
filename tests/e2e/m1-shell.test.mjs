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
let cleanupPromise;

async function cleanupRuntime() {
  cleanupPromise ??= (async () => {
    await stop(web);
    await stop(api);
    if (dataDir) await rm(dataDir, { recursive: true, force: true });
  })();
  await cleanupPromise;
}

for (const [signal, exitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  process.once(signal, () => {
    void cleanupRuntime().finally(() => process.exit(exitCode));
  });
}

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
  try {
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
  } catch (error) {
    await cleanupRuntime();
    throw error;
  }
});

after(cleanupRuntime);

test("m1-auth uses the prototype light cards and protected-page handoff", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.source === "network" &&
        entry.url?.endsWith("/api/auth/refresh") &&
        /status of 401/.test(entry.text),
    });
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/login` });
    const login = await waitForDocument(
      page.session,
      `(() => {
        const card = document.querySelector(".auth-card");
        if (!card || !document.body.textContent.includes("Harness Evolution")) return null;
        return {
          bodyBackground: getComputedStyle(document.body).backgroundColor,
          cardBackground: getComputedStyle(card).backgroundColor,
          hasTopbar: Boolean(document.querySelector(".topbar")),
          brand: document.querySelector(".brand-lockup")?.textContent.trim() ?? "",
          path: location.pathname,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "prototype login card",
    );
    assert.equal(login.path, "/login");
    assert.equal(login.bodyBackground, "rgb(244, 245, 247)");
    assert.equal(login.cardBackground, "rgb(255, 255, 255)");
    assert.equal(login.hasTopbar, false);
    assert.equal(login.brand, "Harness Evolution轨迹诊断与自进化");
    assert.ok(login.clientWidth > 0);
    assert.ok(login.clientWidth <= 1408);
    assert.equal(login.scrollWidth, login.clientWidth);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const narrowLogin = await waitForDocument(
      page.session,
      `(() => {
        const card = document.querySelector(".auth-card");
        if (!card) return null;
        const bounds = card.getBoundingClientRect();
        return {
          cardLeft: bounds.left,
          cardRight: bounds.right,
          clientWidth: document.documentElement.clientWidth,
          hasTopbar: Boolean(document.querySelector(".topbar")),
          scrollWidth: document.documentElement.scrollWidth,
        };
      })()`,
      "390px login card",
    );
    assert.equal(narrowLogin.hasTopbar, false);
    assert.ok(narrowLogin.cardLeft >= 0, JSON.stringify(narrowLogin));
    assert.ok(narrowLogin.cardRight <= narrowLogin.clientWidth, JSON.stringify(narrowLogin));
    assert.equal(narrowLogin.scrollWidth, narrowLogin.clientWidth);

    await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        const setValue = (selector, value) => {
          const input = document.querySelector(selector);
          const setter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype,
            "value",
          ).set;
          setter.call(input, value);
          input.dispatchEvent(new Event("input", { bubbles: true }));
        };
        setValue('input[name="username"]', "admin");
        setValue('input[name="password"]', ${JSON.stringify(currentAdminPassword)});
        document.querySelector("form").requestSubmit();
      })()`,
    });
    const changePassword = await waitForDocument(
      page.session,
      `(() => {
        const card = document.querySelector(".auth-card");
        if (location.pathname !== "/change-password" || !card) return null;
        return {
          cardBackground: getComputedStyle(card).backgroundColor,
          cardLeft: card.getBoundingClientRect().left,
          cardRight: card.getBoundingClientRect().right,
          clientWidth: document.documentElement.clientWidth,
          hasTopbar: Boolean(document.querySelector(".topbar")),
          path: location.pathname,
          scrollWidth: document.documentElement.scrollWidth,
        };
      })()`,
      "prototype forced-password card",
    );
    assert.equal(changePassword.path, "/change-password");
    assert.equal(changePassword.cardBackground, "rgb(255, 255, 255)");
    assert.equal(changePassword.hasTopbar, false);
    assert.ok(changePassword.cardLeft >= 0, JSON.stringify(changePassword));
    assert.ok(
      changePassword.cardRight <= changePassword.clientWidth,
      JSON.stringify(changePassword),
    );
    assert.equal(changePassword.scrollWidth, changePassword.clientWidth);
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
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
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const initial = await waitForDocument(
      page.session,
      `(() => {
        const nav = document.querySelector("nav");
        const sync = document.querySelector("[data-testid='sync-status']");
        if (
          !nav ||
          !document.querySelector("[data-testid='demo-badge']") ||
          !sync ||
          !document.querySelector(".session-browser") ||
          !document.body.textContent.includes("没有匹配当前筛选的 session")
        ) return null;
        return {
          path: location.pathname,
          links: [...nav.querySelectorAll("a")].map((link) => link.textContent.trim()),
          badge: document.querySelector("[data-testid='demo-badge']").textContent.trim(),
          pending: sync.querySelector(".sync-summary")?.textContent.trim() ?? "",
          pendingDetail: sync.getAttribute("aria-label"),
          hasEmpty: document.body.textContent.includes("没有匹配当前筛选的 session"),
          bodyBackground: getComputedStyle(document.body).backgroundColor,
          topbarBackground: getComputedStyle(document.querySelector(".topbar")).backgroundColor,
          topbarHeight: document.querySelector(".topbar").getBoundingClientRect().height,
          emptyBackground: getComputedStyle(document.querySelector(".sidebar")).backgroundColor,
          activeUnderline: getComputedStyle(
            document.querySelector("nav a.router-link-active"),
          ).borderBottomColor,
          brand: document.querySelector(".brand").textContent.trim(),
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "authenticated M1 shell",
    );
    assert.equal(initial.path, "/sessions");
    assert.deepEqual(initial.links, ["Sessions", "Errors", "Evolution"]);
    assert.equal(initial.badge, "演示数据");
    assert.equal(initial.pending, "待处理 0");
    assert.match(initial.pendingDetail, /已处理/);
    assert.equal(initial.hasEmpty, true);
    assert.equal(initial.bodyBackground, "rgb(244, 245, 247)");
    assert.equal(initial.topbarBackground, "rgb(250, 251, 252)");
    assert.equal(initial.topbarHeight, 56);
    assert.equal(initial.emptyBackground, "rgb(250, 251, 252)");
    assert.equal(initial.activeUnderline, "rgb(47, 111, 224)");
    assert.equal(initial.brand, "Harness Evolution轨迹诊断与自进化");
    assert.ok(initial.clientWidth > 0);
    assert.ok(initial.clientWidth <= 1408);
    assert.equal(initial.scrollWidth, initial.clientWidth);

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(".user-menu").open = true`,
    });
    const syncAction = await waitForDocument(
      page.session,
      `(() => {
        const action = document.querySelector("[data-testid='sync-now']");
        return action ? action.textContent.trim() : null;
      })()`,
      "admin sync action",
    );
    assert.equal(syncAction, "立即处理");
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='sync-now']").click()`,
    });
    await page.session.send("Runtime.evaluate", {
      expression: "new Promise((resolve) => setTimeout(resolve, 500))",
      awaitPromise: true,
    });
    const idleSync = await waitForDocument(
      page.session,
      `(() => {
        const action = document.querySelector("[data-testid='sync-now']");
        if (!action || action.disabled || document.querySelector(".sync-error")) return null;
        return {
          action: action.textContent.trim(),
          pending: document.querySelector(".sync-summary")?.textContent.trim() ?? "",
        };
      })()`,
      "idle admin sync",
    );
    assert.deepEqual(idleSync, { action: "立即处理", pending: "待处理 0" });

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector('nav a[href="/errors"]').click()`,
    });
    const errorsPage = await waitForDocument(
      page.session,
      `(() => {
        const active = document.querySelector("nav a.router-link-active");
        if (location.pathname !== "/errors" || !document.body.textContent.includes("请选择会话")) {
          return null;
        }
        return {
          path: location.pathname,
          underline: active ? getComputedStyle(active).borderBottomColor : null,
        };
      })()`,
      "errors entry",
    );
    assert.equal(errorsPage.path, "/errors");
    assert.equal(errorsPage.underline, "rgb(47, 111, 224)");

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector('nav a[href="/evolution"]').click()`,
    });
    const evolutionPage = await waitForDocument(
      page.session,
      `(() => {
        const active = document.querySelector("nav a.router-link-active");
        if (
          location.pathname !== "/evolution" ||
          !document.body.textContent.includes("暂无自进化运行") ||
          !document.querySelector(".canvas")
        ) {
          return null;
        }
        return {
          path: location.pathname,
          underline: active ? getComputedStyle(active).borderBottomColor : null,
        };
      })()`,
      "evolution placeholder",
    );
    assert.equal(evolutionPage.path, "/evolution");
    assert.equal(evolutionPage.underline, "rgb(138, 85, 201)");

    await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        window.history.pushState({}, "", "/missing-prototype-page");
        window.dispatchEvent(new PopStateEvent("popstate", {
          state: window.history.state,
        }));
      })()`,
    });
    const notFound = await waitForDocument(
      page.session,
      `(() => {
        const error = document.querySelector(".error-state");
        if (location.pathname !== "/missing-prototype-page" || !error) return null;
        return {
          bodyBackground: getComputedStyle(document.body).backgroundColor,
          cardBackground: getComputedStyle(error).backgroundColor,
          borderLeft: getComputedStyle(error).borderLeftColor,
          messageColor: getComputedStyle(error.querySelector(".error-message")).color,
        };
      })()`,
      "prototype not-found state",
    );
    assert.equal(notFound.bodyBackground, "rgb(244, 245, 247)");
    assert.equal(notFound.cardBackground, "rgb(255, 245, 245)");
    assert.equal(notFound.borderLeft, "rgb(214, 60, 60)");
    assert.equal(notFound.messageColor, "rgb(90, 99, 114)");

    await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        window.history.pushState({}, "", "/evolution");
        window.dispatchEvent(new PopStateEvent("popstate", {
          state: window.history.state,
        }));
      })()`,
    });
    await waitForDocument(
      page.session,
      `location.pathname === "/evolution" && Boolean(document.querySelector(".canvas"))`,
      "return to evolution placeholder",
    );

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
        const brand = document.querySelector(".brand");
        const demo = document.querySelector("[data-testid='demo-badge']");
        const sync = document.querySelector("[data-testid='sync-status']");
        return {
          path: location.pathname,
          hasMenu: Boolean(menu),
          syncDisplay: sync ? getComputedStyle(sync).display : null,
          brandAriaLabel: brand?.getAttribute("aria-label") ?? null,
          demoText: demo?.textContent.trim() ?? null,
          demoColor: demo ? getComputedStyle(demo).color : null,
          demoWidth: demo ? demo.getBoundingClientRect().width : null,
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
    assert.equal(shell.syncDisplay, "none");
    assert.equal(shell.brandAriaLabel, "Harness Evolution");
    assert.equal(shell.demoText, "演示数据");
    assert.equal(shell.demoColor, "rgb(217, 123, 28)");
    assert.ok(shell.demoWidth > 24, JSON.stringify(shell));
    const layout = shell;
    assert.ok(layout.scrollWidth <= layout.clientWidth, JSON.stringify(layout));
    assert.ok(layout.menuRight <= layout.clientWidth, JSON.stringify(layout));
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
});

test("m1-shell opens a direct Evolution URL without Vue Flow size warnings", async () => {
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
    // Reproduce a cold first paint where the scoped .canvas rule arrives late.
    await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `(() => {
        const removeDelayedCanvasRule = () => {
          for (const sheet of document.styleSheets) {
            try {
              for (let index = sheet.cssRules.length - 1; index >= 0; index -= 1) {
                const rule = sheet.cssRules[index];
                if (rule.selectorText?.includes(".canvas")) sheet.deleteRule(index);
              }
            } catch {
              // Only same-origin Vite stylesheets are inspected.
            }
          }
        };
        removeDelayedCanvasRule();
        new MutationObserver(removeDelayedCanvasRule).observe(document, {
          childList: true,
          characterData: true,
          subtree: true,
        });
        document.addEventListener("DOMContentLoaded", removeDelayedCanvasRule);
      })()`,
    });

    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution` });
    const canvas = await waitForDocument(
      page.session,
      `(() => {
        const canvas = document.querySelector(".canvas");
        if (!canvas || !document.body.textContent.includes("暂无自进化运行")) return null;
        const bounds = canvas.getBoundingClientRect();
        return {
          height: bounds.height,
          inlineHeight: canvas.style.height,
          inlineWidth: canvas.style.width,
          path: location.pathname,
          width: bounds.width,
        };
      })()`,
      "direct evolution canvas",
    );
    await new Promise((resolve) => setTimeout(resolve, 500));

    assert.equal(canvas.path, "/evolution");
    assert.ok(canvas.width > 0, JSON.stringify(canvas));
    assert.ok(canvas.height > 0, JSON.stringify(canvas));
    assert.match(canvas.inlineHeight, /\S/, JSON.stringify(canvas));
    assert.match(canvas.inlineWidth, /\S/, JSON.stringify(canvas));
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
});

test("m1-shell presents a 409 as a styled message without replacing the page", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.source === "network" &&
        entry.url?.endsWith("/api/health") &&
        /status of 409/.test(entry.text),
    });
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
    assert.deepEqual(conflict.runtimeErrors, [], JSON.stringify(conflict));
    assert.deepEqual(
      violations,
      [],
      `${violations.join("\n")}\n\nIntercepted:\n${interceptedRequests.join("\n")}\n\nVite:\n${webLogs}`,
    );
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});

test("m1-shell rejects an error-envelope health response and retries into the shell", async () => {
  const page = await createBrowserPage();
  try {
    const refreshCookie = await browserRefreshCookie();
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: refreshCookie,
      url: `${baseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `window.__e2eErrors = [];
        window.addEventListener("error", (event) => window.__e2eErrors.push(String(event.error || event.message)));
        window.addEventListener("unhandledrejection", (event) => window.__e2eErrors.push(String(event.reason)));`,
    });
    await page.session.send("Fetch.enable", {
      patterns: [{ urlPattern: "*://*/api/health", requestStage: "Request" }],
    });
    let healthAttempts = 0;
    let failHealth = true;
    const violatedLogs = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.source === "network" &&
        entry.url?.endsWith("/api/health") &&
        /status of 503/.test(entry.text),
    });
    page.session.on("Fetch.requestPaused", (event) => {
      healthAttempts += 1;
      if (failHealth) {
        void page.session.send("Fetch.fulfillRequest", {
          requestId: event.requestId,
          responseCode: 503,
          responseHeaders: [
            { name: "content-type", value: "application/json" },
            { name: "access-control-allow-origin", value: baseUrl },
          ],
          body: Buffer.from(
            JSON.stringify({
              error: {
                code: "HEALTH_UNAVAILABLE",
                details: {},
                message: "database unavailable",
              },
            }),
          ).toString("base64"),
        });
        return;
      }
      void page.session.send("Fetch.continueRequest", {
        requestId: event.requestId,
      });
    });

    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const failure = await waitForDocument(
      page.session,
      `(() => {
        const alert = document.querySelector(".error-state");
        if (!alert || !document.querySelector(".shell")) return null;
        return {
          code: alert.textContent,
          background: getComputedStyle(alert).backgroundColor,
          borderLeft: getComputedStyle(alert).borderLeftColor,
          messageColor: getComputedStyle(alert.querySelector(".error-message")).color,
          hasNav: Boolean(document.querySelector("nav")),
          runtimeErrors: window.__e2eErrors ?? [],
        };
      })()`,
      "retryable health error state",
    );
    assert.match(failure.code, /HEALTH_UNAVAILABLE/);
    assert.equal(failure.background, "rgb(255, 245, 245)");
    assert.equal(failure.borderLeft, "rgb(214, 60, 60)");
    assert.equal(failure.messageColor, "rgb(90, 99, 114)");
    assert.equal(failure.hasNav, true);
    assert.deepEqual(failure.runtimeErrors, []);

    failHealth = false;
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(".error-state button").click()`,
    });
    const recovered = await waitForDocument(
      page.session,
      `(() => {
        if (document.querySelector(".error-state")) return null;
        if (!document.body.textContent.includes("Session 浏览器")) return null;
        return {
          hasNav: Boolean(document.querySelector("nav")),
          runtimeErrors: window.__e2eErrors ?? [],
        };
      })()`,
      "recovered M1 shell",
    );
    assert.ok(healthAttempts >= 4, `health attempts: ${healthAttempts}`);
    assert.equal(recovered.hasNav, true);
    assert.deepEqual(recovered.runtimeErrors, []);
    assert.deepEqual(
      violatedLogs,
      [],
      `${violatedLogs.join("\n")}\n\nVite:\n${webLogs}`,
    );
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});
