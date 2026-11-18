<script setup lang="ts">
import type { BadCase } from "@harness/contracts";
import { computed, nextTick, watch } from "vue";

import EmptyState from "../ui/EmptyState.vue";
import ErrorState from "../ui/ErrorState.vue";
import LoadingSkeleton from "../ui/LoadingSkeleton.vue";
import {
  badCaseDeepLink,
  shortBadCaseId,
} from "../../utils/badCaseId";
import {
  badCaseFactEntries,
  badCaseState,
} from "./badCaseDisplay";
import { renderMarkdown } from "../../utils/markdown";

const props = withDefaults(
  defineProps<{
    wid: string;
    problems: BadCase[];
    activeBadCaseId?: string | null;
    loading?: boolean;
    error?: Error | null;
    compact?: boolean;
    showHeader?: boolean;
  }>(),
  {
    activeBadCaseId: null,
    loading: false,
    error: null,
    compact: false,
    showHeader: true,
  },
);

const emit = defineEmits<{
  retry: [];
  select: [badCaseId: string];
}>();

const count = computed(() => props.problems.length);

/**
 * Render one problem description as safe Markdown for the list card.
 * @param problem Read-only problem detail.
 * @returns Escaped HTML with hardened external links and no remote images.
 */
function reasonHtml(problem: BadCase): string {
  return renderMarkdown(problem.reason, { images: false });
}

function scrollToProblem(badCaseId: string) {
  const element = document.getElementById(`problem-row-${badCaseId}`);
  if (element && typeof element.scrollIntoView === "function") {
    element.scrollIntoView({ block: "nearest", behavior: "auto" });
  }
}

watch(
  () => props.activeBadCaseId,
  async (badCaseId) => {
    if (!badCaseId) return;
    await nextTick();
    scrollToProblem(badCaseId);
  },
);

defineExpose({ scrollToProblem });
</script>

<template>
  <section
    class="problem-list"
    :class="{ compact }"
    data-testid="problem-list"
    :aria-label="showHeader ? undefined : '问题列表'"
    :aria-labelledby="showHeader ? 'problem-list-title' : undefined"
  >
    <header
      v-if="showHeader"
      class="problem-list-head"
    >
      <strong id="problem-list-title">问题</strong>
      <span>{{ count }} 条</span>
    </header>
    <LoadingSkeleton
      v-if="loading"
      label="正在读取问题"
      :rows="2"
    />
    <ErrorState
      v-else-if="error"
      code="BAD_CASES_UNAVAILABLE"
      message="问题列表读取失败，请重试。"
      @retry="emit('retry')"
    />
    <EmptyState
      v-else-if="problems.length === 0"
      description="当前 Session 没有已上报问题。"
      title="暂无问题"
    />
    <div
      v-else
      class="problem-rows"
      role="list"
    >
      <div
        v-for="(problem, index) in problems"
        :id="`problem-row-${problem.badCaseId}`"
        :key="problem.badCaseId"
        class="problem-row-item"
        role="listitem"
      >
        <div
          class="problem-row-card"
          :class="{ active: problem.badCaseId === activeBadCaseId }"
        >
          <template v-if="compact">
            <div class="problem-card-content">
              <div class="problem-card-main">
                <span class="problem-no">#{{ index + 1 }}</span>
                <a
                  class="problem-id"
                  :href="badCaseDeepLink(
                    props.wid,
                    problem.sessionId,
                    problem.badCaseId,
                    'desc',
                  )"
                  :aria-label="`问题 ${shortBadCaseId(problem.badCaseId)}，在新窗口打开问题描述`"
                  rel="noopener noreferrer"
                  target="_blank"
                  :title="problem.badCaseId"
                >
                  {{ shortBadCaseId(problem.badCaseId) }}
                </a>
                <strong class="problem-card-title">{{ problem.title }}</strong>
              </div>
              <div class="problem-card-secondary">
                <span
                  class="state-chip"
                  :class="badCaseState(problem.analysis.displayState).tone"
                >
                  {{ badCaseState(problem.analysis.displayState).label }}
                </span>
                <span
                  v-if="problem.degraded"
                  class="degraded-chip"
                >
                  数据降级
                </span>
                <span class="problem-target">
                  {{ problem.objectType }} · {{ problem.objectName }}
                </span>
                <a
                  v-if="
                    problem.analysis.status === 'analyzed_issue' &&
                      problem.analysis.probeId
                  "
                  class="report-id"
                  :href="badCaseDeepLink(
                    props.wid,
                    problem.sessionId,
                    problem.badCaseId,
                    'attr',
                  )"
                  :aria-label="`归因报告 ${shortBadCaseId(problem.analysis.probeId)}，在新窗口打开归因分析`"
                  rel="noopener noreferrer"
                  target="_blank"
                  :title="problem.analysis.probeId"
                >
                  {{ shortBadCaseId(problem.analysis.probeId) }}
                </a>
              </div>
            </div>
            <button
              class="problem-row"
              :class="{ active: problem.badCaseId === activeBadCaseId }"
              :data-bad-case-id="problem.badCaseId"
              :aria-label="`选择问题 ${shortBadCaseId(problem.badCaseId)}：${problem.title}`"
              :aria-pressed="problem.badCaseId === activeBadCaseId"
              type="button"
              @click="emit('select', problem.badCaseId)"
            />
          </template>
          <template v-else>
            <span class="problem-no">BC{{ index + 1 }}</span>
            <div class="problem-card-content">
              <span class="problem-row-head">
                <strong>{{ problem.title }}</strong>
                <span
                  class="type-badge"
                  :class="problem.badCaseType"
                >{{ problem.badCaseType }}</span>
                <span class="object-badge">{{ problem.objectName }}</span>
                <a
                  class="problem-id"
                  :href="badCaseDeepLink(
                    props.wid,
                    problem.sessionId,
                    problem.badCaseId,
                    'desc',
                  )"
                  :aria-label="`问题 ${problem.badCaseId}，在新窗口打开问题描述`"
                  rel="noopener noreferrer"
                  target="_blank"
                  :title="problem.badCaseId"
                >
                  {{ problem.badCaseId }}
                </a>
                <span
                  class="state-chip"
                  :class="badCaseState(problem.analysis.displayState).tone"
                >
                  {{ badCaseState(problem.analysis.displayState).label }}
                </span>
                <span
                  v-if="problem.degraded"
                  class="degraded-chip"
                >
                  数据降级
                </span>
              </span>
              <!-- eslint-disable vue/no-v-html -- MarkdownIt raw HTML is disabled and links are hardened. -->
              <div
                v-if="problem.reason.trim()"
                class="problem-detail markdown"
                data-testid="problem-card-description"
                v-html="reasonHtml(problem)"
              />
              <!-- eslint-enable vue/no-v-html -->
              <span
                v-if="badCaseFactEntries(problem.metaData).length"
                class="problem-facts"
              >
                <span
                  v-for="fact in badCaseFactEntries(problem.metaData)"
                  :key="fact.key"
                  class="fact-chip"
                >
                  <span class="fact-key">{{ fact.key }}</span>
                  <span class="fact-value">{{ fact.value }}</span>
                </span>
              </span>
              <span class="problem-meta">
                关联：{{ problem.objectType }} · {{ problem.objectName }}
              </span>
            </div>
            <span class="locate-copy">定位 ↗</span>
            <button
              class="problem-row"
              :class="{ active: problem.badCaseId === activeBadCaseId }"
              :data-bad-case-id="problem.badCaseId"
              :aria-label="`选择问题 ${problem.badCaseId}：${problem.title}`"
              :aria-pressed="problem.badCaseId === activeBadCaseId"
              type="button"
              @click="emit('select', problem.badCaseId)"
            />
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.problem-list {
  display: grid;
  gap: 8px;
  padding: 10px 12px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
}

.problem-list-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  color: var(--text-dim);
  font-size: 12px;
}

.problem-list-head span {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
}

.problem-rows {
  display: grid;
  gap: 6px;
}

.problem-row-card {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text);
}

.problem-row {
  position: absolute;
  z-index: 1;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.problem-list.compact {
  display: block;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.problem-list.compact .problem-rows {
  gap: 8px;
}

.problem-list.compact .problem-row-card {
  display: block;
  border-left: 3px solid transparent;
}

.problem-list.compact .problem-row-card:hover {
  border-color: var(--border-strong);
}

.problem-list.compact .problem-row-card.active {
  border-color: var(--blue);
  border-left-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 7%, var(--bg-card));
  box-shadow: none;
}

.problem-list.compact .problem-row-card:has(.problem-row:focus-visible) {
  outline-color: var(--blue);
}

.problem-card-content {
  display: grid;
  flex: 1;
  gap: 5px;
  min-width: 0;
  pointer-events: none;
}

.problem-card-main,
.problem-card-secondary {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.problem-card-main {
  align-items: baseline;
  flex-wrap: nowrap;
}

.problem-card-title {
  min-width: 0;
  overflow: hidden;
  color: var(--text);
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.problem-card-secondary .problem-target {
  flex: 1;
}

.problem-card-content :deep(a) {
  position: relative;
  z-index: 2;
  pointer-events: auto;
}

.problem-row-card:hover {
  border-color: var(--red);
}

.problem-row-card.active {
  border-color: var(--red);
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--red) 12%, transparent);
}

.problem-row-card:has(.problem-row:focus-visible) {
  outline: 2px solid var(--red);
  outline-offset: 1px;
}

.problem-row-head {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.problem-row-head strong {
  min-width: 0;
  color: var(--text);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.problem-target {
  min-width: 0;
  color: var(--text-faint);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.problem-no,
.problem-id,
.report-id {
  font-family: var(--mono);
  font-weight: 650;
}

.problem-no {
  flex-shrink: 0;
  color: var(--red);
  font-size: 10px;
}

.problem-list:not(.compact) .problem-no {
  padding: 1px 8px;
  border: 1px solid var(--red);
  border-radius: 999px;
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
  font-size: 11px;
  font-weight: 700;
  line-height: 1.6;
}

.problem-id {
  flex-shrink: 1;
  min-width: 0;
  color: var(--blue);
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
  font-size: 10px;
  overflow-wrap: anywhere;
  text-decoration: none;
}

.problem-id:hover {
  border-bottom-style: solid;
}

.report-id {
  flex-shrink: 0;
  color: var(--purple);
  border-bottom: 1px dashed color-mix(in srgb, var(--purple) 45%, transparent);
  font-size: 10px;
  text-decoration: none;
}

.report-id:hover {
  border-bottom-style: solid;
}

.type-badge {
  padding: 1px 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}

.type-badge.self {
  color: var(--purple);
}

.type-badge.discovery {
  color: var(--blue);
}

.object-badge {
  max-width: 100%;
  overflow: hidden;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.problem-detail {
  margin-top: 3px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.problem-detail.markdown :deep(p) {
  margin: 0 0 5px;
}

.problem-detail.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.problem-detail.markdown :deep(ul),
.problem-detail.markdown :deep(ol) {
  margin: 2px 0 6px;
  padding-left: 17px;
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
  margin: 5px 0 7px;
  padding: 7px 9px;
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

.problem-detail.markdown :deep(em) {
  font-style: italic;
}

.problem-detail.markdown :deep(a) {
  color: var(--blue);
}

.problem-detail.markdown :deep(blockquote) {
  margin: 5px 0 7px;
  padding: 2px 0 2px 10px;
  border-left: 2px solid var(--border);
  color: var(--text-faint);
}

.problem-detail.markdown :deep(h1),
.problem-detail.markdown :deep(h2),
.problem-detail.markdown :deep(h3),
.problem-detail.markdown :deep(h4),
.problem-detail.markdown :deep(h5),
.problem-detail.markdown :deep(h6) {
  margin: 7px 0 3px;
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
}

.problem-detail.markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  margin: 5px 0 7px;
  border-collapse: collapse;
}

.problem-detail.markdown :deep(th),
.problem-detail.markdown :deep(td) {
  padding: 3px 6px;
  border: 1px solid var(--border);
  text-align: left;
}

.problem-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.problem-meta {
  color: var(--text-faint);
  font-size: 10.5px;
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

.state-chip,
.degraded-chip {
  padding: 1px 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}

.state-chip.neutral {
  color: var(--text-faint);
}

.state-chip.green {
  color: var(--green);
}

.state-chip.purple {
  color: var(--purple);
}

.state-chip.orange,
.degraded-chip {
  color: var(--orange);
}

.state-chip.red {
  color: var(--red);
}

.degraded-chip {
  background: color-mix(in srgb, var(--orange) 8%, var(--bg-card));
}

.locate-copy {
  flex-shrink: 0;
  color: var(--blue);
  font-size: 10.5px;
  white-space: nowrap;
}
</style>
