import assert from "node:assert/strict";
import { spawn } from "node:child_process";
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
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m11-07-initial-password";
const secret = "m11-07-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
const sessionId = "10000000-0000-4000-8000-000000000001";
const caseId = "badcase-synthetic-0001";
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";
let currentPassword = initialPassword;
let passwordRevision = 0;

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

async function loginSession() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: currentPassword }),
  });
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);

  const replacement = `m11-07-password-${++passwordRevision}`;
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${login.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ oldPassword: currentPassword, newPassword: replacement }),
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
  currentPassword = replacement;
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

async function clientNavigate(page, pathname) {
  await page.session.send("Runtime.evaluate", {
    expression: `history.pushState({}, "", ${JSON.stringify(pathname)});
      window.dispatchEvent(new PopStateEvent("popstate"));`,
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

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m11-07-e2e-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
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
  const seedExit = await new Promise((resolve) => {
    seed.once("exit", (code) => resolve(code));
  });
  assert.equal(seedExit, 0, seedLogs);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  apiUrl = `http://127.0.0.1:${apiPort}`;
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
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
});

after(cleanup);

test("m11-07 execution-flow defaults to lane DAG with zoom, pan and a structure-tree toggle", async () => {
  const auth = await loginSession();
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    await installCookie(page, auth.cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
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
    await waitForDocument(
      page.session,
      `/^\\/workspaces\\/ws-default\\/sessions\\/[0-9a-f-]{36}$/.test(location.pathname)`,
      "session auto-selection settled",
    );

    await clientNavigate(page, `${ws}/sessions/${sessionId}`);
    const flow = await waitForDocument(
      page.session,
      `(() => {
        const view = document.querySelector("[data-testid='lane-viewport']");
        const lanes = [...document.querySelectorAll(".ld-lane")];
        const markers = [...document.querySelectorAll(".ld-case")];
        if (!view || lanes.length < 2 || markers.length < 2) return null;
        const laneBars = lanes.map((lane) => {
          const bars = [...lane.querySelectorAll(".ld-bar")].map((bar) => {
            const rect = bar.getBoundingClientRect();
            return { left: rect.left, right: rect.right, width: rect.width };
          }).sort((left, right) => left.left - right.left);
          return {
            path: lane.getAttribute("data-lane-path"),
            overlapping: bars.some((bar, index) => index > 0 && bar.left < bars[index - 1].right - 1),
            bars: bars.length,
          };
        });
        return {
          modeDag: document.querySelector("[data-testid='flow-mode-dag']")?.getAttribute("aria-pressed"),
          treeVisible: Boolean(document.querySelector(".vue-flow")),
          paths: lanes.map((lane) => lane.getAttribute("data-lane-path")),
          laneBars,
          markers: markers.map((marker) => marker.textContent.trim()),
          title: document.querySelector("[data-testid='agent-tree-title']")?.textContent,
          foot: document.querySelector(".ld-foot")?.textContent?.replace(/\\s+/g, " ").trim(),
          height: view.getBoundingClientRect().height,
          transform: document.querySelector(".ld-canvas")?.style.transform,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "session lane DAG",
    );

    assert.equal(flow.modeDag, "true");
    assert.equal(flow.treeVisible, false, JSON.stringify(flow));
    assert.ok(flow.paths.includes("A1"), JSON.stringify(flow));
    assert.ok(flow.paths.includes("A1.1"), JSON.stringify(flow));
    assert.equal(flow.laneBars.some((lane) => lane.overlapping), false, JSON.stringify(flow));
    assert.equal(flow.laneBars.every((lane) => lane.bars > 0), true, JSON.stringify(flow));
    assert.equal(flow.markers.length >= 2, true, JSON.stringify(flow));
    assert.ok(flow.height <= 521 && flow.height >= 359, JSON.stringify(flow));
    assert.match(flow.foot, /同一 lane 内 bar 不重叠/);
    assert.match(flow.foot, /不再按数量折叠/);
    assert.ok(flow.scrollWidth <= flow.clientWidth, JSON.stringify(flow));

    const markerFlow = await waitForDocument(
      page.session,
      `(() => {
        const marker = document.querySelector(".ld-case[data-bad-case-id='${caseId}']");
        if (!marker) return null;
        marker.click();
        return true;
      })()`,
      "clicked BC marker",
    );
    assert.equal(markerFlow, true);
    const selected = await waitForDocument(
      page.session,
      `(() => {
        const marker = document.querySelector(".ld-case[data-bad-case-id='${caseId}']");
        if (!marker?.classList.contains("is-selected")) return null;
        return {
          selected: marker.classList.contains("is-selected"),
          highlightedBars: document.querySelectorAll(".ld-bar.is-case-src").length,
          hit: document.querySelector("[data-testid='lane-selected-case']")?.textContent,
        };
      })()`,
      "selected BC marker",
    );
    assert.equal(selected.selected, true);
    assert.ok(selected.highlightedBars > 0, JSON.stringify(selected));
    assert.match(selected.hit, /高亮 BC/);

    const zoomed = await evaluate(
      page,
      `(async () => {
        const viewport = document.querySelector("[data-testid='lane-viewport']");
        const canvas = document.querySelector(".ld-canvas");
        const rect = viewport.getBoundingClientRect();
        const before = canvas.style.transform;
        viewport.dispatchEvent(new WheelEvent("wheel", {
          deltaY: -120,
          clientX: rect.left + rect.width / 2,
          clientY: rect.top + rect.height / 2,
          bubbles: true,
          cancelable: true,
        }));
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const afterWheel = canvas.style.transform;
        viewport.dispatchEvent(new PointerEvent("pointerdown", {
          pointerId: 1,
          button: 0,
          clientX: rect.left + 200,
          clientY: rect.top + 120,
          bubbles: true,
        }));
        viewport.dispatchEvent(new PointerEvent("pointermove", {
          pointerId: 1,
          clientX: rect.left + 260,
          clientY: rect.top + 150,
          bubbles: true,
        }));
        viewport.dispatchEvent(new PointerEvent("pointerup", { pointerId: 1, bubbles: true }));
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const afterPan = canvas.style.transform;
        document.querySelector("button[aria-label='恢复 1:1']").click();
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const reset = canvas.style.transform;
        document.querySelector("button[aria-label='适应窗口']").click();
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        return { before, afterWheel, afterPan, reset, fitted: canvas.style.transform };
      })()`,
    );
    assert.notEqual(zoomed.afterWheel, zoomed.before);
    assert.notEqual(zoomed.afterPan, zoomed.afterWheel);
    assert.equal(zoomed.reset, "translate(0px, 0px) scale(1)");
    assert.match(zoomed.fitted, /scale\(/);

    await evaluate(page, `document.querySelector("[data-testid='flow-mode-tree']").click()`);
    const tree = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const flow = tree?.querySelector(".vue-flow");
        if (!tree || !flow) return null;
        return {
          treeVisible: true,
          laneVisible: Boolean(document.querySelector("[data-testid='lane-dag']")),
          nodes: document.querySelectorAll(".vue-flow__node").length,
        };
      })()`,
      "structure tree toggle",
    );
    assert.equal(tree.treeVisible, true);
    assert.equal(tree.laneVisible, false);
    assert.ok(tree.nodes >= 2, JSON.stringify(tree));

    await evaluate(page, `document.querySelector("[data-testid='flow-mode-dag']").click()`);
    const back = await waitForDocument(
      page.session,
      `(() => {
        const marker = document.querySelector(".ld-case[data-bad-case-id='${caseId}']");
        if (!marker?.classList.contains("is-selected")) return null;
        return {
          laneVisible: Boolean(document.querySelector("[data-testid='lane-viewport']")),
          selected: marker.classList.contains("is-selected"),
        };
      })()`,
      "lane DAG restored with selection",
    );
    assert.equal(back.laneVisible, true);
    assert.equal(back.selected, true);

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=desc`,
    );
    const errors = await waitForDocument(
      page.session,
      `(() => {
        const workspace = document.querySelector("[data-testid='errors-workspace']");
        const view = document.querySelector("[data-testid='lane-viewport']");
        const marker = document.querySelector(".ld-case[data-bad-case-id='${caseId}']");
        if (!workspace || !view || !marker) return null;
        return {
          selected: marker.classList.contains("is-selected"),
          note: document.querySelector(".flow-head span")?.textContent,
          timeline: document.body.innerText.includes("打开时间线"),
          positions: document.querySelector(".ld-hit")?.textContent,
          lanes: document.querySelectorAll(".ld-lane").length,
        };
      })()`,
      "error detail lane DAG",
    );
    assert.equal(errors.selected, true);
    assert.match(errors.note, /保留全部并发分支/);
    assert.equal(errors.timeline, false);
    assert.match(errors.positions, /高亮 BC/);
    assert.ok(errors.lanes >= 2, JSON.stringify(errors));

    await clientNavigate(page, `/agent-tree-demo?variant=stress`);
    const stress = await waitForDocument(
      page.session,
      `(() => {
        if (!document.querySelector("[data-testid='agent-tree-demo']")) return null;
        const lanes = [...document.querySelectorAll(".ld-lane")];
        if (lanes.length !== 61) return null;
        return {
          lanes: lanes.length,
          folds: document.querySelectorAll(".ld-fold-summary").length,
          paths: lanes.slice(0, 3).map((lane) => lane.getAttribute("data-lane-path")),
          view: document.querySelector("[data-testid='lane-viewport']")?.getBoundingClientRect().height,
        };
      })()`,
      "61-agent lane DAG",
    );
    assert.equal(stress.lanes, 61);
    assert.equal(stress.folds, 0);
    assert.deepEqual(stress.paths, ["A1", "A1.1", "A1.2"]);
    const stressZoom = await evaluate(
      page,
      `(async () => {
        const viewport = document.querySelector("[data-testid='lane-viewport']");
        const canvas = document.querySelector(".ld-canvas");
        const before = canvas.style.transform;
        const rect = viewport.getBoundingClientRect();
        viewport.dispatchEvent(new WheelEvent("wheel", {
          deltaY: -120,
          clientX: rect.left + rect.width / 2,
          clientY: rect.top + rect.height / 2,
          bubbles: true,
          cancelable: true,
        }));
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        return { before, after: canvas.style.transform };
      })()`,
    );
    assert.notEqual(stressZoom.after, stressZoom.before);

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);

    if (process.env.HE_E2E_ARTIFACT_DIR) {
      const captureResult = await page.session.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: false,
      });
      await mkdir(process.env.HE_E2E_ARTIFACT_DIR, { recursive: true });
      await writeFile(
        path.join(process.env.HE_E2E_ARTIFACT_DIR, "m11-07-execution-flow.png"),
        Buffer.from(captureResult.data, "base64"),
      );
    }
  } finally {
    await page.close();
  }
});
