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
        const detailCta = document.querySelector(".overview-head [data-testid='detail-cta']");
        if (cards.length !== 4 || !sidebar || !card || !detailCta) return null;
        return {
          path: location.pathname,
          query: location.search,
          cards: cards.length,
          densities: document.querySelectorAll("[data-testid='density-bar']").length,
          sidebarWidth: sidebar.getBoundingClientRect().width,
          browserWidth: document.querySelector(".session-browser").getBoundingClientRect().width,
          browserRadius: getComputedStyle(document.querySelector(".session-browser")).borderRadius,
          filterLabels: [...document.querySelectorAll(".filter-label")].map((node) => node.textContent.trim()),
          ctaInHeader: Boolean(detailCta),
          cardBackground: getComputedStyle(card).backgroundColor,
          bodyBackground: getComputedStyle(document.body).backgroundColor,
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
    assert.ok(initial.browserWidth >= 1390, JSON.stringify(initial));
    assert.equal(initial.browserRadius, "0px");
    assert.deepEqual(initial.filterLabels, ["状态", "排序"]);
    assert.equal(initial.ctaInHeader, true);

    const initialTree = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const nodes = tree?.querySelectorAll(".vue-flow__node").length ?? 0;
        if (!tree || nodes === 0) return null;
        return {
          height: tree.getBoundingClientRect().height,
          nodes,
          legend: (() => {
            const node = document.querySelector(".tree-legend");
            if (!node) return null;
            const box = node.getBoundingClientRect();
            const treeBox = tree.getBoundingClientRect();
            return {
              bottomGap: treeBox.bottom - box.bottom,
              leftGap: box.left - treeBox.left,
            };
          })(),
        };
      })()`,
      "production Agent tree",
    );
    assert.ok(Math.abs(initialTree.height - 720) < 1, JSON.stringify(initialTree));
    assert.ok(initialTree.nodes > 0, JSON.stringify(initialTree));
    assert.ok(initialTree.legend, JSON.stringify(initialTree));
    assert.ok(initialTree.legend.leftGap >= 0 && initialTree.legend.leftGap <= 24, JSON.stringify(initialTree));
    assert.ok(initialTree.legend.bottomGap >= 0 && initialTree.legend.bottomGap <= 24, JSON.stringify(initialTree));

    const pressKey = async (key, code, windowsVirtualKeyCode) => {
      await page.session.send("Input.dispatchKeyEvent", {
        type: key === "Enter" ? "rawKeyDown" : "keyDown",
        key,
        code,
        windowsVirtualKeyCode,
      });
      if (key === "Enter") {
        await page.session.send("Input.dispatchKeyEvent", {
          type: "char",
          key,
          code,
          text: "\r",
          unmodifiedText: "\r",
          windowsVirtualKeyCode,
        });
      }
      await page.session.send("Input.dispatchKeyEvent", {
        type: "keyUp",
        key,
        code,
        windowsVirtualKeyCode,
      });
    };
    const treeCounts = [];
    let keyboardCheck = null;
    for (let index = 0; index < initial.cards; index += 1) {
      await page.session.send("Runtime.evaluate", {
        expression: `document.querySelectorAll("[data-testid='session-card']")[${index}].click()`,
      });
      const tree = await waitForDocument(
        page.session,
        `(() => {
          const selected = document.querySelector("[data-testid='session-card'][data-selected='true']");
          const nodes = document.querySelectorAll("[data-testid='agent-tree'] .vue-flow__node").length;
          return selected && nodes > 0 ? { path: location.pathname, nodes } : null;
        })()`,
        `Agent tree for session ${index + 1}`,
      );
      assert.match(tree.path, /^\/sessions\/.+/);
      treeCounts.push(tree.nodes);
      if (!keyboardCheck && tree.nodes > 1) {
        const focusState = await page.session.send("Runtime.evaluate", {
          expression: `(() => {
            const tree = document.querySelector("[data-testid='agent-tree']");
            tree.tabIndex = -1;
            tree.focus();
            return {
              edgeTabStops: [...document.querySelectorAll(".vue-flow__edge")].filter((node) => node.tabIndex >= 0).length,
              nodeWrapperTabStops: [...document.querySelectorAll(".vue-flow__node")].filter((node) => node.tabIndex >= 0).length,
            };
          })()`,
          returnByValue: true,
        });
        assert.equal(focusState.result.value.edgeTabStops, 0);
        assert.equal(focusState.result.value.nodeWrapperTabStops, 0);
        await pressKey("Tab", "Tab", 9);
        const firstFocus = await page.session.send("Runtime.evaluate", {
          expression: `(() => {
            const active = document.activeElement;
            return {
              className: active?.className ?? "",
              label: active?.getAttribute?.("aria-label") ?? "",
              tagName: active?.tagName ?? "",
            };
          })()`,
          returnByValue: true,
        });
        assert.equal(firstFocus.result.value.tagName, "BUTTON", JSON.stringify(firstFocus));
        assert.match(firstFocus.result.value.className, /rf-agent/);
        await pressKey("Tab", "Tab", 9);
        const secondFocus = await page.session.send("Runtime.evaluate", {
          expression: `(() => {
            const active = document.activeElement;
            return {
              className: active?.className ?? "",
              label: active?.getAttribute?.("aria-label") ?? "",
              tagName: active?.tagName ?? "",
            };
          })()`,
          returnByValue: true,
        });
        assert.equal(secondFocus.result.value.tagName, "BUTTON", JSON.stringify(secondFocus));
        assert.match(secondFocus.result.value.className, /rf-agent/);
        assert.notEqual(secondFocus.result.value.label, "主会话", JSON.stringify(secondFocus));
        await pressKey("Enter", "Enter", 13);
        const selectedNode = await waitForDocument(
          page.session,
          `(() => {
            const active = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
              .filter((node) => node.getAttribute("aria-pressed") === "true");
            return active.length === 1
              ? {
                  border: getComputedStyle(document.querySelector("[data-testid='agent-tree']")).borderTopWidth,
                  label: active[0].getAttribute("aria-label"),
                }
              : null;
          })()`,
          "selected Agent node",
        );
        assert.ok(selectedNode.label, JSON.stringify(selectedNode));
        assert.equal(selectedNode.border, "0px", JSON.stringify(selectedNode));
        keyboardCheck = selectedNode;
      }
    }
    assert.equal(treeCounts.length, 4);
    assert.equal(treeCounts.reduce((sum, count) => sum + count, 0), 8);
    assert.ok(keyboardCheck, "expected at least one multi-Agent Session");

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
