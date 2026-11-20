<script setup lang="ts">
import type { AttributionItem } from "@harness/contracts";
import { computed, ref } from "vue";

import { formatStartedAt } from "../../../utils/sessionDisplay";
import { badCaseDeepLink } from "../../../utils/badCaseId";
import { attributionConclusion } from "./attributionDisplay";
import VersionLabel from "./VersionLabel.vue";
import { resolveVersionLabel } from "./versionLabel";

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
const versionInfo = computed(() =>
  resolveVersionLabel(
    props.attribution.objectVersion,
    props.attribution.objectRef,
    props.attribution.objectCommit,
  ),
);
const linkLabel = computed(
  () => `${props.attribution.objectName} · ${versionInfo.value.full} · ${conclusion.value.label}`,
);
const versionLabel = ref<InstanceType<typeof VersionLabel> | null>(null);

function showVersionTip(): void {
  versionLabel.value?.showTip();
}

function hideVersionTip(): void {
  versionLabel.value?.hideTip();
}
</script>

<template>
  <div
    class="attr-item"
    :class="{ active }"
    data-testid="attribution-item"
    :data-attribution-id="attribution.attributionId"
    @mouseenter="showVersionTip"
    @mouseleave="hideVersionTip"
    @focusin="showVersionTip"
    @focusout="hideVersionTip"
  >
    <RouterLink
      class="attr-link"
      :to="target"
      :aria-current="active ? 'page' : undefined"
      :aria-label="linkLabel"
    />
    <span
      class="ai-dot"
      :class="attribution.conclusion"
      aria-hidden="true"
    />
    <span class="ai-main">
      <span class="ai-obj">
        <b aria-hidden="true">{{ attribution.objectName }}</b>
        <VersionLabel
          ref="versionLabel"
          :version="attribution.objectVersion"
          :object-ref="attribution.objectRef"
          :object-commit="attribution.objectCommit"
        />
      </span>
      <span
        class="ai-sub"
        aria-hidden="true"
      >
        {{ conclusion.label }} · {{ formatStartedAt(attribution.createdAt) }}
      </span>
    </span>
    <span
      class="ai-badges"
      aria-hidden="true"
    >
      <span class="ai-badge-stack">
        <span
          v-if="attribution.isCached"
          class="badge cache"
          :title="`复用缓存归因 ${attribution.reusedCount} 次`"
        >缓存</span>
        <span
          class="badge"
          :class="conclusion.tone"
        >{{ conclusion.badge }}</span>
      </span>
      <span
        class="ai-go"
        aria-hidden="true"
      >→</span>
    </span>
  </div>
</template>

<style scoped>
.attr-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--text);
}

.attr-link {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: 7px;
}

.attr-link:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: -1px;
}

.attr-item:hover {
  border-color: var(--border-strong);
  background: var(--bg-card);
}

.attr-item.active {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
}

.attr-item > .ai-dot,
.attr-item > .ai-main,
.attr-item > .ai-badges {
  position: relative;
  z-index: 1;
  pointer-events: none;
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

.ai-dot.non_target {
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
  gap: 3px;
}

.ai-obj b {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 54%;
  overflow: hidden;
  color: var(--text);
  font-size: 11.5px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-sub {
  overflow: hidden;
  color: var(--text-faint);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-badges {
  position: relative;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 2px;
  padding-right: 8px;
}

.ai-badge-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
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
  position: absolute;
  right: 0;
  bottom: 0;
  color: var(--blue);
  font-size: 11px;
  line-height: 1;
}
</style>
