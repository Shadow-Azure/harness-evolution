// Capture before/after prototype screenshots for the multi-object evolution target review.
// Usage: node capture.mjs <before|after>
//   PROTOTYPE_HTML=<path>  optional prototype file; defaults to ../../harness-evolution.html.
//                          For the "before" pass, export the committed file first:
//                          git show HEAD:plans/ui-prototype-v2/harness-evolution.html > <tmp>
// Requires CHROME_BIN pointing at a Chrome executable on Windows.
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { createBrowserPage } from "../../../../tests/support/runtime.mjs";

const phase = process.argv[2];
if (!["before", "after"].includes(phase)) {
  console.error("usage: node capture.mjs <before|after>");
  process.exit(2);
}

const evidenceDir = path.dirname(fileURLToPath(import.meta.url));
const prototypePath =
  process.env.PROTOTYPE_HTML || path.join(evidenceDir, "..", "..", "harness-evolution.html");
const pageUrl = pathToFileURL(path.resolve(prototypePath)).href;
console.log(`prototype: ${pageUrl}`);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Evaluate one expression and return its JSON value.
 * @param {object} session CDP session.
 * @param {string} expression JavaScript expression.
 * @returns {Promise<unknown>} Serialized result.
 */
async function evaluate(session, expression) {
  const result = await session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(`evaluation failed: ${result.exceptionDetails.text} ${expression}`);
  }
  return result.result.value;
}

/**
 * Evaluate one expression until it returns true; the prototype boots after its
 * CDN React bundle lands, which is slow on a cold profile.
 * @param {object} session CDP session.
 * @param {string} expression JavaScript expression.
 * @param {string} label Wait reason for the error message.
 * @returns {Promise<void>} Resolves once the expression is truthy.
 */
async function waitUntil(session, expression, label) {
  const deadline = Date.now() + 90_000;
  let lastLog = 0;
  while (Date.now() < deadline) {
    const value = await evaluate(session, expression);
    if (value) return;
    if (Date.now() - lastLog > 10_000) {
      lastLog = Date.now();
      const state = await evaluate(
        session,
        "[document.readyState, location.search, performance.now() | 0].join(' ')",
      ).catch(() => "unavailable");
      console.log(`  waiting for ${label}: ${expression} => ${JSON.stringify(value)} (${state})`);
    }
    await sleep(150);
  }
  throw new Error(`timed out waiting for ${label}`);
}

/**
 * Open one prototype route and wait until the app reports ready.
 * @param {object} session CDP session.
 * @param {string} query URL query string.
 * @returns {Promise<void>} Resolves after the V2 shell booted.
 */
async function open(session, query) {
  await session.send("Page.navigate", { url: `${pageUrl}?${query}` });
  await waitUntil(session, "window.V2_READY === true", `boot ${query}`);
  await sleep(500);
}

/**
 * Click one element through the page's own click delegation.
 * @param {object} session CDP session.
 * @param {string} selector CSS selector.
 * @returns {Promise<void>} Resolves after the click dispatched.
 */
async function click(session, selector) {
  const ok = await evaluate(
    session,
    `(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true; })()`,
  );
  if (!ok) throw new Error(`element not found: ${selector}`);
  await sleep(350);
}

/**
 * Capture one element as a crisp PNG with a small margin.
 * @param {object} session CDP session.
 * @param {string} selector CSS selector of the element to crop.
 * @param {string} name Output file stem.
 * @returns {Promise<void>} Resolves after the PNG is written.
 */
async function shootElement(session, selector, name) {
  const rect = await evaluate(
    session,
    `(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return null;
      const r = el.getBoundingClientRect();
      const y = r.top + window.scrollY;
      // Leave room for the sticky app header so it does not paint over the crop.
      window.scrollTo(0, Math.max(0, y - 170));
      return { x: r.left + window.scrollX, y, width: r.width, height: r.height };
    })()`,
  );
  if (!rect) throw new Error(`element not found for capture: ${selector}`);
  await sleep(200);
  const { data } = await session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: true,
    clip: {
      x: Math.max(0, rect.x - 16),
      y: Math.max(0, rect.y - 16),
      width: rect.width + 32,
      height: rect.height + 32,
      scale: 2,
    },
  });
  const target = path.join(evidenceDir, `${phase}-${name}.png`);
  await writeFile(target, Buffer.from(data, "base64"));
  console.log(`wrote ${path.relative(process.cwd(), target)}`);
}

await mkdir(evidenceDir, { recursive: true });
const page = await createBrowserPage();
try {
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });

  // 1. Target configuration dialog (总览 → 进化对象 → 新增进化对象)
  await open(page.session, "u=admin&page=overview&tab=targets");
  await click(page.session, "[data-v2-tg-add]");
  await waitUntil(
    page.session,
    "!!document.getElementById('v2TgName') || !!document.querySelector('#v2TgMembers [data-v2-tg-member]')",
    "target dialog",
  );
  if (phase === "after") {
    // The after-state dialog is one configuration with a shared block and member
    // rows. Add a second member and fill both rows plus the shared block through
    // the page's own input events so the sub-directory auto-fill runs as a user
    // would see it.
    await click(page.session, "[data-v2-tg-member-add]");
    await evaluate(page.session, `(() => {
      const set = (el, value) => { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); };
      set(document.getElementById('v2TgRepo'), 'https://github.com/acme/agent-skills.git');
      set(document.getElementById('v2TgVersion'), 'v2.4.0');
      set(document.getElementById('v2TgVal'), 'val-skills-2026q4');
      set(document.getElementById('v2TgTest'), 'test-skills-2026q4');
      set(document.getElementById('v2TgMetric'), 'resolved_rate');
      const rows = [...document.querySelectorAll('#v2TgMembers [data-v2-tg-member]')];
      set(rows[0].querySelector('.tgm-name'), 'deep-research');
      set(rows[1].querySelector('.tgm-name'), 'code-review');
      document.getElementById('v2TgMembers').scrollIntoView({ block: 'center' });
      return true;
    })()`);
    await sleep(300);
  }
  await shootElement(page.session, "#v2Modal .modal", "target-form");

  // 2. Launch wizard, step 1 (选择范围). On the evo page the wizard mounts
  // into the page-local #modal-root rather than the global #v2Modal. A taller
  // viewport lets the modal body (max-height 66vh) show the whole form.
  await open(page.session, "u=admin&demo=wizard1");
  await waitUntil(page.session, "!!document.querySelector('#modal-root .evov .modal')", "wizard step 1");
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1200,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await sleep(300);
  await shootElement(page.session, "#modal-root .modal", "wizard-step1");
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });

  // 3. Run detail, step 1 (选择范围)
  await open(page.session, "u=admin&demo=run");
  await waitUntil(page.session, "!!document.querySelector('.detail-head')", "run detail");
  await evaluate(page.session, "window.__evState.selStep = 0; window.scrollTo(0,0); true");
  await sleep(300);
  await click(page.session, "[data-action=\"ev-detail-tab\"][data-tab=\"steps\"]");
  await evaluate(page.session, "window.__evState.selStep = 0; true");
  await sleep(200);
  await evaluate(
    page.session,
    `(() => { const el = document.querySelector('[data-action="ev-sel-step"][data-step="0"]'); if (el) el.click(); return true; })()`,
  );
  await sleep(400);
  await shootElement(page.session, ".evo-app .wrap", "run-scope");

  // 4. Run detail, workspace block inside the step-4 info panel
  await evaluate(
    page.session,
    `(() => { const el = document.querySelector('[data-action="ev-sel-step"][data-step="3"]'); if (el) el.click(); return true; })()`,
  );
  await sleep(400);
  await evaluate(page.session, `(() => { const d = document.querySelector('details.ws-detail'); if (d) d.open = true; return !!d; })()`);
  await sleep(250);
  await shootElement(page.session, "details.ws-detail", "run-workspace");
} finally {
  await page.close();
}
