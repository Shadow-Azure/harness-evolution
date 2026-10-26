<script setup lang="ts">
import { Handle, Position } from "@vue-flow/core";
import { inject } from "vue";

import { BAD_CASE_SELECT_KEY } from "../interactions";
import type { BadCaseLayoutNodeData } from "../types";

const props = defineProps<{
  data: BadCaseLayoutNodeData;
}>();

const selectBadCase = inject(BAD_CASE_SELECT_KEY, null);

function onSelect() {
  selectBadCase?.(props.data.badCaseId);
}
</script>

<template>
  <button
    class="rf-finding"
    :class="[`state-${data.displayState}`, { active: data.active, degraded: data.degraded }]"
    :data-bad-case-id="data.badCaseId"
    :aria-label="`问题 ${data.shortId}: ${data.reason}`"
    :aria-pressed="Boolean(data.active)"
    :title="`${data.badCaseId} · ${data.reason}`"
    type="button"
    @click.stop="onSelect"
  >
    <span class="finding-id">{{ data.shortId }}</span>
    <span class="finding-reason">{{ data.reason }}</span>
    <span
      v-if="data.degraded"
      class="finding-degraded"
    >
      降级
    </span>
    <Handle
      id="card-left"
      type="target"
      :position="Position.Left"
      class="hidden-handle"
    />
    <Handle
      id="card-right"
      type="target"
      :position="Position.Right"
      class="hidden-handle"
    />
    <Handle
      id="card-top"
      type="target"
      :position="Position.Top"
      class="hidden-handle"
    />
    <Handle
      id="card-bottom"
      type="target"
      :position="Position.Bottom"
      class="hidden-handle"
    />
  </button>
</template>

<style scoped>
.rf-finding {
  display: flex;
  width: 230px;
  height: 30px;
  align-items: center;
  gap: 6px;
  box-sizing: border-box;
  padding: 3px 8px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--red) 62%, var(--border));
  border-radius: 6px;
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
  box-shadow: 0 1px 2px color-mix(in srgb, var(--red) 12%, transparent);
  color: var(--red);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.rf-finding.active {
  border-color: var(--red);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--red) 18%, transparent);
}

.rf-finding:focus-visible {
  outline: 2px solid var(--red);
  outline-offset: 2px;
}

.finding-id {
  flex-shrink: 0;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 650;
}

.finding-reason {
  min-width: 0;
  overflow: hidden;
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.finding-degraded {
  flex-shrink: 0;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--state-error-surface);
  font-size: 9px;
}

.hidden-handle {
  width: 6px;
  height: 6px;
  border: 0;
  background: transparent;
  opacity: 0;
}
</style>
