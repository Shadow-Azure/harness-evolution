import { execFileSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const root = process.cwd();
const reportDir = path.resolve("reports/2026-10-27/m5-02-target-config-api");
const scratch = await mkdtemp(path.join(tmpdir(), "harness-target-git-"));
const source = path.join(scratch, "source");
const bare = path.join(scratch, "remote.git");

function git(cwd, ...args) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

try {
  execFileSync("git", ["init", "-b", "main", source], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  git(source, "config", "user.name", "Smoke Fixture");
  git(source, "config", "user.email", "smoke@example.invalid");
  await writeFile(path.join(source, "README.md"), "target smoke\n", "utf8");
  git(source, "add", "README.md");
  git(source, "commit", "-m", "fixture");
  git(source, "tag", "v1.9.0");
  git(source, "tag", "v2.0.0");
  execFileSync("git", ["clone", "--bare", source, bare], {
    stdio: ["ignore", "pipe", "pipe"],
  });

  const python = path.join(root, "apps/api/.venv/bin/python");
  const probe = [
    "import asyncio, json",
    "from app.third_party_api.git.remote import SubprocessGitRemote",
    "async def main():",
    "    remote = SubprocessGitRemote(timeout_seconds=5)",
    "    await remote.validate(" + JSON.stringify(bare) + ", 'main')",
    "    print(json.dumps({'validated': True, 'tags': list(await remote.list_tags(" + JSON.stringify(bare) + "))}))",
    "asyncio.run(main())",
  ].join("\n");
  const output = execFileSync(python, ["-c", probe], {
    cwd: path.join(root, "apps/api"),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
  const result = JSON.parse(output);
  if (result.validated !== true || result.tags.join(",") !== "v1.9.0,v2.0.0") {
    throw new Error(`unexpected git smoke result: ${output}`);
  }
  await writeFile(
    path.join(reportDir, "git-smoke.json"),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify(result));
} finally {
  await rm(scratch, { recursive: true, force: true });
}
