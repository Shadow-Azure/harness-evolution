import { createReadStream } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import readline from "node:readline";
import { parseSessionMeta, toRecord } from "./meta";
import type {
  RolloutFileRef,
  RolloutRecord,
  RolloutSessionMeta,
  SnapshotSource,
} from "./types";

async function collectJsonl(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await collectJsonl(full)));
    else if (entry.isFile() && entry.name.endsWith(".jsonl")) files.push(full);
  }
  return files;
}

async function firstLine(file: string): Promise<string> {
  const stream = createReadStream(file, { encoding: "utf8" });
  const lines = readline.createInterface({ input: stream, crlfDelay: Infinity });
  try {
    for await (const line of lines) return line;
    return "";
  } finally {
    lines.close();
    stream.destroy();
  }
}

/**
 * Create a Node filesystem snapshot source.
 * @param sessionsRoot Directory containing Codex rollout JSONL files.
 * @returns Snapshot source rooted at the directory.
 */
export function createNodeSnapshotSource(sessionsRoot: string): SnapshotSource {
  const root = path.resolve(sessionsRoot);
  const resolveFile = (rolloutId: string): string => {
    const file = path.resolve(root, rolloutId);
    if (file !== root && !file.startsWith(`${root}${path.sep}`)) {
      throw new Error(`rolloutId escapes sessions root: ${rolloutId}`);
    }
    return file;
  };
  return {
    async listRollouts(): Promise<readonly RolloutFileRef[]> {
      const files = await collectJsonl(root);
      const refs = await Promise.all(
        files.map(async (file) => {
          const info = await stat(file);
          return {
            rolloutId: path.relative(root, file).split(path.sep).join("/"),
            byteCount: info.size,
            modifiedAt: info.mtime.toISOString(),
          };
        }),
      );
      return refs.sort((left, right) => left.rolloutId.localeCompare(right.rolloutId));
    },
    async readMeta(rolloutId: string): Promise<RolloutSessionMeta> {
      const line = await firstLine(resolveFile(rolloutId));
      const meta = parseSessionMeta(line, rolloutId);
      if (!meta) throw new Error(`invalid session_meta: ${rolloutId}`);
      return meta;
    },
    async readRecords(rolloutId: string): Promise<readonly RolloutRecord[]> {
      const text = await readFile(resolveFile(rolloutId), "utf8");
      return text
        .split("\n")
        .map((line, index) => (line.length > 0 ? toRecord(rolloutId, line, index + 1) : null))
        .filter((record): record is RolloutRecord => record !== null);
    },
  };
}
