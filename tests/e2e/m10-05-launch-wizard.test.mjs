import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
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
const initialPassword = "m10-wizard-initial-password";
const finalPassword = "m10-wizard-final-password";
const secret = "m10-wizard-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
const evolutionPath = `${ws}/evolution`;
let api;
let web;
let dataDir;
let screenshotDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
const keepScreenshots = process.env.HE_KEEP_SCREENSHOTS === "1";
const longSessionTitle =
  "You are an autonomous software engineer working in the repository at /testbed. " +
  "Solve the issue by editing the repository and running the test suite until it passes.";

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
  if (screenshotDir && !keepScreenshots) {
    await rm(screenshotDir, { recursive: true, force: true });
  }
}

async function loginCookie() {
  let password = initialPassword;
  let response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password }),
  });
  if (response.status === 401) {
    password = finalPassword;
    response = await fetch(`${baseUrl}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: "admin", password }),
    });
  }
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);
  if (password === initialPassword) {
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
  }
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

async function click(page, testId) {
  await evaluate(
    page,
    `document.querySelector("[data-testid='${testId}']").click()`,
  );
}

async function setValue(page, testId, value) {
  await evaluate(
    page,
    `(() => {
      const input = document.querySelector("[data-testid='${testId}']");
      input.value = ${JSON.stringify(value)};
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    })()`,
  );
}

async function selectOption(page, testId, label) {
  await evaluate(
    page,
    `(() => {
      const select = document.querySelector("[data-testid='${testId}']");
      const option = [...select.options].find((item) => item.text === ${JSON.stringify(label)});
      if (!option) throw new Error("missing option: " + ${JSON.stringify(label)});
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    })()`,
  );
}

async function openAndFillWizard(page) {
  await click(page, "open-launch-wizard");
  await waitForDocument(
    page.session,
    `Boolean(document.querySelector("[data-testid='launch-wizard']"))`,
    "wizard modal",
  );
  await waitForDocument(
    page.session,
    `[...document.querySelectorAll("[data-testid='wizard-target'] option")]
      .some((option) => option.text === "synthetic-review")`,
    "configured target option",
  );
  await selectOption(page, "wizard-target", "synthetic-review");
  await click(page, "wizard-version-toggle");
  await waitForDocument(
    page.session,
    `Boolean(document.querySelector("[data-testid='wizard-version-menu']"))`,
    "target version suggestions",
  );
  await setValue(page, "wizard-version", "synthetic-1");
  await setValue(page, "wizard-from", "2026-10-20");
  await setValue(page, "wizard-to", "2026-10-25");
}

async function reachStep4(page) {
  await openAndFillWizard(page);
  await click(page, "wizard-next");
  await waitForDocument(
    page.session,
    `document.querySelector("[data-testid='wizard-session-table']")?.textContent.includes("You are an autonomous software engineer")`,
    "associated Session row",
  );
  await click(page, "wizard-step2-next");
  await waitForDocument(
    page.session,
    `document.querySelector("[data-testid='wizard-potential-table']")?.textContent.includes("badc")`,
    "potential row",
  );
  await click(page, "wizard-step3-next");
  await waitForDocument(
    page.session,
    `Boolean(document.querySelector("[data-testid='wizard-attribution-stats']"))`,
    "attribution preview",
  );
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m10-wizard-data-"));
  screenshotDir = await mkdtemp(
    path.join(tmpdir(), "harness-m10-wizard-screenshots-"),
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

  const originDir = path.join(dataDir, "skill-origin.git");
  const workDir = path.join(dataDir, "skill-work");
  const git = (args, cwd) => {
    const result = spawnSync("git", args, { cwd, encoding: "utf8" });
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  };
  git(["init", "--bare", "-b", "main", originDir], root);
  git(["clone", originDir, workDir], root);
  await mkdir(path.join(workDir, "skills/synthetic-review"), {
    recursive: true,
  });
  await writeFile(
    path.join(workDir, "skills/synthetic-review/SKILL.md"),
    "# synthetic-review\n",
  );
  git(["add", "."], workDir);
  git(
    [
      "-c",
      "user.name=Smoke",
      "-c",
      "user.email=smoke@example.invalid",
      "commit",
      "-m",
      "seed synthetic-review",
    ],
    workDir,
  );
  git(["tag", "synthetic-1"], workDir);
  git(["push", "origin", "main", "--tags"], workDir);

  const seed = spawn(
    python,
    [
      path.join(root, "tests/e2e/support/m10_05_seed.py"),
      "--data-dir",
      dataDir,
      "--repo-url",
      originDir,
      "--long-title",
    ],
    {
      cwd: root,
      env,
      shell: process.platform === "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let seedOutput = "";
  capture(seed, (chunk) => {
    seedOutput += chunk;
  });
  const seedExit = await new Promise((resolve) => seed.once("exit", resolve));
  assert.equal(seedExit, 0, seedOutput);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(
    python,
    [path.join(root, "tests/e2e/support/m10_05_launch_server.py")],
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

test("m10-05 four-step wizard previews and exits into both run routes", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installCookie(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 1100,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${evolutionPath}`,
    });
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("当前没有正在执行的自进化")`,
      "empty run list",
    );

    await openAndFillWizard(page);
    await screenshot(page, "01-wizard-step1.png");
    await click(page, "wizard-next");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='wizard-session-table']")?.textContent.includes("You are an autonomous software engineer")`,
      "associated Session row",
    );
    const step2 = await evaluate(
      page,
      `document.querySelector(".wz-stats")?.textContent`,
    );
    assert.match(step2, /对象出现 · 已关联/);

    const sessionLayout = await evaluate(
      page,
      `(() => {
        const table = document.querySelector("[data-testid='wizard-session-table']");
        const scroll = table.closest(".rep-scroll");
        const title = document.querySelector("[data-testid='wizard-session-title']");
        const bounds = scroll.getBoundingClientRect();
        return {
          headers: [...table.querySelectorAll("thead th")].map((th) => {
            const rect = th.getBoundingClientRect();
            return { text: th.textContent.trim(), left: rect.left, right: rect.right };
          }),
          bounds: { left: bounds.left, right: bounds.right },
          overflow: scroll.scrollWidth - scroll.clientWidth,
          titleText: title.textContent,
          title: title.getAttribute("title"),
          clipped: title.scrollWidth > title.clientWidth,
          sessionId: table.querySelector(".cell-sub").textContent,
        };
      })()`,
    );
    assert.equal(sessionLayout.headers.length, 4);
    for (const header of sessionLayout.headers) {
      assert.ok(
        header.left >= sessionLayout.bounds.left - 1,
        `${header.text} starts inside the table viewport`,
      );
      assert.ok(
        header.right <= sessionLayout.bounds.right + 1,
        `${header.text} ends inside the table viewport`,
      );
    }
    assert.ok(
      sessionLayout.overflow <= 1,
      `table overflows by ${sessionLayout.overflow}px`,
    );
    assert.equal(sessionLayout.titleText, longSessionTitle.slice(0, 120));
    assert.equal(sessionLayout.title, longSessionTitle);
    assert.ok(sessionLayout.clipped, "long Session title is visually clamped");
    assert.match(sessionLayout.sessionId, /^#.{4}….{4}$/);

    await screenshot(page, "02-wizard-step2.png");

    await click(page, "wizard-step2-next");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='wizard-potential-table']")?.textContent.includes("self 上报")`,
      "potential row",
    );
    const step3 = await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-potential-table']")?.textContent`,
    );
    assert.match(step3, /badc/);
    await screenshot(page, "03-wizard-step3.png");

    await click(page, "wizard-step3-next");
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='wizard-attribution-stats']"))`,
      "attribution preview",
    );
    const step4 = await evaluate(
      page,
      `document.querySelector("[data-testid='wizard-attribution-stats']")?.textContent`,
    );
    assert.match(step4, /潜在 bad case/);
    assert.match(step4, /复用缓存/);
    await screenshot(page, "04-wizard-step4.png");

    await click(page, "wizard-cluster");
    await waitForDocument(
      page.session,
      `location.pathname.includes("/evolution/cluster/")`,
      "cluster preview route",
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='evolution-cluster-preview']"))`,
      "cluster preview page",
    );
    await screenshot(page, "05-cluster-preview.png");

    await evaluate(
      page,
      `[...document.querySelectorAll("button")]
        .find((button) => button.textContent.includes("返回运行列表")).click()`,
    );
    try {
      await waitForDocument(
        page.session,
        `location.pathname === ${JSON.stringify(evolutionPath)} &&
          Boolean(document.querySelector("[data-testid='open-launch-wizard']"))`,
        "run list after cluster launch",
      );
    } catch (error) {
      const url = await evaluate(page, "location.href");
      const body = await evaluate(page, "document.body.innerText.slice(0, 600)");
      throw new Error(
        `${error.message}; url=${url}; body=${body}; api=${apiLogs.slice(-1500)}; web=${webLogs.slice(-500)}`,
      );
    }
    await reachStep4(page);
    await click(page, "wizard-start");
    await waitForDocument(
      page.session,
      `location.pathname.includes("/evolution/runs/")`,
      "full run route",
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='evolution-run-detail']"))`,
      "run detail page",
    );
    await screenshot(page, "06-run-detail.png");

    assert.deepEqual(violations, []);
    console.log(`screenshots: ${screenshotDir}`);
  } finally {
    page.close();
  }
});

test("m10-05 launch wizard rejects a ref git cannot find", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: (entry) => entry.text.includes("Failed to load resource"),
  });
  try {
    await installCookie(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${evolutionPath}`,
    });
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("当前没有正在执行的自进化") ||
        Boolean(document.querySelector("[data-testid='open-launch-wizard']"))`,
      "evolution page",
    );
    await openAndFillWizard(page);
    await setValue(page, "wizard-version", "feature/does-not-exist");
    await click(page, "wizard-next");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='wizard-version-error']")?.textContent.includes("该版本在仓库中不存在")`,
      "missing ref error",
    );
    await screenshot(page, "07-wizard-missing-ref.png");
    assert.deepEqual(violations, []);
  } finally {
    page.close();
  }
});
