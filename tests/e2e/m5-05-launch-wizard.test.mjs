import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
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
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m5-launch-initial-password";
const finalPassword = "m5-launch-final-password";
const secret = "m5-launch-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let screenshotDir;
let baseUrl;
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
  if (screenshotDir) await rm(screenshotDir, { recursive: true, force: true });
}

async function loginCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
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
      oldPassword: initialPassword,
      newPassword: finalPassword,
    }),
  });
  assert.equal(changed.status, 204);
  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  assert.equal(refreshed.status, 200);
  return refreshed.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
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
    throw new Error(
      result.exceptionDetails.exception?.description ??
        result.exceptionDetails.text,
    );
  }
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

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m5-launch-e2e-"));
  screenshotDir = await mkdtemp(
    path.join(tmpdir(), "harness-m5-launch-screenshots-"),
  );
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
    PYTHONPATH: path.join(root, "apps/api"),
  };
  const setup = spawn(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    shell: process.platform === "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  let setupOutput = "";
  capture(setup, (chunk) => {
    setupOutput += chunk;
  });
  const setupExit = await new Promise((resolve) => setup.once("exit", resolve));
  assert.equal(setupExit, 0, setupOutput);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(
    python,
    [path.join(root, "tests/e2e/support/m5_launch_server.py")],
    {
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
    },
  );
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

test("m5-05 launch wizard starts a cluster-only run and lands on its preview", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: (entry) =>
      entry.source === "network" &&
      entry.url?.endsWith("/api/evolution/probes/query") &&
      /status of 409/.test(entry.text),
  });
  try {
    await installCookie(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution` });
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("当前没有正在执行的自进化")`,
      "empty run list",
    );

    await evaluate(
      page,
      `document.querySelector("[data-testid='open-launch-wizard']").click()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='launch-wizard']"))`,
      "wizard modal",
    );

    const dialogSemantics = await evaluate(
      page,
      `(() => {
        const dialog = document.querySelector("[data-testid='launch-wizard']");
        const titleId = dialog.getAttribute("aria-labelledby") ?? "";
        return {
          role: dialog.getAttribute("role"),
          modal: dialog.getAttribute("aria-modal"),
          title: titleId
            ? (document.getElementById(titleId)?.textContent ?? "").trim()
            : "",
        };
      })()`,
    );
    assert.equal(dialogSemantics.role, "dialog");
    assert.equal(dialogSemantics.modal, "true");
    assert.equal(dialogSemantics.title, "启动自进化");

    await page.session.send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: "Escape",
      code: "Escape",
      windowsVirtualKeyCode: 27,
    });
    await page.session.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: "Escape",
      code: "Escape",
      windowsVirtualKeyCode: 27,
    });
    await waitForDocument(
      page.session,
      `!document.querySelector("[data-testid='launch-wizard']")`,
      "wizard closed by Escape",
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='open-launch-wizard']").click()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='launch-wizard']"))`,
      "wizard reopened",
    );

    await waitForDocument(
      page.session,
      `[...document.querySelectorAll("[data-testid='wizard-target'] option")]
        .some((option) => option.text === "synthetic-review")`,
      "configured target options",
    );

    await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-next']").click()`,
    );
    await waitForDocument(
      page.session,
      `["wizard-target-error", "wizard-version-error", "wizard-from-error", "wizard-to-error"]
        .every((id) => document.getElementById(id)?.classList.contains("field-error")) &&
        [...document.querySelectorAll("[data-testid='wizard-target'], [data-testid='wizard-version'], [data-testid='wizard-from'], [data-testid='wizard-to']")]
          .every((control) => control.getAttribute("aria-invalid") === "true")`,
      "field-level validation errors",
    );
    const validation = await evaluate(
      page,
      `(() => ({
        next: document.querySelector("[data-testid='wizard-next']").disabled,
        stats: Boolean(document.querySelector(".wz-stats")),
        target: document.getElementById("wizard-target-error")?.textContent,
        version: document.getElementById("wizard-version-error")?.textContent,
        from: document.getElementById("wizard-from-error")?.textContent,
        to: document.getElementById("wizard-to-error")?.textContent,
      }))()`,
    );
    assert.equal(validation.next, false);
    assert.equal(validation.stats, false);
    assert.deepEqual(
      [
        validation.target?.trim(),
        validation.version?.trim(),
        validation.from,
        validation.to,
      ],
      ["请选择进化对象", "请选择版本", "请选择开始时间", "请选择结束时间"],
    );
    await screenshot(page, "00-wizard-field-errors.png");

    const step1 = await evaluate(
      page,
      `(() => {
        const select = document.querySelector("[data-testid='wizard-target']");
        const options = [...select.options].map((option) => option.text);
        return { options };
      })()`,
    );
    assert.ok(
      step1.options.includes("synthetic-review"),
      `wizard should list configured targets only: ${JSON.stringify(step1.options)}`,
    );
    assert.ok(
      !step1.options.includes("Explore"),
      "unconfigured objects must stay out of the selector",
    );

    await evaluate(
      page,
      `(() => {
        const target = document.querySelector("[data-testid='wizard-target']");
        const option = [...target.options].find(
          (item) => item.text === "synthetic-review",
        );
        target.value = option.value;
        target.dispatchEvent(new Event("change", { bubbles: true }));
      })()`,
    );
    await waitForDocument(
      page.session,
      `[...document.querySelector("[data-testid='wizard-version']").options]
        .some((option) => option.text === "synthetic-1")`,
      "version options",
    );
    await evaluate(
      page,
      `(() => {
        const version = document.querySelector("[data-testid='wizard-version']");
        const option = [...version.options].find(
          (item) => item.text === "synthetic-1",
        );
        version.value = option.value;
        version.dispatchEvent(new Event("change", { bubbles: true }));
        const setDate = (testId, value) => {
          const input = document.querySelector("[data-testid='" + testId + "']");
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        };
        setDate("wizard-from", "2026-10-01");
        setDate("wizard-to", "2026-09-30");
      })()`,
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-next']").click()`,
    );
    await waitForDocument(
      page.session,
      `document.getElementById("wizard-from-error")?.textContent === "起始时间不能晚于结束时间" &&
        document.getElementById("wizard-to-error")?.textContent === "起始时间不能晚于结束时间" &&
        !document.querySelector(".wz-stats")`,
      "reversed window validation",
    );
    await evaluate(
      page,
      `(() => {
        const setDate = (testId, value) => {
          const input = document.querySelector("[data-testid='" + testId + "']");
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        };
        setDate("wizard-to", "2026-10-31");
      })()`,
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-next']").click()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".wz-stats")) &&
        document.body.textContent.includes("「是问题」进入聚类")`,
      "hit statistics frame",
    );
    const step2 = await evaluate(
      page,
      `(() => ({
        strip: document.querySelector(".wz-condstrip")?.textContent ?? "",
        table: document.querySelector("table.rep")?.textContent ?? "",
        footer: document.querySelector(".modal-foot")?.textContent ?? "",
      }))()`,
    );
    assert.ok(step2.strip.includes("skill:synthetic-review@synthetic-1"));
    assert.ok(step2.strip.includes("2026-10-01"));
    assert.ok(step2.strip.includes("2026-10-31"));
    assert.ok(step2.table.includes("prob…0002"));
    assert.ok(step2.table.includes("badc…0003"));
    assert.ok(step2.table.includes("是问题-错误"));
    assert.ok(step2.footer.includes("启动问题聚类分析"));

    await screenshot(page, "01-wizard-step2.png");
    await evaluate(
      page,
      `([...document.querySelectorAll(".wz-condstrip button")]
        .find((button) => button.textContent.includes("修改条件")) ?? document.querySelector(".wz-condstrip button"))
        .click()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='wizard-from']"))`,
      "wizard returned to step 1",
    );
    await evaluate(
      page,
      `(() => {
        const setDate = (testId, value) => {
          const input = document.querySelector("[data-testid='" + testId + "']");
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        };
        setDate("wizard-from", "2026-01-01");
        setDate("wizard-to", "2026-01-31");
        document.querySelector("[data-testid='wizard-next']").click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='wizard-empty']")) &&
        document.querySelector("[data-testid='wizard-empty']").textContent.includes("未找到匹配的问题报告")`,
      "zero-match empty state",
    );
    const emptyState = await evaluate(
      page,
      `(() => ({
        strip: document.querySelector(".wz-condstrip")?.textContent ?? "",
        cluster: document.querySelector("[data-testid='wizard-cluster']").disabled,
        start: document.querySelector("[data-testid='wizard-start']").disabled,
      }))()`,
    );
    assert.ok(emptyState.strip.includes("2026-01-01"));
    assert.equal(emptyState.cluster, true);
    assert.equal(emptyState.start, true);
    await screenshot(page, "02-wizard-empty-state.png");
    await evaluate(
      page,
      `([...document.querySelectorAll(".wz-condstrip button")]
        .find((button) => button.textContent.includes("修改条件")) ?? document.querySelector(".wz-condstrip button"))
        .click()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='wizard-from']"))`,
      "wizard returned from empty state",
    );
    await evaluate(
      page,
      `(() => {
        const setDate = (testId, value) => {
          const input = document.querySelector("[data-testid='" + testId + "']");
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        };
        setDate("wizard-from", "2026-10-01");
        setDate("wizard-to", "2026-10-31");
        document.querySelector("[data-testid='wizard-next']").click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".wz-stats")) &&
        document.body.textContent.includes("「是问题」进入聚类")`,
      "hit statistics restored",
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-cluster']").click()`,
    );
    await waitForDocument(
      page.session,
      `location.pathname.startsWith("/evolution/cluster/") &&
        Boolean(document.querySelector("[data-testid='cluster-status']")) &&
        document.body.textContent.includes("准备中")`,
      "cluster preview preparing page",
    );
    const landing = await evaluate(
      page,
      `(() => ({
        path: location.pathname,
        banner: document.querySelector(".banner")?.textContent ?? "",
        status: document.querySelector("[data-testid='cluster-status']")?.textContent ?? "",
        info: document.querySelector(".info-panel")?.textContent ?? "",
      }))()`,
    );
    assert.ok(landing.path.startsWith("/evolution/cluster/"));
    assert.ok(landing.banner.includes("仅聚类分析"));
    assert.ok(landing.status.includes("准备中"));
    assert.ok(landing.info.includes("2026-10-01"));
    assert.ok(landing.info.includes("2026-10-31"));
    assert.ok(!landing.info.includes("— ~ —"));
    await screenshot(page, "03-cluster-preparing.png");

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
