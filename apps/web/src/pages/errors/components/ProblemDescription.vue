<script setup lang="ts">
import type { AttributionItem, BadCase } from "@harness/contracts";
import { computed } from "vue";

import {
  badCaseAnchorPresentation,
  badCaseFactEntries,
} from "../../../components/bad-cases/badCaseDisplay";
import {
  badCaseDeepLink,
  shortBadCaseId,
} from "../../../utils/badCaseId";
import { renderMarkdown } from "../../../utils/markdown";

const props = withDefaults(
  defineProps<{
    wid: string;
    problem: BadCase;
    index: number | null;
    attributions?: AttributionItem[];
  }>(),
  { attributions: () => [] },
);

const emit = defineEmits<{
  openAttribution: [];
}>();

const facts = computed(() => badCaseFactEntries(props.problem.metaData));
const anchorPresentation = computed(() =>
  badCaseAnchorPresentation(props.problem.anchor),
);
const reporter = computed(() =>
  props.problem.badCaseAgent.agentId
    ? `${props.problem.badCaseType} · ${props.problem.badCaseAgent.agentId}`
    : `${props.problem.badCaseType} · 主 Agent`,
);
const attributedCount = computed(
  () =>
    props.attributions.filter(
      (attribution) => attribution.conclusion === "attributed",
    ).length,
);
const nonTargetCount = computed(
  () => props.attributions.length - attributedCount.value,
);
const hasAttributions = computed(() => props.problem.attributionCount > 0);
const descriptionLink = computed(() =>
  badCaseDeepLink(
    props.wid,
    props.problem.sessionId,
    props.problem.badCaseId,
    "desc",
  ),
);
const reasonHtml = computed(() =>
  renderMarkdown(props.problem.reason, { images: false }),
);
</script>

<template>
  <section
    class="description"
    aria-labelledby="problem-description-title"
  >
    <header class="problem-heading">
      <span
        v-if="index !== null"
        class="problem-number"
      >#{{ index }}</span>
      <a
        class="problem-id"
        :href="descriptionLink"
        :aria-label="`问题 ${shortBadCaseId(problem.badCaseId)}，在新窗口打开问题描述`"
        rel="noopener noreferrer"
        target="_blank"
        :title="problem.badCaseId"
      >
        {{ shortBadCaseId(problem.badCaseId) }}
      </a>
      <span
        id="problem-description-title"
        class="problem-title"
      >{{ problem.title }}</span>
      <span
        class="type-badge"
        :class="problem.badCaseType"
      >{{ problem.badCaseType }}</span>
      <span
        v-if="problem.degraded"
        class="degraded-chip"
      >
        数据降级
      </span>
    </header>

    <div class="problem-meta">
      <span class="meta-chip">
        object_name · {{ problem.objectName }}
        <template v-if="problem.objectVersion">
          @{{ problem.objectVersion }}
        </template>
      </span>
      <span class="meta-chip">{{ problem.objectType }}</span>
      <button
        v-if="hasAttributions"
        type="button"
        class="attribution-summary"
        data-testid="problem-attribution-summary"
        @click="emit('openAttribution')"
      >
        已生成 {{ problem.attributionCount }} 条归因
        <template v-if="attributions.length === problem.attributionCount">
          · {{ attributedCount }} 可归因<template v-if="nonTargetCount">
            / {{ nonTargetCount }} 非该对象
          </template>
        </template>
        →
      </button>
      <span
        v-else
        class="attribution-summary empty"
        data-testid="problem-attribution-summary"
      >尚未归因</span>
      <span
        v-if="anchorPresentation"
        class="anchor-chip"
        :class="anchorPresentation.tone"
        data-testid="problem-anchor"
        :title="anchorPresentation.description"
      >
        {{ anchorPresentation.label }}
      </span>
    </div>

    <!-- eslint-disable vue/no-v-html -- MarkdownIt raw HTML is disabled and links are hardened. -->
    <div
      class="problem-detail markdown"
      data-testid="problem-detail"
      v-html="reasonHtml"
    />
    <!-- eslint-enable vue/no-v-html -->
    <div
      v-if="facts.length"
      class="facts-block"
    >
      <div class="facts">
        <span
          v-for="fact in facts"
          :key="fact.key"
          class="fact-chip"
        >
          <span class="fact-key">{{ fact.key }}</span>
          <span class="fact-value">{{ fact.value }}</span>
        </span>
      </div>
    </div>
    <div class="association">
      关联：{{ reporter }} · {{ problem.objectType }} · {{ problem.objectName }}
      <span v-if="problem.objectVersion">@{{ problem.objectVersion }}</span>
      · 会话：{{ problem.sessionTitle }}
    </div>
    <p
      v-if="problem.degraded"
      class="diagnostic"
    >
      外部字段存在漂移，当前以安全占位展示。
    </p>
  </section>
</template>

<style scoped>
.description {
  display: grid;
  gap: 0;
  padding: 14px 18px 18px;
}

.problem-heading {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.problem-detail {
  margin-top: 9px;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.7;
}

.problem-detail.markdown :deep(p) {
  margin: 0 0 7px;
}

.problem-detail.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.problem-detail.markdown :deep(ul),
.problem-detail.markdown :deep(ol) {
  margin: 3px 0 9px;
  padding-left: 18px;
}

.problem-detail.markdown :deep(li) {
  margin: 1px 0;
}

.problem-detail.markdown :deep(li:last-child) {
  margin-bottom: 0;
}

.problem-detail.markdown :deep(code) {
  padding: 0 4px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-inset);
  color: var(--text);
  font-family: var(--mono);
  font-size: 10.5px;
  overflow-wrap: anywhere;
}

.problem-detail.markdown :deep(pre) {
  overflow-x: auto;
  margin: 6px 0 9px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
}

.problem-detail.markdown :deep(pre code) {
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 10.5px;
  line-height: 1.55;
  white-space: pre;
}

.problem-detail.markdown :deep(strong) {
  color: var(--text);
  font-weight: 650;
}

.problem-detail.markdown :deep(a) {
  color: var(--blue);
}

.problem-detail.markdown :deep(h1),
.problem-detail.markdown :deep(h2),
.problem-detail.markdown :deep(h3),
.problem-detail.markdown :deep(h4),
.problem-detail.markdown :deep(h5),
.problem-detail.markdown :deep(h6) {
  margin: 9px 0 4px;
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
}

.problem-detail.markdown :deep(h1:first-child),
.problem-detail.markdown :deep(h2:first-child),
.problem-detail.markdown :deep(h3:first-child),
.problem-detail.markdown :deep(h4:first-child),
.problem-detail.markdown :deep(h5:first-child),
.problem-detail.markdown :deep(h6:first-child) {
  margin-top: 0;
}

.problem-detail.markdown :deep(em) {
  font-style: italic;
}

.problem-detail.markdown :deep(blockquote) {
  margin: 6px 0 9px;
  padding: 2px 0 2px 10px;
  border-left: 2px solid var(--border);
  color: var(--text-faint);
}

.problem-detail.markdown :deep(hr) {
  margin: 9px 0;
  border: 0;
  border-top: 1px solid var(--border);
}

.problem-detail.markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  margin: 6px 0 9px;
  border-collapse: collapse;
}

.problem-detail.markdown :deep(th),
.problem-detail.markdown :deep(td) {
  padding: 3px 6px;
  border: 1px solid var(--border);
  text-align: left;
}

.problem-detail.markdown :deep(img) {
  max-width: 100%;
  height: auto;
}

.problem-number,
.problem-id {
  flex-shrink: 0;
  font-family: var(--mono);
  font-weight: 700;
}

.problem-number {
  padding: 1px 8px;
  border: 1px solid var(--red);
  border-radius: 999px;
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
  color: var(--red);
  font-size: 11px;
}

.problem-id {
  color: var(--blue);
  font-size: 10.5px;
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
  text-decoration: none;
}

.problem-id:hover {
  border-bottom-style: solid;
}

.problem-title {
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

.type-badge {
  padding: 1px 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
}

.type-badge.self {
  color: var(--purple);
}

.type-badge.discovery {
  color: var(--blue);
}

.problem-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 7px;
}

.meta-chip {
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-inset);
  color: var(--text-faint);
  font-size: 10px;
}

.attribution-summary {
  padding: 1px 7px;
  border: 1px solid var(--green);
  border-radius: 999px;
  background: color-mix(in srgb, var(--green) 7%, var(--bg-card));
  color: var(--green);
  cursor: pointer;
  font: inherit;
  font-size: 10px;
}

.attribution-summary:hover {
  background: color-mix(in srgb, var(--green) 13%, var(--bg-card));
}

.attribution-summary.empty {
  border-color: var(--orange);
  background: color-mix(in srgb, var(--orange) 7%, var(--bg-card));
  color: var(--orange);
  cursor: default;
}

.anchor-chip {
  padding: 1px 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}

.anchor-chip.orange {
  background: color-mix(in srgb, var(--orange) 7%, transparent);
  color: var(--orange);
}

.anchor-chip.neutral {
  color: var(--text-faint);
}

.degraded-chip {
  padding: 1px 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  background: color-mix(in srgb, var(--orange) 8%, var(--bg-card));
  color: var(--orange);
  font-size: 10px;
}

.facts-block {
  margin-top: 6px;
}

.facts {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.fact-chip {
  display: inline-flex;
  align-items: flex-start;
  gap: 5px;
  max-width: 100%;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-inset);
  font-size: 10.5px;
  line-height: 1.5;
}

.fact-key {
  flex-shrink: 0;
  color: var(--text-faint);
}

.fact-value {
  min-width: 0;
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10px;
  overflow-wrap: anywhere;
}

.diagnostic {
  margin: 8px 0 0;
  color: var(--orange);
  font-size: 11.5px;
}

.association {
  margin-top: 8px;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}
</style>
