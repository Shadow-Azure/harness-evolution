<script setup lang="ts">
import type { AttributionItem } from "@harness/contracts";
import { computed } from "vue";

import { formatStartedAt } from "../../../utils/sessionDisplay";
import { badCaseDeepLink } from "../../../utils/badCaseId";
import { attributionConclusion } from "./attributionDisplay";

const props = defineProps<{
  wid: string;
  sessionId: string;
  badCaseId: string;
  attribution: AttributionItem;
  active: boolean;
}>();

const conclusion = computed(() =>
  attributionConclusion(props.attribution.conclusion),
);
const target = computed(() =>
  badCaseDeepLink(
    props.wid,
    props.sessionId,
    props.badCaseId,
    "attr",
    props.attribution.attributionId,
  ),
);
const version = computed(
  () => props.attribution.objectVersion ?? "版本未固定",
);
</script>

<template>
  <RouterLink
    class="attr-item"
    :class="{ active }"
    :to="target"
    data-testid="attribution-item"
    :data-attribution-id="attribution.attributionId"
    :aria-current="active ? 'page' : undefined"
    :title="`${attribution.objectName} · ${version} · ${conclusion.label}`"
  >
    <span
      class="ai-dot"
      :class="attribution.conclusion"
      aria-hidden="true"
    />
    <span class="ai-main">
      <span class="ai-obj">
        <b>{{ attribution.objectName }}</b>
        <span class="ver">{{ version }}</span>
      </span>
      <span class="ai-sub">
        {{ conclusion.label }} · {{ formatStartedAt(attribution.createdAt) }}
      </span>
    </span>
    <span class="ai-badges">
      <span
        v-if="attribution.isCached"
        class="badge cache"
        :title="`复用缓存归因 ${attribution.reusedCount} 次`"
      >缓存</span>
      <span
        class="badge"
        :class="conclusion.tone"
      >{{ conclusion.badge }}</span>
      <span
        class="ai-go"
        aria-hidden="true"
      >→</span>
    </span>
  </RouterLink>
</template>

<style scoped>
.attr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--text);
  text-decoration: none;
}

.attr-item:hover {
  border-color: var(--border-strong);
  background: var(--bg-card);
}

.attr-item.active {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
}

.attr-item:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 1px;
}

.ai-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
}

.ai-dot.attributed {
  background: var(--green);
}

.ai-dot.non_target,
.ai-dot.inconclusive {
  background: var(--orange);
}

.ai-main {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 1px;
}

.ai-obj {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 5px;
}

.ai-obj b {
  min-width: 0;
  overflow: hidden;
  color: var(--text);
  font-size: 11.5px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ver {
  flex-shrink: 0;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
}

.ai-sub {
  overflow: hidden;
  color: var(--text-faint);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-badges {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
}

.badge {
  padding: 0 5px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 9px;
  white-space: nowrap;
}

.badge.green {
  color: var(--green);
}

.badge.orange {
  color: var(--orange);
}

.badge.cache {
  border-color: var(--border);
  color: var(--text-faint);
}

.ai-go {
  color: var(--blue);
  font-size: 11px;
}
</style>
