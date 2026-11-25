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
const windowsShell = process.platform === "win32";
const secret = "m12-14-brand-config-signing-secret-with-sufficient-length";
const initialPassword = "m12-14-brand-config-initial-password";
const replacementPassword = "m12-14-brand-config-replacement-password";
const brandName = "Acme Diagnostics Self-Evolution Platform for Research Teams";
const brandSubtitle = "Acme Self-Evolution and Trajectory Diagnostics";
const loginLogEntry = (entry) =>
  entry.source === "network" &&
  /status of 401/.test(entry.text) &&
  (entry.url?.endsWith("/api/auth/refresh") || entry.url?.endsWith("/api/auth/login"));
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
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

before(async () => {
  try {
    // Windows sandboxes can deny SQLite writes under the system temp directory;
    // keep local test data inside the checkout while CI retains its temp root.
    const dataRoot = process.platform === "win32" ? root : tmpdir();
    dataDir = await mkdtemp(path.join(dataRoot, "harness-m12-14-e2e-"));
    const apiPort = await availablePort();
    const webPort = await availablePort();
    baseUrl = `http://127.0.0.1:${webPort}`;
    const seedEnv = {
      ...process.env,
      HE_BRAND_NAME: brandName,
      HE_BRAND_SUBTITLE: brandSubtitle,
      HE_ADMIN_PASSWORD: initialPassword,
      HE_ADMIN_USERNAME: "admin",
      HE_DATA_DIR: dataDir,
      HE_DB_DIALECT: "sqlite",
      HE_FIXTURE_MANIFEST: "fixtures/m1-shell.json",
      HE_JWT_SECRET: secret,
      HE_PHASE: "demo",
    };

    const seed = spawnSync(pnpm, ["fixtures:seed"], {
      cwd: root,
      env: seedEnv,
      encoding: "utf8",
      shell: windowsShell,
    });
    assert.equal(seed.status, 0, seed.stderr || seed.stdout);

    api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
      cwd: root,
      env: {
        ...seedEnv,
        HE_DOCS_ENABLED: "false",
        HE_HOST: "127.0.0.1",
        HE_LOGIN_RATE_LIMIT: "100",
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
        shell: windowsShell,
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

/** Log in through the API, complete the forced change, and return the refresh cookie. */
async function loginCookie() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
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
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return cookie;
}

/** Install the refresh cookie and one deterministic viewport on a fresh page. */
async function installBrowser(page, cookie, width, height) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 760,
  });
}

/** Read the configured brand pair from the login page and its document title. */
async function readLoginBrand(page, width, height) {
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 760,
  });
  await page.session.send("Page.navigate", { url: `${baseUrl}/login` });
  return await waitForDocument(
    page.session,
    `(() => {
      const lockup = document.querySelector("[data-testid='login-brand'] .brand-lockup");
      const brand = document.querySelector("[data-testid='login-brand']");
      if (!lockup || !brand) return null;
      const name = lockup.querySelector(":scope > div > strong");
      const subtitle = lockup.querySelector(":scope > div > span");
      if (!name || !subtitle) return null;
      if (document.title !== ${JSON.stringify(brandName)}) return null;
      const lockupRect = lockup.getBoundingClientRect();
      const brandRect = brand.getBoundingClientRect();
      return {
        name: name.textContent.trim(),
        subtitle: subtitle.textContent.trim(),
        title: document.title,
        nameClientWidth: name.clientWidth,
        nameScrollWidth: name.scrollWidth,
        lockupLeft: lockupRect.left,
        lockupRight: lockupRect.right,
        brandLeft: brandRect.left,
        brandRight: brandRect.right,
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      };
    })()`,
    "configured login brand",
  );
}

test("m12-14 serves the configured brand pair without authentication", async () => {
  const response = await fetch(`${baseUrl}/api/app-config`);

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    brand: { name: brandName, subtitle: brandSubtitle },
  });
});

test("m12-14 renders the configured brand on the login page and document title", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: loginLogEntry,
    });
    const login = await readLoginBrand(page, 1408, 900);

    assert.equal(login.name, brandName);
    assert.equal(login.subtitle, brandSubtitle);
    assert.equal(login.title, brandName);
    assert.equal(login.scrollWidth, login.clientWidth);
    assert.ok(login.nameScrollWidth > login.nameClientWidth, JSON.stringify(login));
    assert.ok(login.brandLeft >= 0, JSON.stringify(login));
    assert.ok(login.brandRight <= login.clientWidth, JSON.stringify(login));
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-14 truncates the configured brand at 390px without horizontal overflow", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: loginLogEntry,
    });
    const login = await readLoginBrand(page, 390, 844);

    assert.equal(login.name, brandName);
    assert.equal(login.subtitle, brandSubtitle);
    assert.equal(login.title, brandName);
    assert.equal(login.scrollWidth, login.clientWidth);
    assert.ok(login.lockupLeft >= 0, JSON.stringify(login));
    assert.ok(login.lockupRight <= login.clientWidth, JSON.stringify(login));
    assert.ok(
      login.nameScrollWidth > login.nameClientWidth,
      JSON.stringify(login),
    );
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-14 bounds the configured brand in the topbar at both viewports", async () => {
  const cookie = await loginCookie();
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    await installBrowser(page, cookie, 1408, 900);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/ws-default/sessions`,
    });
    const wide = await waitForDocument(
      page.session,
      `(() => {
        const topbar = document.querySelector(".topbar");
        const brand = topbar?.querySelector(".brand");
        const name = topbar?.querySelector(".brand-copy strong");
        const subtitle = topbar?.querySelector(".brand-copy small");
        if (!brand || !name || !subtitle) return null;
        if (name.textContent.trim() !== ${JSON.stringify(brandName)}) return null;
        const rect = brand.getBoundingClientRect();
        return {
          aria: brand.getAttribute("aria-label"),
          name: name.textContent.trim(),
          subtitle: subtitle.textContent.trim(),
          nameClientWidth: name.clientWidth,
          nameScrollWidth: name.scrollWidth,
          brandLeft: rect.left,
          brandRight: rect.right,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "configured topbar brand",
    );

    assert.equal(wide.aria, brandName);
    assert.equal(wide.name, brandName);
    assert.equal(wide.subtitle, brandSubtitle);
    assert.ok(wide.nameScrollWidth > wide.nameClientWidth, JSON.stringify(wide));
    assert.equal(wide.scrollWidth, wide.clientWidth);
    assert.ok(wide.brandLeft >= 0, JSON.stringify(wide));
    assert.ok(wide.brandRight <= wide.clientWidth, JSON.stringify(wide));

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const narrow = await waitForDocument(
      page.session,
      `(() => {
        const topbar = document.querySelector(".topbar");
        const brand = topbar?.querySelector(".brand");
        const copy = topbar?.querySelector(".brand-copy");
        if (!brand || !copy) return null;
        const rect = brand.getBoundingClientRect();
        return {
          copyDisplay: getComputedStyle(copy).display,
          brandLeft: rect.left,
          brandRight: rect.right,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "compact topbar brand",
    );

    assert.equal(narrow.copyDisplay, "none");
    assert.equal(narrow.scrollWidth, narrow.clientWidth);
    assert.ok(narrow.brandLeft >= 0, JSON.stringify(narrow));
    assert.ok(narrow.brandRight <= narrow.clientWidth, JSON.stringify(narrow));
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
