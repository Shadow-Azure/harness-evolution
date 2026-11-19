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
const initialPassword = "m11-05-v2-initial-password";
const finalPassword = "m11-05-v2-final-password";
const secret = "m11-05-v2-cross-stack-signing-secret-with-sufficient-length";
const sessionId = "10000000-0000-4000-8000-000000000003";
const screenshotDir = process.env.M11_05_SCREENSHOT_DIR ?? "";
let labId = "";
let labPath = "";
const defaultPath = "/workspaces/ws-default";
const ingestCases = [
  {
    badCaseId: "badcase-m11-05-self-1",
    badCaseType: "self",
    objectName: "synthetic-review",
    objectType: "skill",
    title: "技能漏掉目标文件",
    reason: "检查清单技能未输出目标文件，导致结果无法复核。",
    createdAt: "2026-10-22T12:01:00+08:00",
  },
  {
    badCaseId: "badcase-m11-05-self-2",
    badCaseType: "self",
    objectName: "synthetic-review",
    objectType: "skill",
    title: "技能输出缺少约束",
    reason: "技能输出没有引用目标文件约束，复核时无法定位来源。",
    createdAt: "2026-10-22T12:02:00+08:00",
  },
  {
    badCaseId: "badcase-m11-05-discovery-1",
    badCaseType: "self",
    objectName: "review-workflow",
    objectType: "agent",
    title: "工作流在汇总前退出",
    reason: "工作流在汇总步骤之前退出，报告缺少最终结论。",
    createdAt: "2026-10-22T12:03:00+08:00",
  },
];
let api;
let web;
let dataDir;
let gitConfigPath;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminToken = "";
let workspaceId = "";
let credential = "";
let targetId = "";

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

for (const [signal, exitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  process.once(signal, () => {
    void cleanup().finally(() => process.exit(exitCode));
  });
}

async function apiRequest(pathname, init = {}, token = adminToken) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...init,
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      "content-type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const text = await response.text();
  return {
    status: response.status,
    body: text ? JSON.parse(text) : null,
    headers: response.headers,
  };
}

async function requireApi(pathname, init = {}) {
  const result = await apiRequest(pathname, init);
  assert.ok(
    result.status >= 200 && result.status < 300,
    `${pathname} returned ${result.status}: ${JSON.stringify(result.body)}`,
  );
  return result;
}

async function loginApi() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
  });
  assert.equal(login.status, 200);
  const body = await login.json();
  const cookie = login.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${body.accessToken}`,
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
    headers: { cookie: `refresh_token=${cookie}` },
  });
  assert.equal(refreshed.status, 200);
  const access = await refreshed.json();
  adminToken = access.accessToken;
  return access;
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

async function click(page, selector) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true, view: window }),
      );
      return true;
    })()`,
    `click ${selector}`,
  );
}

async function setControl(page, selector, value) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      ).set;
      setter.call(element, ${JSON.stringify(value)});
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return element.value === ${JSON.stringify(value)};
    })()`,
    `set ${selector}`,
  );
}

async function selectOption(page, selector, label) {
  await waitForDocument(
    page.session,
    `(() => {
      const select = document.querySelector(${JSON.stringify(selector)});
      if (!select) return null;
      const option = [...select.options].find((item) => item.text === ${JSON.stringify(label)});
      if (!option) return false;
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      return select.value === option.value;
    })()`,
    `select ${selector}=${label}`,
  );
}

async function screenshot(page, name, full = true) {
  if (!screenshotDir) return;
  await mkdir(screenshotDir, { recursive: true });
  if (full) {
    const contentHeight = await evaluate(
      page,
      `Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
        document.querySelector("[data-testid='overview-page']")?.scrollHeight ?? 0,
      )`,
    );
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: Math.max(980, Number(contentHeight) + 60),
      deviceScaleFactor: 1,
      mobile: false,
    });
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
  });
  await writeFile(
    path.join(screenshotDir, name),
    Buffer.from(result.data, "base64"),
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 980,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function openPickerAndSwitch(page, workspace) {
  await waitForDocument(
    page.session,
    `(() => {
      const picker = document.querySelector("[data-testid='workspace-picker']");
      if (!picker) return null;
      picker.open = true;
      const option = document.querySelector(
        ${JSON.stringify(`[data-testid='workspace-option-${workspace}']`)},
      );
      if (!option) return false;
      option.click();
      return true;
    })()`,
    `workspace option ${workspace}`,
  );
}

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource")
  );
}


async function pollRun(runId) {
  const deadline = Date.now() + 40_000;
  let last = null;
  while (Date.now() < deadline) {
    const response = await requireApi(`/api/workspaces/${workspaceId}/evolution/runs`);
    const cards = [...(response.body.running ?? []), ...(response.body.history ?? [])];
    const card = cards.find((item) => item.runId === runId);
    if (card) {
      last = card;
      if (card.status !== "preparing" && card.status !== "running") return card;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`run ${runId} did not settle: ${JSON.stringify(last)}`);
}

async function ingestAll() {
  for (const [index, item] of ingestCases.entries()) {
    const response = await fetch(`${baseUrl}/api/workspaces/${workspaceId}/bad-cases`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${credential}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        badCaseId: item.badCaseId,
        sessionId,
        badCaseType: item.badCaseType,
        objectName: item.objectName,
        objectType: item.objectType,
        objectVersion: "synthetic-1",
        title: item.title,
        reason: item.reason,
        source: "Explore",
        createdAt: item.createdAt,
      }),
    });
    const text = await response.text();
    assert.equal(response.status, 201, `ingest ${index} failed: ${text}`);
    const body = JSON.parse(text);
    assert.equal(body.workspaceUsed, index + 1);
    assert.equal(body.badCaseId, item.badCaseId);
  }

  const repeat = await fetch(`${baseUrl}/api/workspaces/${workspaceId}/bad-cases`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${credential}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      badCaseId: ingestCases[0].badCaseId,
      sessionId,
      badCaseType: ingestCases[0].badCaseType,
      objectName: ingestCases[0].objectName,
      objectType: "skill",
      objectVersion: "synthetic-1",
      title: "幂等重报后的标题",
      reason: "同一个 badCaseId 重报时只替换上游字段，不增加额度。",
      source: "Explore",
      createdAt: ingestCases[0].createdAt,
    }),
  });
  assert.equal(repeat.status, 200);
  assert.equal((await repeat.json()).workspaceUsed, 3);
  assert.equal(repeat.headers.get("x-he-workspace-used"), "3");

  const overflow = await fetch(`${baseUrl}/api/workspaces/${workspaceId}/bad-cases`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${credential}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      badCaseId: "badcase-m11-05-over-quota",
      sessionId,
      badCaseType: "self",
      objectName: "synthetic-review",
      objectType: "skill",
      objectVersion: "synthetic-1",
      title: "额度外的新 case",
      reason: "额度已满时必须拒绝且旧数据不丢。",
      source: "Explore",
      createdAt: "2026-10-22T12:04:00+08:00",
    }),
  });
  assert.equal(overflow.status, 409);
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m11-05-e2e-"));
  gitConfigPath = path.join(dataDir, "gitconfig");
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_LOGIN_RATE_LIMIT: "100",
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
    GIT_CONFIG_GLOBAL: gitConfigPath,
  };
  const seed = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    encoding: "utf8",
  });
  assert.equal(seed.status, 0, seed.stderr || seed.stdout);

  const targetSeed = spawnSync(
    python,
    [path.join(root, "tests/e2e/support/m10_05_seed.py"), "--data-dir", dataDir],
    { cwd: root, env, encoding: "utf8" },
  );
  assert.equal(targetSeed.status, 0, targetSeed.stderr || targetSeed.stdout);

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
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);

  await loginApi();
  const me = await requireApi("/api/auth/session");
  assert.ok(me.body.user.id);

  const workspace = await requireApi("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({
      name: "M11-05 验收空间",
      mark: "M1105",
      quota: 3,
      spaceAdminIds: [me.body.user.id],
    }),
  });
  workspaceId = workspace.body.id;
  labId = workspaceId;
  labPath = `/workspaces/${labId}`;

  const created = await requireApi(`/api/workspaces/${workspaceId}/credentials`, {
    method: "POST",
  });
  credential = created.body.credential;
  assert.match(credential, /^whk_/);

  // The target content resolver reads SKILL.md at the selected tag. Seed a real
  // local mirror so the smoke test covers tag -> body hash instead of a fake
  // unreachable repository.
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
      "user.name=M11-05",
      "-c",
      "user.email=m11-05@example.invalid",
      "commit",
      "-m",
      "seed synthetic-review",
    ],
    workDir,
  );
  git(["tag", "synthetic-1"], workDir);
  git(["tag", "main"], workDir);
  git(["push", "origin", "refs/heads/main:refs/heads/main", "--tags"], workDir);
  await writeFile(
    gitConfigPath,
    `[url "file://${originDir}"]\n\tinsteadOf = https://example.test/skills.git\n` +
      `[url "file://${originDir}"]\n\tinsteadOf = https://example.invalid/example/skills.git\n`,
  );

  const target = await requireApi(
    `/api/workspaces/${workspaceId}/evolution/targets`,
    {
      method: "POST",
      body: JSON.stringify({
        objectType: "skill",
        objectName: "synthetic-review",
        repoUrl: "https://example.test/skills.git",
        subDir: "skills/synthetic-review",
        defaultRef: "synthetic-1",
        validationProjectId: "m11-05-validation",
        testProjectId: "m11-05-test",
        enabled: true,
      }),
    },
  );
  targetId = target.body.id;
  assert.ok(targetId);
});

after(cleanup);

test("m11-05 v2 cross-stack smoke walks auth, workspace, ingest, overview, sessions, error detail, wizard and run", async () => {
  await ingestAll();

  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: expectedLogEntry,
  });
  try {
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 980,
      deviceScaleFactor: 1,
      mobile: false,
    });

    // 1. Anonymous access to a workspace route hands off to the login form.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/overview`,
    });
    const loginCard = await waitForDocument(
      page.session,
      `(() => {
        if (location.pathname !== "/login") return null;
        const username = document.querySelector('input[name="username"]');
        const password = document.querySelector('input[name="password"]');
        if (!username || !password) return null;
        return {
          redirect: new URLSearchParams(location.search).get("redirect"),
          hasTopbar: Boolean(document.querySelector(".topbar")),
        };
      })()`,
      "login handoff",
    );
    assert.equal(loginCard.redirect, `${labPath}/overview`);
    assert.equal(loginCard.hasTopbar, false);
    await screenshot(page, "01-login.png", false);

    // 2. Real login form submission with the rotated password.
    await setControl(page, 'input[name="username"]', "admin");
    await setControl(page, 'input[name="password"]', finalPassword);
    await evaluate(page, `document.querySelector("form").requestSubmit(); true`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".shell")) &&
       Boolean(document.querySelector("[data-testid='current-workspace']"))`,
      "authenticated shell after login",
    );

    // 3. Ingest tab exposes the workspace-scoped endpoint and credential table.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/admin?tab=ingest`,
    });
    const ingestTab = await waitForDocument(
      page.session,
      `(() => {
        const tab = document.querySelector("[data-testid='ingest-tab']");
        if (!tab) return null;
        const endpoint = document.querySelector("[data-testid='ingest-endpoint']")?.textContent?.trim();
        const rows = document.querySelectorAll("[data-testid^='credential-row-']").length;
        if (!endpoint || rows < 1) return null;
        return { endpoint, rows };
      })()`,
      "ingest tab",
    );
    assert.match(ingestTab.endpoint, new RegExp(`/api/workspaces/${workspaceId}/bad-cases$`));
    assert.ok(ingestTab.rows >= 1, JSON.stringify(ingestTab));
    await screenshot(page, "02-lab-admin-ingest.png");

    // 4. The bad-case overview reflects the three ingested reports.
    await page.session.send("Page.navigate", { url: `${baseUrl}${labPath}/overview` });
    const overview = await waitForDocument(
      page.session,
      `(() => {
        const pageRoot = document.querySelector("[data-testid='overview-page']");
        if (!pageRoot) return null;
        const stat = pageRoot.querySelector("[data-testid='ov-stat-badcases'] b")?.textContent?.trim();
        if (stat !== "3") return null;
        return { stat };
      })()`,
      "workspace overview summary",
    );
    assert.equal(overview.stat, "3");
    await screenshot(page, "03-lab-overview-cases.png");

    // 5. The target overview uses the same candidate set as the wizard.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/overview?tab=targets`,
    });
    const targets = await waitForDocument(
      page.session,
      `(() => {
        const stats = document.querySelector("[data-testid='ov-target-stats']");
        if (!stats) return null;
        const state = {
          targets: stats.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim() ?? null,
          potential: stats.querySelector("[data-testid='ov-target-stat-potential']")?.textContent?.trim() ?? null,
        };
        return state.targets === "1" && state.potential === "2" ? state : null;
      })()`,
      "target overview summary",
    );
    assert.equal(targets.targets, "1");
    assert.equal(targets.potential, "2");
    await screenshot(page, "04-lab-overview-targets.png");

    // 6. Sessions are scoped to this workspace and Enter search restores them.
    await page.session.send("Page.navigate", { url: `${baseUrl}${labPath}/sessions` });
    const sessions = await waitForDocument(
      page.session,
      `(() => {
        const count = document.querySelector("[data-testid='session-browser-count']")?.textContent?.trim();
        if (!count || count.includes("加载")) return null;
        const sessionCards = document.querySelectorAll("[data-session-id]").length;
        if (sessionCards !== 1) return null;
        return { count, sessionCards };
      })()`,
      "workspace session list",
    );
    assert.match(sessions.count, /1/);
    await setControl(page, "[data-testid='search-input']", sessionId);
    await evaluate(
      page,
      `document.querySelector("[data-testid='search-input']").dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true })
      ); true`,
    );
    await waitForDocument(
      page.session,
      `new URLSearchParams(location.search).get("q") === ${JSON.stringify(sessionId)}`,
      "session search query",
    );
    await screenshot(page, "05-lab-sessions.png", false);

    // 7. Error detail is still un-attributed before the first run.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/sessions/${sessionId}/errors?case=${ingestCases[0].badCaseId}&tab=attr`,
    });
    const unattributed = await waitForDocument(
      page.session,
      `(() => {
        const empty = document.querySelector("[data-testid='attribution-empty']");
        if (!empty) return null;
        return { text: empty.textContent };
      })()`,
      "unattributed case",
    );
    assert.match(unattributed.text, /尚未归因/);
    await screenshot(page, "06-lab-error-unattributed.png");

    // 8. Four-step wizard previews the same two potential cases.
    await page.session.send("Page.navigate", { url: `${baseUrl}${labPath}/evolution` });
    await click(page, "[data-testid='open-launch-wizard']");
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='launch-wizard']"))`,
      "wizard modal",
    );
    await selectOption(page, "[data-testid='wizard-target']", "synthetic-review");
    await setControl(page, "[data-testid='wizard-version']", "synthetic-1");
    await setControl(page, "[data-testid='wizard-from']", "2026-10-01");
    await setControl(page, "[data-testid='wizard-to']", "2026-10-31");
    await screenshot(page, "07-wizard-step1.png", false);

    await click(page, "[data-testid='wizard-next']");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='wizard-session-table']")?.textContent.includes("技能分叉")`,
      "associated session",
    );
    await click(page, "[data-testid='wizard-step2-next']");
    const potential = await waitForDocument(
      page.session,
      `(() => {
        const table = document.querySelector("[data-testid='wizard-potential-table']");
        if (!table) return null;
        const rows = table.querySelectorAll("tbody tr").length;
        return { rows, text: table.textContent };
      })()`,
      "potential preview rows",
    );
    assert.equal(potential.rows, 2, potential.text);
    await screenshot(page, "08-wizard-step3.png", false);

    await click(page, "[data-testid='wizard-step3-next']");
    const attributionPreview = await waitForDocument(
      page.session,
      `(() => {
        const stats = document.querySelector("[data-testid='wizard-attribution-stats']");
        if (!stats) return null;
        return stats.textContent;
      })()`,
      "attribution preview",
    );
    assert.match(attributionPreview, /潜在 bad case/);
    assert.match(attributionPreview, /2/);
    await click(page, "[data-testid='wizard-cluster']");
    await waitForDocument(
      page.session,
      `location.pathname.includes("/evolution/cluster/")`,
      "cluster preview route",
    );
    const runId = await evaluate(page, `location.pathname.split("/").pop()`);
    assert.ok(runId);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='evolution-cluster-preview']"))`,
      "cluster preview page",
    );
    const runCard = await pollRun(runId);
    assert.equal(runCard.status, "completed", JSON.stringify(runCard));
    await waitForDocument(
      page.session,
      `(() => {
        const status = document.querySelector("[data-testid='cluster-status']");
        if (!status) return false;
        const badge = status.querySelector(".badge")?.textContent?.trim();
        return badge === "completed";
      })()`,
      "cluster-only run completion",
    );
    await screenshot(page, "09-cluster-preview.png");

    // 9. Run detail shows seven steps and the cluster step is clickable.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/evolution/runs/${runId}`,
    });
    const runDetail = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='evolution-run-detail']");
        if (!root) return null;
        const steps = [...root.querySelectorAll("[data-step-key]")];
        if (steps.length !== 7) return null;
        return {
          steps: steps.map((step) => step.getAttribute("data-step-key")),
          title: document.querySelector("h1")?.textContent?.trim(),
        };
      })()`,
      "run detail seven steps",
    );
    assert.deepEqual(runDetail.steps, [
      "range",
      "sessions",
      "potential",
      "attribution",
      "clusters",
      "iteration",
      "final",
    ]);
    await click(page, "[data-step-key='clusters']");
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("聚类") &&
       document.body.textContent.includes("synthetic-review")`,
      "cluster step content",
    );
    await screenshot(page, "10-run-detail.png");

    // 10. The completed run is visible in the error detail as a real attribution.
    // A full reload avoids reusing the stale empty attribution query from step 7.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/sessions/${sessionId}/errors?case=${ingestCases[0].badCaseId}&tab=attr`,
    });
    const attributed = await waitForDocument(
      page.session,
      `(() => {
        const report = document.querySelector("[data-testid='attribution-report']");
        if (!report) return null;
        return { text: report.textContent };
      })()`,
      "attributed error detail",
    );
    assert.match(attributed.text, /synthetic-review/);
    assert.match(attributed.text, /可归因到本对象/);
    await screenshot(page, "11-lab-error-attributed.png");

    // 11. The execution flow defaults to lane DAG and keeps the tree toggle.
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/sessions/${sessionId}`,
    });
    const flow = await waitForDocument(
      page.session,
      `(() => {
        const view = document.querySelector("[data-testid='lane-viewport']");
        const lanes = [...document.querySelectorAll(".ld-lane")];
        if (!view || lanes.length < 2) return null;
        return { lanes: lanes.length };
      })()`,
      "lane DAG",
    );
    assert.ok(flow.lanes >= 2, JSON.stringify(flow));
    await screenshot(page, "12-lane-dag.png");
    await click(page, "[data-testid='flow-mode-tree']");
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".vue-flow")) &&
       !document.querySelector("[data-testid='lane-dag']")`,
      "structure tree toggle",
    );
    await screenshot(page, "13-structure-tree.png");
    await click(page, "[data-testid='flow-mode-dag']");
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='lane-dag']"))`,
      "lane DAG restored",
    );

    // 12. Switching back to the default workspace must not reuse the lab cache.
    await page.session.send("Page.navigate", { url: `${baseUrl}${labPath}/overview` });
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ov-stat-badcases'] b")?.textContent?.trim() === "3"`,
      "lab overview before workspace switch",
    );
    await openPickerAndSwitch(page, "ws-default");
    await waitForDocument(
      page.session,
      `location.pathname === ${JSON.stringify(`${defaultPath}/overview`)}`,
      "default workspace overview",
    );
    const defaultOverview = await waitForDocument(
      page.session,
      `(() => {
        const pageRoot = document.querySelector("[data-testid='overview-page']");
        if (!pageRoot) return null;
        const stat = pageRoot.querySelector("[data-testid='ov-stat-badcases'] b")?.textContent?.trim();
        if (stat !== "5") return null;
        return { stat };
      })()`,
      "default workspace data",
    );
    assert.equal(defaultOverview.stat, "5");
    await screenshot(page, "14-default-overview.png");

    await openPickerAndSwitch(page, labId);
    await waitForDocument(
      page.session,
      `location.pathname === ${JSON.stringify(`${labPath}/overview`)} &&
       document.querySelector("[data-testid='ov-stat-badcases'] b")?.textContent?.trim() !== "5"`,
      "lab overview does not reuse the default workspace data",
    );
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${labPath}/overview?tab=cases&range=90&grain=week`,
    });
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ov-stat-badcases'] b")?.textContent?.trim() === "3"`,
      "lab overview after switching back",
    );

    assert.deepEqual(violations, [], violations.join("\n"));
  } catch (error) {
    const url = await evaluate(page, "location.href").catch(() => "unavailable");
    throw new Error(
      `${error.message}\nurl=${url}\napi=${apiLogs.slice(-2000)}\nweb=${webLogs.slice(-800)}`,
    );
  } finally {
    await page.close();
  }
});
