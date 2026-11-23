// The deploy workflow uploads apps/api/. Bundle the versioned runtime assets with it.
import { copyFile, mkdir, readFile, rm } from "node:fs/promises";
import path from "node:path";

const output = path.resolve("apps/api/release-assets");
const manifest = await readFile("deploy/attribution-assets.list", "utf8");
await rm(output, { recursive: true, force: true });
for (const resource of manifest.trim().split(/\r?\n/)) {
  const destination = path.join(output, resource);
  await mkdir(path.dirname(destination), { recursive: true });
  await copyFile(resource, destination);
}
