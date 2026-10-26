import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../../../tests/support/runtime.mjs";

const root = process.cwd();
const reportDir = path.resolve("reports/2026-10-27/m5-03-target-config-ui");
const screenshotDir = path.join(reportDir, "screenshots");
const runtimePath = path.join(tmpdir(), "harness-m5-03-smoke-runtime.json");
const apiDir = path.join(root, "apps/api");
const python = path.join(apiDir, ".venv", "bin", "python");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m5-smoke-initial-password";
const finalPassword = "m5-smoke-final-password";
const memberInitialPassword = "m5-member-initial-password";
const memberFinalPassword = "m5-member-final-password";
const secret = "m5-target-smoke-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let apiUrl;
let baseUrl;
let apiLogs = "";
let webLogs = "";
const results = [];

function record(id, name, detail, evidence, status = "pass") {
  results.push({ id, name, status, detail, evidence });
}

async function apiJson(pathname, token, options = {}) {
  const response = await fetch(`${apiUrl}${pathname}`, {
    ...options,
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const text = await response.text();
  assert.equal(response.status, options.expectedStatus ?? 200, text);
  if (response.status === 204) return null;
  return JSON.parse(text);
}

async function authenticate(username, password, replacement) {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);
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
  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  assert.equal(refreshed.status, 200);
  const access = await refreshed.json();
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return { accessToken: access.accessToken, cookie };
}

async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.clearBrowserCookies");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
}

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function screenshot(page, filename) {
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(screenshotDir, filename), data, "base64");
}

async function setInput(page, selector, value) {
  const updated = await evaluate(
    page,
    `(() => {
      const input = document.querySelector(${JSON.stringify(selector)});
      if (!input) return false;
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      ).set;
      input.focus();
      setter.call(input, ${JSON.stringify(value)});
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return input.value === ${JSON.stringify(value)};
    })()`,
  );
  assert.equal(updated, true, `missing input ${selector}`);
}

async function clickText(page, selector, text) {
  const clicked = await evaluate(
    page,
    `(() => {
      const element = [...document.querySelectorAll(${JSON.stringify(selector)})]
        .find((item) => item.textContent.trim() === ${JSON.stringify(text)});
      if (!element) return false;
      element.click();
      return true;
    })()`,
  );
  assert.equal(clicked, true, `missing ${selector} with text ${text}`);
}

async function fillTargetForm(page, { name, repoUrl, subDir, defaultRef }) {
  await setInput(page, "input[name='objectName']", name);
  await setInput(page, "input[name='repoUrl']", repoUrl);
  await setInput(page, "input[name='subDir']", subDir);
  await evaluate(
    page,
    `document.querySelector("[data-testid='target-version-select']").click()`,
  );
  await waitForDocument(
    page.session,
    `Boolean(document.querySelector(".target-version-select input"))`,
    "version select input",
  );
  await evaluate(
    page,
    `document.querySelector(".target-version-select input").focus()`,
  );
  await page.session.send("Input.insertText", { text: defaultRef });
  await waitForDocument(
    page.session,
    `[...document.querySelectorAll(".el-select-dropdown__item")]
      .some((item) => item.textContent.trim() === ${JSON.stringify(defaultRef)})`,
    "created version option",
  );
  await clickText(page, ".el-select-dropdown__item", defaultRef);
}

async function startServices() {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m5-smoke-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };
  const seed = spawn(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let seedLogs = "";
  capture(seed, (chunk) => {
    seedLogs += chunk;
  });
  const seedExit = await new Promise((resolve) => seed.once("exit", resolve));
  assert.equal(seedExit, 0, seedLogs);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  apiUrl = `http://127.0.0.1:${apiPort}`;
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(python, [path.join(root, "tests/e2e/support/m5_target_server.py")], {
    cwd: root,
    env: {
      ...env,
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
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);

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
      env: { ...process.env, HE_API_PROXY_URL: apiUrl },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);
}

async function collectCdpEvidence() {
  const admin = await authenticate("admin", initialPassword, finalPassword);
  await apiJson("/api/users", admin.accessToken, {
    expectedStatus: 201,
    method: "POST",
    body: JSON.stringify({
      username: "m5-member",
      displayName: "M5 Member",
      password: memberInitialPassword,
      role: "member",
    }),
  });
  const member = await authenticate(
    "m5-member",
    memberInitialPassword,
    memberFinalPassword,
  );
  let page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: (entry) =>
      entry.source === "network" &&
      entry.url?.includes("/api/evolution/targets") &&
      /status of 422/.test(entry.text),
  });
  let memberViolations = [];
  try {
    await installCookie(page, admin.cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".shell"))`,
      "authenticated shell",
    );
    await evaluate(page, `history.pushState({}, "", "/evolution/targets");
      window.dispatchEvent(new PopStateEvent("popstate"));`);
    const desktop = await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector(".target-config-page");
        if (!page) return null;
        const rect = page.getBoundingClientRect();
        return {
          width: rect.width,
          left: rect.left,
          right: rect.right,
          title: page.querySelector("h1")?.textContent.trim(),
          note: page.querySelector(".page-note")?.textContent.trim(),
          viewport: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        };
      })()`,
      "desktop target page",
    );
    assert.equal(desktop.title, "进化对象配置");
    assert.match(desktop.note, /skill 与 agent/);
    assert.ok(Math.abs(desktop.width - 1080) <= 1, JSON.stringify(desktop));
    assert.equal(desktop.scrollWidth, desktop.viewport);
    await screenshot(page, "01-desktop-1408.png");
    record(
      "01",
      "1408px 原型页面骨架",
      "页面外框 1080px、标题与说明采用原型层级，无横向溢出。",
      ["screenshots/01-desktop-1408.png"],
    );

    await evaluate(page, `document.querySelector(".target-create").click()`);
    const modal = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector(".target-form-dialog");
        if (!root) return null;
        const dialog = root.matches(".el-dialog")
          ? root
          : root.querySelector(".el-dialog");
        const overlay = document.querySelector(".el-overlay");
        const rect = dialog.getBoundingClientRect();
        const overlayRect = overlay.getBoundingClientRect();
        const body = root.querySelector(".target-dialog-body");
        return {
          width: rect.width,
          radius: getComputedStyle(dialog).borderRadius,
          titleSize: getComputedStyle(
            root.querySelector(".target-dialog-head .el-dialog__title"),
          ).fontSize,
          bodyMaxHeight: Number.parseFloat(getComputedStyle(body).maxHeight),
          overlay: {
            left: overlayRect.left,
            top: overlayRect.top,
            right: overlayRect.right,
            bottom: overlayRect.bottom,
          },
          viewportWidth: innerWidth,
          viewportHeight: innerHeight,
        };
      })()`,
      "desktop modal",
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    assert.ok(Math.abs(modal.width - 720) <= 1, JSON.stringify(modal));
    assert.equal(modal.radius, "14px");
    assert.equal(modal.titleSize, "15px");
    assert.ok(Math.abs(modal.overlay.left) <= 1);
    assert.ok(Math.abs(modal.overlay.top) <= 1);
    assert.ok(Math.abs(modal.overlay.right - modal.viewportWidth) <= 1);
    assert.ok(Math.abs(modal.overlay.bottom - modal.viewportHeight) <= 1);
    await screenshot(page, "02-modal-1408.png");
    record(
      "02",
      "720px 新增表单与全视口遮罩",
      "表单 14px 圆角、15px 标题、66vh 滚动体与全视口遮罩均符合原型。",
      ["screenshots/02-modal-1408.png"],
    );

    await fillTargetForm(page, {
      name: "m5-smoke-target",
      repoUrl: "https://invalid.example.com/repo.git",
      subDir: "skills/m5-smoke-target",
      defaultRef: "v2.0.0",
    });
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    const inlineError = await waitForDocument(
      page.session,
      `document.querySelector(".server-error")?.textContent.trim()`,
      "inline invalid repository error",
    );
    assert.match(inlineError, /仓库或 ref 无效/);
    assert.equal(
      await evaluate(page, `document.querySelectorAll(".el-message").length`),
      0,
    );
    await screenshot(page, "03-inline-error.png");
    record(
      "03",
      "422 表单内收敛",
      "无效仓库只显示表单内中文错误，输入保留，不弹全局 toast。",
      ["screenshots/03-inline-error.png"],
    );

    await setInput(
      page,
      "input[name='repoUrl']",
      "https://git.example.com/agent-skills.git",
    );
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    await waitForDocument(
      page.session,
      `[...document.querySelectorAll(".object-name")]
        .some((item) => item.textContent.trim() === "m5-smoke-target")`,
      "created target row",
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    const rowEvidence = await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-smoke-target"));
        const kind = getComputedStyle(row.querySelector(".kind-chip"));
        const state = getComputedStyle(row.querySelector(".state-chip"));
        return {
          kindColor: kind.color,
          kindBackground: kind.backgroundColor,
          stateColor: state.color,
          stateBackground: state.backgroundColor,
        };
      })()`,
    );
    assert.equal(rowEvidence.kindColor, "rgb(138, 85, 201)");
    assert.notEqual(rowEvidence.kindBackground, "rgba(0, 0, 0, 0)");
    assert.equal(rowEvidence.stateColor, "rgb(31, 157, 107)");
    assert.notEqual(rowEvidence.stateBackground, "rgba(0, 0, 0, 0)");
    await screenshot(page, "04-created-row.png");
    record(
      "04",
      "新增成功与语义 chip",
      "真实 API 写入后行出现；kind 使用紫色 chip，enabled 使用绿色 tinted badge。",
      ["screenshots/04-created-row.png"],
    );

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 800,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const medium = await evaluate(
      page,
      `(() => {
        const page = document.querySelector(".target-config-page");
        const rect = page.getBoundingClientRect();
        const style = getComputedStyle(page);
        return {
          width: rect.width,
          contentWidth:
            rect.width -
            Number.parseFloat(style.paddingLeft) -
            Number.parseFloat(style.paddingRight),
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
    );
    assert.ok(Math.abs(medium.width - 800) <= 1, JSON.stringify(medium));
    assert.ok(Math.abs(medium.contentWidth - 752) <= 1, JSON.stringify(medium));
    assert.equal(medium.scrollWidth, medium.clientWidth);
    await screenshot(page, "05-medium-800.png");
    record(
      "05",
      "800px 中等视口",
      "页面外框 800px、内容区 752px、24px gutter，不再重复缩进。",
      ["screenshots/05-medium-800.png"],
    );

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobile = await evaluate(
      page,
      `(() => {
        const page = document.querySelector(".target-config-page");
        const rect = page.getBoundingClientRect();
        const style = getComputedStyle(page);
        const scroller = document.querySelector(".target-table-scroll");
        return {
          width: rect.width,
          contentWidth:
            rect.width -
            Number.parseFloat(style.paddingLeft) -
            Number.parseFloat(style.paddingRight),
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
          tableScrollWidth: scroller.scrollWidth,
          tableClientWidth: scroller.clientWidth,
        };
      })()`,
    );
    assert.ok(Math.abs(mobile.width - 390) <= 1, JSON.stringify(mobile));
    assert.ok(Math.abs(mobile.contentWidth - 342) <= 1, JSON.stringify(mobile));
    assert.equal(mobile.pageScrollWidth, mobile.pageClientWidth);
    assert.ok(mobile.tableScrollWidth > mobile.tableClientWidth);
    await screenshot(page, "06-mobile-390.png");
    record(
      "06",
      "390px 响应式",
      "页面内容区 342px、无页面横向溢出；宽表格在自身容器内横向滚动。",
      ["screenshots/06-mobile-390.png"],
    );

    await evaluate(page, `document.querySelector(".target-create").click()`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".target-form-dialog"))`,
      "mobile modal",
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    const mobileModal = await evaluate(
      page,
      `(() => {
        const root = document.querySelector(".target-form-dialog");
        const dialog = root.matches(".el-dialog")
          ? root
          : root.querySelector(".el-dialog");
        const rect = dialog.getBoundingClientRect();
        return {
          width: rect.width,
          left: rect.left,
          right: rect.right,
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
        };
      })()`,
    );
    assert.ok(Math.abs(mobileModal.width - 358) <= 1, JSON.stringify(mobileModal));
    assert.ok(Math.abs(mobileModal.left - 16) <= 1, JSON.stringify(mobileModal));
    assert.ok(Math.abs(mobileModal.right - 374) <= 1, JSON.stringify(mobileModal));
    assert.equal(mobileModal.pageScrollWidth, mobileModal.pageClientWidth);
    await screenshot(page, "07-modal-390.png");
    await clickText(page, ".target-form-dialog button", "取消");
    record(
      "07",
      "390px 表单",
      "modal 宽 358px、左右 16px，页面本体无横向溢出。",
      ["screenshots/07-modal-390.png"],
    );

    await page.close();
    page = await createBrowserPage();
    memberViolations = browserViolations(page.session);
    await installCookie(page, member.cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/evolution/targets`,
    });
    const memberState = await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector(".target-config-page");
        if (!page || !page.querySelector(".target-table tbody tr")) return null;
        return {
          create: Boolean(page.querySelector(".target-create")),
          actions: Boolean(page.querySelector(".row-actions")),
          overflow:
            document.documentElement.scrollWidth ===
            document.documentElement.clientWidth,
        };
      })()`,
      "member target page",
    );
    assert.equal(memberState.create, false);
    assert.equal(memberState.actions, false);
    assert.equal(memberState.overflow, true);
    await screenshot(page, "08-member-390.png");
    record(
      "08",
      "成员只读权限",
      "成员可见真实配置行，但没有新增或行操作，390px 仍无页面溢出。",
      ["screenshots/08-member-390.png"],
    );

    await evaluate(page, `history.pushState({}, "", "/evolution");
      window.dispatchEvent(new PopStateEvent("popstate"));`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".target-config-entry"))`,
      "evolution entry",
    );
    await screenshot(page, "09-evolution-entry-390.png");
    record(
      "09",
      "自进化页齿轮入口",
      "icon-only 齿轮入口可见，390px 下布局不溢出。",
      ["screenshots/09-evolution-entry-390.png"],
    );

    assert.deepEqual(violations, []);
    assert.deepEqual(memberViolations, []);
    record(
      "10",
      "Console / network",
      "除刻意验证的 422 响应外，未捕获 warning、error 或未处理异常。",
      ["cdp-evidence.json"],
    );
  } finally {
    await page.close();
  }
  await writeFile(
    path.join(reportDir, "cdp-evidence.json"),
    JSON.stringify(
      {
        results,
        violations: [...violations, ...memberViolations],
        baseUrl,
        apiUrl,
      },
      null,
      2,
    ),
  );
  const targets = await apiJson("/api/evolution/targets", admin.accessToken);
  await writeFile(
    runtimePath,
    JSON.stringify(
      {
        baseUrl,
        apiUrl,
        adminUsername: "admin",
        adminPassword: finalPassword,
        memberUsername: "m5-member",
        memberPassword: memberFinalPassword,
        targetCount: targets.items.length,
      },
      null,
      2,
    ),
  );
}

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) {
    await rm(dataDir, { recursive: true, force: true, maxRetries: 10 });
  }
}

await mkdir(screenshotDir, { recursive: true });
try {
  await startServices();
  await collectCdpEvidence();
  process.stdout.write(`SMOKE_READY ${baseUrl}\n`);
  await new Promise((resolve) => {
    process.once("SIGINT", resolve);
    process.once("SIGTERM", resolve);
  });
} finally {
  await cleanup();
}
