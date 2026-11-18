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
const initialPassword = "m12-11-login-initial-password";
const expectedLogEntry = (entry) =>
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
    const apiPort = await availablePort();
    const webPort = await availablePort();
    dataDir = await mkdtemp(path.join(tmpdir(), "harness-e2e-"));
    baseUrl = `http://127.0.0.1:${webPort}`;

    const setup = spawnSync(pnpm, ["fixtures:seed"], {
      cwd: root,
      env: {
        ...process.env,
        HE_ADMIN_PASSWORD: initialPassword,
        HE_ADMIN_USERNAME: "admin",
        HE_DATA_DIR: dataDir,
        HE_DB_DIALECT: "sqlite",
        HE_FIXTURE_MANIFEST: "fixtures/m1-shell.json",
        HE_JWT_SECRET: "m12-11-login-e2e-signing-secret-with-sufficient-length",
        HE_PHASE: "demo",
      },
      encoding: "utf8",
    });
    assert.equal(setup.status, 0, setup.stderr || setup.stdout);

    api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
      cwd: root,
      env: {
        ...process.env,
        HE_ADMIN_PASSWORD: initialPassword,
        HE_ADMIN_USERNAME: "admin",
        HE_DATA_DIR: dataDir,
        HE_DB_DIALECT: "sqlite",
        HE_DOCS_ENABLED: "false",
        HE_HOST: "127.0.0.1",
        HE_JWT_SECRET: "m12-11-login-e2e-signing-secret-with-sufficient-length",
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

async function openLogin(page, width, height) {
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
      const card = document.querySelector(".auth-card");
      const brand = document.querySelector("[data-testid='login-brand']");
      const form = document.querySelector("[data-testid='login-form-region']");
      if (!card || !brand || !form) return null;
      const rect = (element) => {
        const bounds = element.getBoundingClientRect();
        return {
          left: bounds.left,
          right: bounds.right,
          top: bounds.top,
          bottom: bounds.bottom,
          width: bounds.width,
        };
      };
      const points = document.querySelector("[data-testid='login-capabilities']");
      const footnote = [...document.querySelectorAll("p")].find((element) =>
        element.textContent.includes("首次登录需要设置自己的密码"),
      );
      return {
        card: rect(card),
        brand: rect(brand),
        form: rect(form),
        capabilities: points
          ? { display: getComputedStyle(points).display, text: points.textContent }
          : null,
        footnoteVisible: Boolean(footnote) && footnote.getBoundingClientRect().height > 0,
        inputs: [...document.querySelectorAll("input")].map((input) => input.name),
        buttons: [...document.querySelectorAll("button")].map((button) =>
          button.textContent.trim(),
        ),
        accounts: document.querySelectorAll("[data-testid='login-account']").length,
        emails: document.body.textContent.match(/[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}/gi),
        accountDirectoryText: document.body.textContent.includes("演示账号"),
        hasTopbar: Boolean(document.querySelector(".topbar")),
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      };
    })()`,
    "login page",
  );
}

test("m12-11 renders the V2 two-column login with capability copy and no account directory", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const requests = [];
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      requests.push(request.url);
    });
    await page.session.send("Network.enable");

    const login = await openLogin(page, 1408, 900);

    assert.ok(
      login.card.width >= 900 && login.card.width <= 940,
      JSON.stringify(login.card),
    );
    assert.ok(
      login.brand.right <= login.form.left + 1,
      `columns overlap: ${JSON.stringify({ brand: login.brand, form: login.form })}`,
    );
    assert.ok(Math.abs(login.brand.top - login.form.top) < 2);
    assert.ok(login.brand.width > 400 && login.form.width > 400);
    assert.equal(login.hasTopbar, false);
    assert.equal(login.scrollWidth, login.clientWidth);

    assert.match(login.capabilities.text, /工作空间隔离/);
    assert.match(login.capabilities.text, /归因进入进化流程/);
    assert.match(login.capabilities.text, /默认 10 个 Session/);
    assert.equal(login.footnoteVisible, true);

    assert.equal(login.accounts, 0);
    assert.equal(login.emails, null);
    assert.equal(login.accountDirectoryText, false);
    assert.deepEqual(login.buttons, ["登录"]);
    assert.deepEqual(login.inputs, ["username", "password"]);

    assert.equal(
      requests.some((url) => /\/api\/(users|members)(\/|\?|$)/.test(url)),
      false,
      requests.join("\n"),
    );
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-11 collapses the login card to one column at 390px", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const login = await openLogin(page, 390, 844);

    assert.ok(login.card.left >= 0, JSON.stringify(login.card));
    assert.ok(login.card.right <= login.clientWidth, JSON.stringify(login.card));
    assert.ok(login.form.top >= login.brand.bottom - 1, JSON.stringify(login));
    assert.ok(login.brand.width >= login.card.width - 2);
    assert.ok(login.form.width >= login.card.width - 2);
    assert.equal(login.capabilities.display, "none");
    assert.match(login.capabilities.text, /默认 10 个 Session/);
    assert.equal(login.footnoteVisible, true);
    assert.equal(login.scrollWidth, login.clientWidth);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

async function pressTab(page) {
  for (const type of ["rawKeyDown", "keyUp"]) {
    await page.session.send("Input.dispatchKeyEvent", {
      type,
      key: "Tab",
      code: "Tab",
      windowsVirtualKeyCode: 9,
      nativeVirtualKeyCode: 9,
    });
  }
}

test("m12-11 keeps keyboard order, inline errors, and the forced-change hint", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    await openLogin(page, 1440, 900);
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
        setValue('input[name="password"]', "definitely-wrong");
        document.activeElement instanceof HTMLElement && document.activeElement.blur();
      })()`,
    });

    const focused = async () => {
      const result = await page.session.send("Runtime.evaluate", {
        expression: `(() => {
          const element = document.activeElement;
          return {
            name: element?.getAttribute?.("name") ?? "",
            testid: element?.getAttribute?.("data-testid") ?? "",
            tag: element?.tagName ?? "",
          };
        })()`,
        returnByValue: true,
      });
      return result.result.value;
    };

    await pressTab(page);
    assert.equal((await focused()).name, "username");
    await pressTab(page);
    assert.equal((await focused()).name, "password");
    await pressTab(page);
    assert.equal((await focused()).testid, "login-submit");

    await page.session.send("Runtime.evaluate", {
      expression: "document.querySelector('form').requestSubmit()",
    });
    const alert = await waitForDocument(
      page.session,
      `(() => {
        const element = document.querySelector("[role='alert']");
        if (!element || !element.textContent.includes("用户名或密码错误")) return null;
        return {
          text: element.textContent.trim(),
          live: element.getAttribute("aria-live"),
        };
      })()`,
      "inline credential error",
    );
    assert.equal(alert.text, "用户名或密码错误");
    assert.equal(alert.live, "polite");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
