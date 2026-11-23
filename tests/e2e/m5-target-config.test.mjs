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

import { uploadSkill } from "./support/attribution-skill.mjs";

const root = process.cwd();
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m5-target-ui-initial-password";
const replacementPassword = "m5-target-ui-final-password";
const memberInitialPassword = "m5-member-initial-password";
const memberFinalPassword = "m5-member-final-password";
const secret = "m5-target-ui-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      try {
        await rm(dataDir, { recursive: true, force: true });
        break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  }
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
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text);
  }
  return result.result.value;
}

async function waitForTargetConfigPage(page, label, violations) {
  try {
    await waitForDocument(
      page.session,
      `document.querySelector("h1")?.textContent === "进化对象配置" &&
        document.querySelectorAll(".target-table tbody tr").length > 0`,
      label,
    );
  } catch (error) {
    const diagnostics = await evaluate(
      page,
      `(() => ({
        url: location.href,
        body: document.body.textContent?.trim().slice(0, 500) ?? "",
        hasShell: Boolean(document.querySelector(".shell")),
        hasLogin: Boolean(document.querySelector("[data-testid='login-submit']")),
        hasTargetPage: Boolean(document.querySelector(".target-config-page")),
        errorStates: [...document.querySelectorAll(".error-state")]
          .map((node) => node.textContent?.trim()),
      }))()`,
    ).catch((diagnosticError) => ({
      diagnosticError:
        diagnosticError instanceof Error
          ? diagnosticError.message
          : String(diagnosticError),
    }));
    throw new Error(
      `${error instanceof Error ? error.message : String(error)}\n${JSON.stringify(
        {
          diagnostics,
          violations,
          apiLogs: apiLogs.slice(-2_000),
          webLogs: webLogs.slice(-2_000),
        },
        null,
        2,
      )}`,
    );
  }
}

async function setInput(page, selector, value) {
  const ok = await evaluate(
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
  assert.equal(ok, true, `missing input ${selector}`);
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

async function fillTargetForm(page, values) {
  await setInput(page, "input[name='objectName']", values.name);
  await setInput(page, "input[name='repoUrl']", values.repoUrl);
  await setInput(page, "input[name='subDir']", values.subDir);
  await setInput(page, "input[name='defaultRef']", values.defaultRef);
  await setInput(
    page,
    "input[name='validationProjectId']",
    values.validationProjectId ?? "val-m5-e2e",
  );
  await setInput(
    page,
    "input[name='testProjectId']",
    values.testProjectId ?? "test-m5-e2e",
  );
}

async function runTool(action, value) {
  const child = spawn(python, [path.join(root, "tests/e2e/support/m5_target_run_tool.py"), action, value], {
    cwd: root,
    env: {
      ...process.env,
      HE_DATA_DIR: dataDir,
      AI_AGENT_PROVIDER: "fake",
      HE_ATTRIBUTION_PACKAGE_DIR: path.join(dataDir, "attribute"),
      HE_DB_DIALECT: "sqlite",
      HE_JWT_SECRET: secret,
      PYTHONPATH: apiDir,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  capture(child, (chunk) => {
    output += chunk;
  });
  const code = await new Promise((resolve) => child.once("exit", resolve));
  assert.equal(code, 0, output);
  return output.trim();
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m5-target-e2e-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    AI_AGENT_PROVIDER: "fake",
    HE_ATTRIBUTION_PACKAGE_DIR: path.join(dataDir, "attribute"),
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };
  const seed = spawn(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    shell: process.platform === "win32",
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
      shell: process.platform === "win32",
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

test("m5 target configuration and attribution-skill binding support admin CRUD and member read-only", async () => {
  const admin = await authenticate("admin", initialPassword, replacementPassword);
  const member = await apiJson("/api/users", admin.accessToken, {
    expectedStatus: 201,
    method: "POST",
    body: JSON.stringify({
      username: "m5-member",
      displayName: "M5 Member",
      password: memberInitialPassword,
      role: "member",
    }),
  });
  assert.equal(member.username, "m5-member");
  const workspaces = await apiJson("/api/workspaces", admin.accessToken);
  const defaultWorkspace = workspaces.items.find((item) => item.id === "ws-default");
  assert.ok(defaultWorkspace);
  const workspaceBase = `/workspaces/${defaultWorkspace.id}`;
  const packagesPath = `/api/workspaces/${defaultWorkspace.id}/attribution-skill-packages`;
  const uploaded = await uploadSkill(python, `${apiUrl}${packagesPath}`, admin.accessToken, "e2e-attribution");
  await apiJson(
    `/api/workspaces/${defaultWorkspace.id}/members`,
    admin.accessToken,
    {
      expectedStatus: 201,
      method: "POST",
      body: JSON.stringify({ userId: member.id, role: "viewer" }),
    },
  );
  const memberAuth = await authenticate(
    "m5-member",
    memberInitialPassword,
    memberFinalPassword,
  );

  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: (entry) =>
      entry.source === "network" &&
      entry.url?.includes("/evolution/targets") &&
      /status of (422|409)/.test(entry.text),
  });
  try {
    await installCookie(page, admin.cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 788,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${workspaceBase}/evolution/targets`,
    });
    await waitForTargetConfigPage(page, "target config page", violations);
    await waitForDocument(
      page.session,
      `document.querySelector(".runtime-notice[role=status]")?.textContent.includes("归因运行时不可用")`,
      "cache-only provider status on the target page",
    );
    const desktopLayout = await evaluate(
      page,
      `(() => {
        const page = document.querySelector(".target-config-page");
        const rect = page.getBoundingClientRect();
        const style = getComputedStyle(page);
        const heading = page.querySelector(".page-head h1");
        const note = page.querySelector(".page-note");
        const headingStyle = getComputedStyle(heading);
        const noteStyle = getComputedStyle(note);
        const scroller = page.querySelector(".target-table-scroll");
        const actions = [...page.querySelectorAll(".row-actions")];
        const scrollerRect = scroller.getBoundingClientRect();
        return {
          width: rect.width,
          contentWidth:
            rect.width -
            Number.parseFloat(style.paddingLeft) -
            Number.parseFloat(style.paddingRight),
          paddingLeft: Number.parseFloat(style.paddingLeft),
          paddingRight: Number.parseFloat(style.paddingRight),
          left: rect.left,
          right: rect.right,
          center: rect.left + rect.width / 2,
          viewportCenter: document.documentElement.clientWidth / 2,
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
          hasEyebrow: Boolean(page.querySelector(".eyebrow, .lede")),
          headingFontSize: headingStyle.fontSize,
          headingFontWeight: headingStyle.fontWeight,
          noteFontSize: noteStyle.fontSize,
          noteColor: noteStyle.color,
          tableScrollWidth: scroller.scrollWidth,
          tableClientWidth: scroller.clientWidth,
          actionsFullyVisible: actions.length > 0 &&
            actions.every(
              (node) => node.getBoundingClientRect().right <= scrollerRect.right + 0.5,
            ),
        };
      })()`,
    );
    assert.ok(Math.abs(desktopLayout.width - 1408) <= 1, JSON.stringify(desktopLayout));
    assert.ok(Math.abs(desktopLayout.contentWidth - 1360) <= 1, JSON.stringify(desktopLayout));
    assert.equal(desktopLayout.paddingLeft, 24);
    assert.equal(desktopLayout.paddingRight, 24);
    assert.ok(
      Math.abs(desktopLayout.center - desktopLayout.viewportCenter) <= 1,
      JSON.stringify(desktopLayout),
    );
    assert.equal(desktopLayout.hasEyebrow, false);
    assert.equal(desktopLayout.headingFontSize, "18px");
    assert.equal(desktopLayout.headingFontWeight, "700");
    assert.equal(desktopLayout.noteFontSize, "12px");
    assert.equal(desktopLayout.noteColor, "rgb(154, 162, 174)");
    assert.equal(desktopLayout.pageScrollWidth, desktopLayout.pageClientWidth);
    assert.equal(
      desktopLayout.tableScrollWidth,
      desktopLayout.tableClientWidth,
      JSON.stringify(desktopLayout),
    );
    assert.equal(desktopLayout.actionsFullyVisible, true, JSON.stringify(desktopLayout));

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1920,
      height: 1080,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const wideLayout = await evaluate(
      page,
      `(() => {
        const page = document.querySelector(".target-config-page");
        const rect = page.getBoundingClientRect();
        const style = getComputedStyle(page);
        const scroller = page.querySelector(".target-table-scroll");
        const actions = [...page.querySelectorAll(".row-actions")];
        const scrollerRect = scroller.getBoundingClientRect();
        return {
          width: rect.width,
          contentWidth:
            rect.width -
            Number.parseFloat(style.paddingLeft) -
            Number.parseFloat(style.paddingRight),
          center: rect.left + rect.width / 2,
          viewportCenter: document.documentElement.clientWidth / 2,
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
          tableScrollWidth: scroller.scrollWidth,
          tableClientWidth: scroller.clientWidth,
          actionsFullyVisible: actions.length > 0 &&
            actions.every(
              (node) => node.getBoundingClientRect().right <= scrollerRect.right + 0.5,
            ),
        };
      })()`,
    );
    assert.ok(Math.abs(wideLayout.width - 1720) <= 1, JSON.stringify(wideLayout));
    assert.ok(Math.abs(wideLayout.contentWidth - 1672) <= 1, JSON.stringify(wideLayout));
    assert.ok(
      Math.abs(wideLayout.center - wideLayout.viewportCenter) <= 1,
      JSON.stringify(wideLayout),
    );
    assert.equal(wideLayout.pageScrollWidth, wideLayout.pageClientWidth);
    assert.equal(wideLayout.tableScrollWidth, wideLayout.tableClientWidth, JSON.stringify(wideLayout));
    assert.equal(wideLayout.actionsFullyVisible, true, JSON.stringify(wideLayout));

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1024,
      height: 768,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const narrowLayout = await evaluate(
      page,
      `(() => {
        const page = document.querySelector(".target-config-page");
        const rect = page.getBoundingClientRect();
        const style = getComputedStyle(page);
        const scroller = page.querySelector(".target-table-scroll");
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
    assert.ok(Math.abs(narrowLayout.width - 1024) <= 1, JSON.stringify(narrowLayout));
    assert.ok(Math.abs(narrowLayout.contentWidth - 976) <= 1, JSON.stringify(narrowLayout));
    assert.equal(narrowLayout.pageScrollWidth, narrowLayout.pageClientWidth);
    assert.ok(
      narrowLayout.tableScrollWidth > narrowLayout.tableClientWidth,
      JSON.stringify(narrowLayout),
    );

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 800,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const mediumLayout = await evaluate(
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
          paddingLeft: Number.parseFloat(style.paddingLeft),
          paddingRight: Number.parseFloat(style.paddingRight),
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
        };
      })()`,
    );
    assert.ok(Math.abs(mediumLayout.width - 800) <= 1, JSON.stringify(mediumLayout));
    assert.ok(Math.abs(mediumLayout.contentWidth - 752) <= 1, JSON.stringify(mediumLayout));
    assert.equal(mediumLayout.paddingLeft, 24);
    assert.equal(mediumLayout.paddingRight, 24);
    assert.equal(mediumLayout.pageScrollWidth, mediumLayout.pageClientWidth);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });

    await evaluate(page, `document.querySelector(".target-create").click()`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".target-form-dialog"))`,
      "create dialog",
    );
    const dialogLayout = await evaluate(
      page,
      `(() => {
        const root = document.querySelector(".target-form-dialog");
        const dialog = root.matches(".el-dialog")
          ? root
          : root.querySelector(".el-dialog");
        const rect = dialog.getBoundingClientRect();
        const head = root.querySelector(".target-dialog-head");
        const body = root.querySelector(".target-dialog-body");
        const foot = root.querySelector(".target-dialog-foot");
        const title = root.querySelector(".target-dialog-head .el-dialog__title");
        const overlay = document.querySelector(".el-overlay");
        const overlayRect = overlay.getBoundingClientRect();
        const bodyStyle = getComputedStyle(body);
        const titleStyle = getComputedStyle(title);
        return {
          width: rect.width,
          radius: getComputedStyle(dialog).borderRadius,
          headPadding: getComputedStyle(head).padding,
          bodyPadding: getComputedStyle(body).padding,
          bodyMaxHeight: Number.parseFloat(bodyStyle.maxHeight),
          bodyOverflowY: bodyStyle.overflowY,
          footPadding: getComputedStyle(foot).padding,
          footBackground: getComputedStyle(foot).backgroundColor,
          titleFontSize: titleStyle.fontSize,
          titleFontWeight: titleStyle.fontWeight,
          viewportHeight: window.innerHeight,
          viewportWidth: window.innerWidth,
          overlay: {
            left: overlayRect.left,
            top: overlayRect.top,
            right: overlayRect.right,
            bottom: overlayRect.bottom,
          },
          hasBodyForm: Boolean(body.querySelector("form")),
          hasFootActions: Boolean(foot.querySelector(".form-actions")),
        };
      })()`,
    );
    assert.ok(Math.abs(dialogLayout.width - 720) <= 1, JSON.stringify(dialogLayout));
    assert.equal(dialogLayout.radius, "14px", JSON.stringify(dialogLayout));
    assert.equal(dialogLayout.headPadding, "14px 18px", JSON.stringify(dialogLayout));
    assert.equal(dialogLayout.bodyPadding, "18px");
    assert.ok(
      Math.abs(dialogLayout.bodyMaxHeight - dialogLayout.viewportHeight * 0.66) <= 1,
      JSON.stringify(dialogLayout),
    );
    assert.equal(dialogLayout.bodyOverflowY, "auto");
    assert.equal(dialogLayout.footPadding, "13px 18px");
    assert.equal(dialogLayout.footBackground, "rgb(250, 251, 252)");
    assert.equal(dialogLayout.titleFontSize, "15px");
    assert.equal(dialogLayout.titleFontWeight, "700");
    assert.ok(
      Math.abs(dialogLayout.overlay.left) <= 1,
      JSON.stringify(dialogLayout),
    );
    assert.ok(
      Math.abs(dialogLayout.overlay.top) <= 1,
      JSON.stringify(dialogLayout),
    );
    assert.ok(
      Math.abs(dialogLayout.overlay.right - dialogLayout.viewportWidth) <= 1,
      JSON.stringify(dialogLayout),
    );
    assert.ok(
      Math.abs(dialogLayout.overlay.bottom - dialogLayout.viewportHeight) <= 1,
      JSON.stringify(dialogLayout),
    );
    assert.equal(dialogLayout.hasBodyForm, true);
    assert.equal(dialogLayout.hasFootActions, true);
    assert.doesNotMatch(
      await evaluate(
        page,
        `document.querySelector(".target-form-dialog").textContent`,
      ),
      /正在读取仓库版本/,
    );
    await fillTargetForm(page, {
      name: "m5-e2e-target",
      repoUrl: "http://invalid.example.com/repo.git",
      subDir: "skills/m5-e2e-target",
      defaultRef: "main",
    });
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    const localError = await waitForDocument(
      page.session,
      `document.querySelector("#target-repoUrl-error")?.textContent.trim()`,
      "field-level repository format error",
    );
    assert.match(localError, /仓库地址格式不正确/);
    assert.match(localError, /HTTPS/);
    assert.equal(
      await evaluate(
        page,
        `Boolean(document.querySelector("[data-testid='target-git-output']"))`,
      ),
      false,
    );
    assert.equal(
      await evaluate(
        page,
        `document.querySelector("input[name='objectName']").value`,
      ),
      "m5-e2e-target",
    );
    assert.equal(
      await evaluate(page, `document.activeElement?.getAttribute("name")`),
      "repoUrl",
    );

    await setInput(
      page,
      "input[name='repoUrl']",
      "https://invalid.example.com/repo.git",
    );
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".server-error")?.textContent.includes("无法访问仓库")`,
      "inline unreachable repository error",
    );
    const remoteOutput = await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='target-git-output']")?.textContent.trim()`,
      "git command output",
    );
    assert.match(remoteOutput, /git ls-remote/);
    assert.match(remoteOutput, /退出码 128/);
    assert.match(remoteOutput, /Could not resolve host/);
    assert.doesNotMatch(remoteOutput, /\/Users\/e2e/);

    await setInput(
      page,
      "input[name='repoUrl']",
      "https://git.example.com/agent-skills.git",
    );
    await setInput(page, "input[name='defaultRef']", "bad-ref");
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    const refError = await waitForDocument(
      page.session,
      `document.querySelector("#target-defaultRef-error")?.textContent.trim()`,
      "missing remote ref error",
    );
    assert.match(refError, /仓库可达，但找不到该 ref/);
    assert.doesNotMatch(
      await evaluate(
        page,
        `document.querySelector(".target-form-dialog .server-error")?.textContent ?? ""`,
      ),
      /检查地址、子目录与基线/,
    );
    assert.match(
      await evaluate(
        page,
        `document.querySelector("[data-testid='target-git-output']")?.textContent ?? ""`,
      ),
      /退出码 2/,
    );
    await clickText(page, ".target-form-dialog button", "取消");

    await evaluate(page, `document.querySelector(".target-create").click()`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".target-form-dialog"))`,
      "create dialog reopened",
    );
    await fillTargetForm(page, {
      name: "m5-e2e-target",
      repoUrl: "https://git.example.com/agent-skills.git",
      subDir: "skills/m5-e2e-target",
      defaultRef: "v2.0.0",
    });
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    await waitForDocument(
      page.session,
      `[...document.querySelectorAll(".object-name")]
        .some((item) => item.textContent.trim() === "m5-e2e-target")`,
      "created target row",
    );
    const enabledChipStyles = await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
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
    assert.equal(enabledChipStyles.kindColor, "rgb(138, 85, 201)");
    assert.notEqual(enabledChipStyles.kindBackground, "rgba(0, 0, 0, 0)");
    assert.equal(enabledChipStyles.stateColor, "rgb(31, 157, 107)");
    assert.notEqual(enabledChipStyles.stateBackground, "rgba(0, 0, 0, 0)");

    const createdRows = await apiJson("/api/evolution/targets", admin.accessToken);
    const created = createdRows.items.find((item) => item.objectName === "m5-e2e-target");
    assert.ok(created);
    assert.equal(created.validationProjectId, "val-m5-e2e");
    assert.equal(created.testProjectId, "test-m5-e2e");
    assert.match(
      await evaluate(
        page,
        `[...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"))
          ?.querySelector('[data-testid="target-project-ids"]')?.textContent ?? ""`,
      ),
      /验证集.*val-m5-e2e.*测试集.*test-m5-e2e/s,
    );

    assert.equal(created.attributionSkillName, null);
    assert.equal(created.attributionPackageId, null);

    await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
        row.querySelector(".edit-target").click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".target-form-dialog")?.textContent.includes("编辑进化对象")`,
      "edit dialog",
    );
    await waitForDocument(page.session,
      `[...document.querySelectorAll("select[aria-label='归因 Skill'] option")]
         .some(option => option.value === ${JSON.stringify(uploaded.id)})`, "uploaded Skill option");
    await evaluate(page, `(() => {
      const select = document.querySelector("select[aria-label='归因 Skill']");
      select.value = ${JSON.stringify(uploaded.id)};
      select.dispatchEvent(new Event("change", { bubbles: true }));
    })()`);
    await setInput(page, "input[name='repoUrl']", "https://git.example.com/agent-skills-updated.git");
    await evaluate(
      page,
      `document.querySelector(".target-form-dialog .el-button--primary").click()`,
    );
    await waitForDocument(
      page.session,
      `[...document.querySelectorAll(".repo-url")]
        .some((item) => item.textContent.includes("agent-skills-updated.git"))`,
      "updated target row",
    );
    const updated = await apiJson("/api/evolution/targets", admin.accessToken);
    assert.equal(updated.items.find(item => item.id === created.id).attributionPackageId, uploaded.id);
    const detail = await apiJson(`${packagesPath}/${uploaded.id}`, admin.accessToken);
    assert.ok(detail.targets.includes("m5-e2e-target"));
    assert.equal(await evaluate(page, `[...document.querySelectorAll(".target-table tbody tr")]
      .find(row => row.textContent.includes("m5-e2e-target"))
      ?.querySelector(".runtime-badge")?.textContent.trim()`), "归因未运行");


    await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
        row.querySelector(".toggle-target").click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
        return row?.textContent.includes("已停用");
      })()`,
      "disabled target row",
    );
    const disabledChipStyles = await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
        const state = getComputedStyle(row.querySelector(".state-chip"));
        return {
          color: state.color,
          background: state.backgroundColor,
        };
      })()`,
    );
    assert.equal(disabledChipStyles.color, "rgb(154, 162, 174)");
    assert.notEqual(disabledChipStyles.background, "rgba(0, 0, 0, 0)");
    const catalog = await apiJson("/api/catalogs/targets", admin.accessToken);
    assert.equal(
      [...catalog.skill, ...catalog.agent].some((item) => item.id === created.id),
      false,
    );

    const runId = await runTool("create", created.id);
    await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
        row.querySelector(".delete-target").click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".el-message-box"))`,
      "delete confirmation",
    );
    assert.match(
      await evaluate(page, `document.querySelector(".el-message-box").textContent`),
      /有进行中 run 时不可删除/,
    );
    await evaluate(
      page,
      `document.querySelector(".el-message-box .el-button--primary").click()`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".operation-error")?.textContent.includes("有进行中 run")`,
      "target in use error",
    );
    await runTool("complete", runId);

    await evaluate(
      page,
      `(() => {
        const row = [...document.querySelectorAll(".target-table tbody tr")]
          .find((item) => item.textContent.includes("m5-e2e-target"));
        row.querySelector(".delete-target").click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".el-message-box"))`,
      "second delete confirmation",
    );
    await evaluate(
      page,
      `document.querySelector(".el-message-box .el-button--primary").click()`,
    );
    await waitForDocument(
      page.session,
      `![...document.querySelectorAll(".object-name")]
        .some((item) => item.textContent.trim() === "m5-e2e-target")`,
      "target deleted",
    );

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const compactLayout = await evaluate(
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
          paddingLeft: Number.parseFloat(style.paddingLeft),
          paddingRight: Number.parseFloat(style.paddingRight),
          left: rect.left,
          right: rect.right,
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
        };
      })()`,
    );
    assert.ok(Math.abs(compactLayout.width - 390) <= 1, JSON.stringify(compactLayout));
    assert.ok(Math.abs(compactLayout.contentWidth - 342) <= 1, JSON.stringify(compactLayout));
    assert.equal(compactLayout.paddingLeft, 24);
    assert.equal(compactLayout.paddingRight, 24);
    assert.ok(Math.abs(compactLayout.left) <= 1, JSON.stringify(compactLayout));
    assert.ok(Math.abs(compactLayout.right - 390) <= 1, JSON.stringify(compactLayout));
    assert.equal(compactLayout.pageScrollWidth, compactLayout.pageClientWidth);
    await evaluate(page, `document.querySelector(".target-create").click()`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".target-form-dialog"))`,
      "mobile target dialog",
    );
    const mobileDialog = await evaluate(
      page,
      `(() => {
        const root = document.querySelector(".target-form-dialog");
        const dialog = root.matches(".el-dialog")
          ? root
          : root.querySelector(".el-dialog");
        const rect = dialog.getBoundingClientRect();
        return {
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
          dialogLeft: rect.left,
          dialogRight: rect.right,
          dialogWidth: rect.width,
        };
      })()`,
    );
    assert.equal(mobileDialog.pageScrollWidth, mobileDialog.pageClientWidth);
    assert.ok(Math.abs(mobileDialog.dialogWidth - 358) <= 1, JSON.stringify(mobileDialog));
    assert.ok(Math.abs(mobileDialog.dialogLeft - 16) <= 1, JSON.stringify(mobileDialog));
    assert.ok(Math.abs(mobileDialog.dialogRight - 374) <= 1, JSON.stringify(mobileDialog));
    await clickText(page, ".target-form-dialog button", "取消");

    await installCookie(page, memberAuth.cookie);
    await page.session.send("Page.reload");
    await waitForDocument(
      page.session,
      `document.querySelector("h1")?.textContent === "进化对象配置" &&
        !document.querySelector(".target-create") &&
        Boolean(document.querySelector(".target-table tbody tr")) &&
        document.querySelector(".target-table thead").textContent.includes("归因 Skill")`,
      "member target page",
    );
    assert.equal(await evaluate(page, `Boolean(document.querySelector(".target-create"))`), false);
    assert.equal(await evaluate(page, `Boolean(document.querySelector(".target-table tbody tr"))`), true);
    assert.equal(await evaluate(page, `Boolean(document.querySelector(".edit-target, .delete-target, .toggle-target"))`), false);
    assert.equal(await evaluate(page, `Boolean(document.querySelector(".target-form-dialog"))`), false);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobile = await waitForDocument(
      page.session,
      `({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        tableScrollWidth: (() => {
          const scroller = document.querySelector(".target-table-scroll");
          return scroller?.scrollWidth ?? 0;
        })(),
        tableClientWidth: (() => {
          const scroller = document.querySelector(".target-table-scroll");
          return scroller?.clientWidth ?? 0;
        })(),
      })`,
      "target config mobile layout",
    );
    assert.equal(mobile.scrollWidth, mobile.clientWidth);
    assert.ok(mobile.tableClientWidth > 0, JSON.stringify(mobile));
    assert.ok(
      mobile.tableScrollWidth > mobile.tableClientWidth,
      JSON.stringify(mobile),
    );

    await evaluate(page, `history.pushState({}, "", "${workspaceBase}/evolution");
      window.dispatchEvent(new PopStateEvent("popstate"));`);
    try {
      await waitForDocument(
        page.session,
        `document.querySelector(".target-config-entry")
          ?.getAttribute("aria-label") === "配置进化对象"`,
        "target config entry",
      );
    } catch (error) {
      const diagnostics = await evaluate(
        page,
        `(() => ({
          url: location.href,
          body: document.body.textContent?.trim().slice(0, 500) ?? "",
          hasShell: Boolean(document.querySelector(".shell")),
          hasLogin: Boolean(document.querySelector("[data-testid='login-submit']")),
          hasEntry: Boolean(document.querySelector(".target-config-entry")),
        }))()`,
      ).catch((diagnosticError) => ({
        diagnosticError:
          diagnosticError instanceof Error
            ? diagnosticError.message
            : String(diagnosticError),
      }));
      throw new Error(
        `${error instanceof Error ? error.message : String(error)}\n${JSON.stringify(
          { diagnostics, violations },
          null,
          2,
        )}`,
      );
    }
    assert.equal(
      await evaluate(page, `Boolean(document.querySelector(".target-config-entry"))`),
      true,
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='open-launch-wizard']")?.click()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='wizard-target-config-link']"))`,
      "wizard hint link",
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-target-config-link']")?.click()`,
    );
    await waitForTargetConfigPage(
      page,
      "wizard hint link target config navigation",
      violations,
    );
    assert.equal(
      await evaluate(page, "location.pathname"),
      `${workspaceBase}/evolution/targets`,
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='target-config-back']")?.click()`,
    );
    await waitForDocument(
      page.session,
      `location.pathname === "${workspaceBase}/evolution" &&
        document.querySelector("h1")?.textContent === "自进化"`,
      "target config back navigation",
    );
    assert.deepEqual(violations, []);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
