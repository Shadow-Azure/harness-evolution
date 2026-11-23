import assert from "node:assert/strict";
import { createServer } from "node:net";
import { test } from "node:test";

import { createBrowserPage, waitFor } from "../support/runtime.mjs";

async function within(promise, milliseconds) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("regression deadline exceeded")), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

test("browser runtime bounds a silent HTTP readiness peer", async () => {
  const connections = new Set();
  const server = createServer((socket) => {
    connections.add(socket);
    socket.on("error", () => {});
    socket.on("close", () => connections.delete(socket));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const waiting = waitFor(
    `http://127.0.0.1:${server.address().port}/`,
    { exitCode: null },
    () => "silent peer",
    response => response.ok,
    100,
  );
  try {
    await assert.rejects(within(waiting, 5_000), /timed out waiting.*\n.*silent peer/);
  } finally {
    for (const socket of connections) socket.destroy();
    await new Promise(resolve => server.close(resolve));
    await waiting.catch(() => {});
  }
});

test("browser runtime rejects in-flight commands when the page closes", async () => {
  const page = await createBrowserPage();
  const request = page.session.send("Runtime.evaluate", {
    expression: "new Promise(() => {})", awaitPromise: true,
  });
  const outcome = within(request, 5_000).then(
    () => ({ error: null }), error => ({ error }),
  );
  await page.close();
  assert.match((await outcome).error?.message ?? "request unexpectedly resolved", /CDP.*closed/);
  assert.equal(page.session.pending.size, 0);
});

test("browser runtime rejects in-flight commands on WebSocket disconnect", async () => {
  const page = await createBrowserPage();
  try {
    const request = page.session.send("Runtime.evaluate", {
      expression: "new Promise(() => {})", awaitPromise: true,
    });
    const outcome = within(request, 5_000).then(
      () => ({ error: null }), error => ({ error }),
    );
    page.session.socket.close();
    assert.match((await outcome).error?.message ?? "request unexpectedly resolved", /CDP.*closed/);
    assert.equal(page.session.pending.size, 0);
  } finally {
    await page.close();
  }
});

test("browser runtime expires an unresponsive CDP command", async () => {
  const page = await createBrowserPage();
  try {
    await assert.rejects(within(page.session.send("Runtime.evaluate", {
      expression: "new Promise(() => {})", awaitPromise: true,
    }, 100), 5_000), /CDP.*Runtime.evaluate.*timed out/);
    assert.equal(page.session.pending.size, 0);
  } finally {
    await page.close();
  }
});

test("browser runtime rejects new commands after close without retaining them", async () => {
  const page = await createBrowserPage();
  await page.close();
  await assert.rejects(within(page.session.send("Runtime.evaluate", { expression: "1" }), 5_000), /CDP.*closed/);
  assert.equal(page.session.pending.size, 0);
});

test("browser runtime clears a command that fails before sending", async () => {
  const page = await createBrowserPage();
  try {
    const params = {};
    params.self = params;
    await assert.rejects(page.session.send("Runtime.evaluate", params), /circular/i);
    assert.equal(page.session.pending.size, 0);
  } finally {
    await page.close();
  }
});
