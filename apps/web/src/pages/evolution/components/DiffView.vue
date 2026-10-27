<script setup lang="ts">
import type { StepRoundPatch } from "@harness/contracts";

defineProps<{
  patch: StepRoundPatch;
}>();

function lineClass(line: string): string {
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  if (line.startsWith("@@")) return "hunk";
  return "ctx";
}
</script>

<template>
  <div class="diff">
    <div class="fhead">
      {{ patch.file }}
    </div>
    <div
      v-for="(line, index) in patch.lines"
      :key="`${index}-${line}`"
      class="dline"
      :class="lineClass(line)"
    >
      {{ line }}
    </div>
    <div
      v-if="patch.lines.length === 0"
      class="empty-patch"
    >
      patch 内容为空
    </div>
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

.fhead {
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  color: var(--text-dim);
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

.empty-patch {
  padding: 10px;
  color: var(--text-faint);
}
</style>
