// Capture prototype screenshots for the m6-16 design review.
// Usage: node capture.mjs <before|after>
// Requires CHROME_BIN pointing at a Chrome executable on Windows.
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  createBrowserPage,
  waitForDocument,
} from "../../../tests/support/runtime.mjs";

const phase = process.argv[2];
if (!["before", "after"].includes(phase)) {
  console.error("usage: node capture.mjs <before|after>");
  process.exit(2);
}

const reportDir = path.dirname(fileURLToPath(import.meta.url));
const pageUrl = new URL("../../../plans/14-15-ui-prototype/harness-evolution.html", import.meta.url).href;

/**
 * Capture one viewport-sized PNG after navigating to the prototype.
 * @param {{session: object, close: () => Promise<void>}} page Browser page.
 * @param {{width: number, height: number, name: string, openSync: boolean}} options Capture options.
 * @returns {Promise<void>} Resolves after the PNG is written.
 */
async function shoot(page, { width, height, name, openSync }) {
  const { session } = page;
  await session.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await session.send("Page.navigate", { url: pageUrl });
  await waitForDocument(session, "document.readyState === 'complete'", `${name} load`);
  await new Promise((resolve) => setTimeout(resolve, 400));
  if (openSync) {
    await session.send("Runtime.evaluate", {
      expression: "document.querySelector('details.tn-sync').open = true",
    });
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  const { data } = await session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const target = path.join(reportDir, `${phase}-${name}.png`);
  await writeFile(target, Buffer.from(data, "base64"));
  console.log(`wrote ${target}`);
}

const page = await createBrowserPage();
try {
  await shoot(page, { width: 1408, height: 900, name: "desktop", openSync: false });
  await shoot(page, { width: 1408, height: 900, name: "desktop-open", openSync: true });
  await shoot(page, { width: 390, height: 844, name: "mobile", openSync: false });
} finally {
  await page.close();
}
