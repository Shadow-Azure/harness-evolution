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
const secret = "m3-session-browser-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

async function loginCookie() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: "m3-session-browser-initial-password",
    }),
  });
  assert.equal(login.status, 200);
  const body = await login.json();
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${body.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: "m3-session-browser-initial-password",
      newPassword: "m3-session-browser-replacement-password",
    }),
  });
  assert.equal(changed.status, 204);
  const refresh = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1]
        ? `refresh_token=${login.headers.get("set-cookie").match(/refresh_token=([^;]+)/)[1]}`
        : "",
    },
  });
  assert.equal(refresh.status, 200);
  const cookie = refresh.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return cookie;
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m3-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: "m3-session-browser-initial-password",
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
  };
  const seeded = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env: baseEnv,
    encoding: "utf8",
  });
  assert.equal(seeded.status, 0, seeded.stderr || seeded.stdout);

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

after(cleanup);

test("m3-session-browser matches the prototype and restores URL state", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const cookie = await loginCookie();
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
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const initial = await waitForDocument(
      page.session,
      `(() => {
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        const sidebar = document.querySelector(".sidebar");
        const card = cards.find((candidate) => candidate.dataset.selected === "false");
        if (cards.length !== 4 || !sidebar || !card) return null;
        return {
          path: location.pathname,
          query: location.search,
          cards: cards.length,
          densities: document.querySelectorAll("[data-testid='density-bar']").length,
          sidebarWidth: sidebar.getBoundingClientRect().width,
          browserWidth: document.querySelector(".session-browser").getBoundingClientRect().width,
          browserRadius: getComputedStyle(document.querySelector(".session-browser")).borderRadius,
          filterLabels: [...document.querySelectorAll(".filter-label")].map((node) => node.textContent.trim()),
          ctaInHeader: Boolean(document.querySelector(".overview-head [data-testid='detail-cta']")),
          placeholderHeight: document.querySelector("[data-testid='tree-placeholder']").getBoundingClientRect().height,
          cardBackground: getComputedStyle(card).backgroundColor,
          bodyBackground: getComputedStyle(document.body).backgroundColor,
          treeRequests: performance.getEntriesByType("resource")
            .filter((entry) => entry.name.endsWith("/tree")).length,
        };
      })()`,
      "four session cards",
    );
    assert.equal(initial.cards, 4);
    assert.equal(initial.densities, 8);
    assert.match(initial.path, /^\/sessions\/.+/);
    assert.ok(Math.abs(initial.sidebarWidth - 360) < 1, JSON.stringify(initial));
    assert.equal(initial.cardBackground, "rgb(255, 255, 255)");
    assert.equal(initial.bodyBackground, "rgb(244, 245, 247)");
    assert.equal(initial.treeRequests, 0);
    assert.ok(initial.browserWidth >= 1390, JSON.stringify(initial));
    assert.equal(initial.browserRadius, "0px");
    assert.deepEqual(initial.filterLabels, ["状态", "排序"]);
    assert.equal(initial.ctaInHeader, true);
    assert.ok(Math.abs(initial.placeholderHeight - 720) < 1, JSON.stringify(initial));

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobile = await waitForDocument(
      page.session,
      `(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        columns: getComputedStyle(document.querySelector(".session-browser")).gridTemplateColumns,
        cards: document.querySelectorAll("[data-testid='session-card']").length
      }))()`,
      "mobile session browser with four cards",
    );
    assert.ok(mobile.scrollWidth <= mobile.clientWidth, JSON.stringify(mobile));
    assert.equal(mobile.cards, 4);
    assert.doesNotMatch(mobile.columns, /360px/);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });

    await page.session.send("Runtime.evaluate", {
      expression: `(async () => {
        const input = document.querySelector("[data-testid='search-input']");
        input.value = "example-repo";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      })()`,
    });
    const searched = await waitForDocument(
      page.session,
      `Boolean(location.search.includes("q=example-repo") && document.querySelector("[data-testid='session-card']"))`,
      "debounced URL search",
    );
    assert.equal(searched, true);

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='session-sort']").value = "messages";
        document.querySelector("[data-testid='session-sort']").dispatchEvent(new Event("change", { bubbles: true }));`,
    });
    const sorted = await waitForDocument(
      page.session,
      `Boolean(location.search.includes("sort=messages") && document.querySelector("[data-testid='session-overview']"))`,
      "sort URL state",
    );
    assert.equal(sorted, true);

    await page.session.send("Runtime.evaluate", {
      expression: `history.back()`,
    });
    const wentBack = await waitForDocument(
      page.session,
      `!location.search.includes("sort=messages")`,
      "browser back state",
    );
    assert.equal(wentBack, true);
    await page.session.send("Runtime.evaluate", {
      expression: `history.forward()`,
    });
    const wentForward = await waitForDocument(
      page.session,
      `location.search.includes("sort=messages")`,
      "browser forward state",
    );
    assert.equal(wentForward, true);

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
});
