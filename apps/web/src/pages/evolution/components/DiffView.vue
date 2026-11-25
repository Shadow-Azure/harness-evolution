<script setup lang="ts">
import { computed } from "vue";
import type { StepRoundPatch } from "@harness/contracts";

const props = defineProps<{
  patch: StepRoundPatch;
}>();

type DiffRowKind = "add" | "del" | "hunk" | "ctx";

interface DiffRow {
  text: string;
  kind: DiffRowKind;
}

interface DiffFile {
  key: string;
  header: string;
  rows: DiffRow[];
}

const DIFF_GIT_HEADER = /^diff --git a\/(.+) b\/(.+)$/;
const FILE_META_PREFIXES = [
  "index ",
  "new file mode ",
  "deleted file mode ",
  "similarity index ",
  "dissimilarity index ",
  "rename from ",
  "rename to ",
  "old mode ",
  "new mode ",
  "Binary files ",
  "\\ No newline at end of file",
];

const files = computed(() => props.patch.files ?? []);
const diff = computed(() => props.patch.diff ?? []);
const hasDiff = computed(() => diff.value.length > 0);

/**
 * Split the real unified diff into file blocks.
 *
 * A file header row comes from `diff --git`, while the plumbing lines (`---`,
 * `+++`, `index`, mode/rename metadata) are dropped. That distinction matters:
 * a removed content line may itself start with `---`, so those header lines
 * are only skipped before the first hunk of a file.
 */
const diffFiles = computed<DiffFile[]>(() => {
  const parsed: DiffFile[] = [];
  let current: DiffFile | null = null;
  let hunkSeen = false;

  for (const line of diff.value) {
    const header = DIFF_GIT_HEADER.exec(line);
    if (header) {
      current = {
        key: String(parsed.length),
        header: header[2] ?? header[1] ?? line,
        rows: [],
      };
      parsed.push(current);
      hunkSeen = false;
      continue;
    }
    if (current === null) {
      current = {
        key: `fallback-${parsed.length}`,
        header: files.value[0]?.file ?? "",
        rows: [],
      };
      parsed.push(current);
      hunkSeen = false;
    }
    if (!hunkSeen && (line.startsWith("--- ") || line.startsWith("+++ "))) continue;
    if (FILE_META_PREFIXES.some((prefix) => line.startsWith(prefix))) continue;
    if (line.startsWith("@@")) hunkSeen = true;
    current.rows.push({ text: line, kind: rowKind(line) });
  }
  return parsed;
});

function rowKind(line: string): DiffRowKind {
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "ctx";
}
</script>

<template>
  <div class="diff">
    <template v-if="hasDiff">
      <div
        v-for="file in diffFiles"
        :key="file.key"
        class="file"
      >
        <div
          v-if="file.header"
          class="fhead"
        >
          {{ file.header }}
        </div>
        <div
          v-for="(row, index) in file.rows"
          :key="`${index}-${row.text}`"
          class="dline"
          :class="row.kind"
        >
          {{ row.text }}
        </div>
        <div
          v-if="file.rows.length === 0"
          class="empty-patch"
        >
          diff 内容为空
        </div>
      </div>
      <div
        v-if="diffFiles.length === 0"
        class="empty-patch"
      >
        diff 内容为空
      </div>
    </template>
    <template v-else>
      <div class="preview-note">
        无 diff 数据，以下为候选文件全文（整文件预览，不对行着色）
      </div>
      <div
        v-for="file in files"
        :key="file.file"
        class="file"
      >
        <div class="fhead">
          {{ file.file }}
        </div>
        <div
          v-for="(line, index) in file.lines"
          :key="`${index}-${line}`"
          class="dline preview"
        >
          {{ line }}
        </div>
        <div
          v-if="file.lines.length === 0"
          class="empty-patch"
        >
          patch 内容为空
        </div>
      </div>
      <div
        v-if="files.length === 0"
        class="empty-patch"
      >
        patch 内容为空
      </div>
    </template>
  </div>
</template>

<style scoped>
.diff {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: var(--mono);
  font-size: 11.5px;
}

.file + .file {
  border-top: 1px solid var(--border);
}

.fhead {
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  color: var(--text-dim);
  font-size: 11px;
}

.preview-note {
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  color: var(--text-faint);
  font-size: 11px;
}

.dline {
  padding: 1px 10px;
  white-space: pre-wrap;
  word-break: break-all;
}

.dline.add {
  background: color-mix(in srgb, var(--green) 11%, transparent);
  color: var(--diff-add-text);
}

.dline.del {
  background: color-mix(in srgb, var(--red) 9%, transparent);
  color: var(--diff-del-text);
}

.dline.hunk {
  background: color-mix(in srgb, var(--blue) 7%, transparent);
  color: var(--blue);
}

.dline.ctx {
  color: var(--text-dim);
}

.dline.preview {
  color: var(--text-dim);
}

.empty-patch {
  padding: 10px;
  color: var(--text-faint);
}
</style>
