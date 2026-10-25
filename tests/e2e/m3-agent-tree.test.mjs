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
      password: "m3-agent-tree-initial-password",
    }),
  });
  assert.equal(login.status, 200);
  const body = await login.json();
  const initialCookie = login.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);

  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${body.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: "m3-agent-tree-initial-password",
      newPassword: "m3-agent-tree-replacement-password",
    }),
  });
  assert.equal(changed.status, 204);

  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  assert.equal(refreshed.status, 200);
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return cookie;
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m3-tree-e2e-"));
  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...process.env,
      HE_ADMIN_PASSWORD: "m3-agent-tree-initial-password",
      HE_ADMIN_USERNAME: "admin",
      HE_DATA_DIR: dataDir,
      HE_DB_DIALECT: "sqlite",
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_JWT_SECRET: "m3-agent-tree-signing-secret-with-sufficient-length",
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

test("m3-agent-tree renders the prototype graph with real Vue Flow geometry", async () => {
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
    await page.session.send("Page.navigate", { url: `${baseUrl}/agent-tree-demo` });

    const result = await waitForDocument(
      page.session,
      `(() => {
        const nodes = [...document.querySelectorAll(".vue-flow__node")];
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (nodes.length !== 4 || !tree) return null;
        const measured = nodes.map((node) => {
          const box = node.querySelector(".rf-agent");
          const rect = node.getBoundingClientRect();
          return {
            text: (box?.querySelector(".rf-label")?.textContent ?? "").trim(),
            width: box?.getBoundingClientRect().width ?? 0,
            y: rect.y,
            border: box ? getComputedStyle(box).borderTopColor : "",
          };
        });
        const controls = [...document.querySelectorAll(".vue-flow__controls-button")];
        return {
          nodes: measured,
          edges: document.querySelectorAll(".vue-flow__edge-path").length,
          markerEnds: [...document.querySelectorAll(".vue-flow__edge-path")].map(
            (edge) => edge.getAttribute("marker-end"),
          ),
          height: tree.getBoundingClientRect().height,
          controls: Boolean(document.querySelector(".vue-flow__controls")),
          controlButtons: controls.map((button) => {
            const rect = button.getBoundingClientRect();
            return {
              label: button.getAttribute("aria-label") ?? button.getAttribute("title") ?? "",
              width: rect.width,
              height: rect.height,
              hasIcon: Boolean(button.querySelector("svg")),
            };
          }),
          background: Boolean(document.querySelector(".vue-flow__background")),
          treeRequests: performance.getEntriesByType("resource")
            .filter((entry) => entry.name.endsWith("/tree")).length,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "real Vue Flow Agent tree",
    );

    const find = (text) => {
      const match = result.nodes.find((node) => node.text.includes(text));
      assert.ok(match, `missing node ${text}: ${JSON.stringify(result)}`);
      return match;
    };
    const main = find("主会话");
    const nested = find("子任务 A");
    const child = find("子任务 C");
    const shortest = [...result.nodes].sort((left, right) => left.width - right.width)[0];

    assert.equal(result.nodes.length, 4);
    assert.equal(result.edges, 3);
    assert.equal(result.markerEnds.every(Boolean), true, JSON.stringify(result));
    assert.ok(Math.abs(result.height - 720) < 1, JSON.stringify(result));
    assert.equal(result.controls, true);
    assert.ok(result.controlButtons.length >= 3, JSON.stringify(result));
    for (const button of result.controlButtons) {
      assert.ok(button.label, JSON.stringify(button));
      assert.ok(button.width >= 24 && button.height >= 24, JSON.stringify(button));
      assert.equal(button.hasIcon, true, JSON.stringify(button));
    }
    assert.equal(result.background, true);
    assert.equal(result.treeRequests, 0);
    assert.ok(result.scrollWidth <= result.clientWidth, JSON.stringify(result));
    assert.ok(main.width > shortest.width, JSON.stringify({ main, shortest }));
    assert.ok(main.y < nested.y && nested.y < child.y, JSON.stringify({ main, nested, child }));
    assert.notEqual(main.border, nested.border);
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);

    await page.session.send("Runtime.evaluate", {
      expression: `history.pushState({}, "", "/agent-tree-demo?variant=large");
        window.dispatchEvent(new PopStateEvent("popstate"))`,
    });
    const loadedLarge = await waitForDocument(
      page.session,
      `location.href.includes("variant=large") && document.readyState !== "loading"
        ? {
            href: location.href,
            title: document.title,
            body: document.body.innerText.slice(0, 300),
            nodes: document.querySelectorAll(".vue-flow__node").length
          }
        : null`,
      "large demo document",
    );
    const collapsed = await waitForDocument(
      page.session,
      `(() => {
        const nodes = [...document.querySelectorAll(".vue-flow__node")];
        const collapse = document.querySelector(".rf-agent.collapse");
        if (!nodes.length) return null;
        return {
          count: nodes.length,
          hasCollapse: Boolean(collapse),
          label: collapse?.textContent?.trim() ?? "",
          path: location.pathname + location.search
        };
      })()`,
      "collapsed large demo",
    );
    assert.equal(loadedLarge.href.includes("variant=large"), true, JSON.stringify(loadedLarge));
    assert.equal(collapsed.count, 2, JSON.stringify(collapsed));
    assert.equal(collapsed.hasCollapse, true, JSON.stringify(collapsed));
    assert.match(collapsed.label, /个子 agent/);
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(".rf-agent.collapse").click()`,
    });
    const expanded = await waitForDocument(
      page.session,
      `document.querySelectorAll(".vue-flow__node").length === 13`,
      "expanded large demo",
    );
    assert.equal(expanded, true);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const narrow = await waitForDocument(
      page.session,
      `(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        treeHeight: document.querySelector("[data-testid='agent-tree']")?.getBoundingClientRect().height,
        controls: document.querySelectorAll(".vue-flow__controls-button").length
      }))()`,
      "narrow agent tree",
    );
    assert.equal(narrow.scrollWidth <= narrow.clientWidth, true, JSON.stringify(narrow));
    assert.ok(narrow.treeHeight >= 300, JSON.stringify(narrow));
    assert.ok(narrow.controls >= 3, JSON.stringify(narrow));

    if (process.env.HE_E2E_ARTIFACT_DIR) {
      const capture = await page.session.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: false,
      });
      await mkdir(process.env.HE_E2E_ARTIFACT_DIR, { recursive: true });
      await writeFile(
        path.join(process.env.HE_E2E_ARTIFACT_DIR, "m3-agent-tree.png"),
        Buffer.from(capture.data, "base64"),
      );
    }
  } finally {
    await page.close();
  }
});
