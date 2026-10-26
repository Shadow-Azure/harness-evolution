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
  badCaseFacts,
  badCaseState,
  badCaseSummary,
} from "./badCaseDisplay";

const props = withDefaults(
  defineProps<{
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
          <span class="problem-no">#{{ index + 1 }}</span>
          <a
            class="problem-id"
            :href="badCaseDeepLink(
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
          <button
            class="problem-row"
            :class="{ active: problem.badCaseId === activeBadCaseId }"
            :data-bad-case-id="problem.badCaseId"
            :aria-pressed="problem.badCaseId === activeBadCaseId"
            type="button"
            @click="emit('select', problem.badCaseId)"
          >
            <span class="problem-row-head">
              <strong>{{ problem.reason }}</strong>
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
            <span class="compact-row-bottom">
              <span
                v-if="compact"
                class="problem-target"
              >
                {{ problem.objectType }} · {{ problem.objectName }}
              </span>
            </span>
            <span
              v-if="!compact"
              class="problem-summary"
            >{{ badCaseSummary(problem) }}</span>
            <span
              v-if="!compact"
              class="problem-meta"
            >
              <span>{{ problem.objectType }} · {{ problem.objectName }}</span>
              <span
                v-for="fact in badCaseFacts(problem.metaData)"
                :key="fact"
                class="fact-chip"
              >
                {{ fact }}
              </span>
              <span class="locate-copy">定位</span>
            </span>
          </button>
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
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  gap: 5px 6px;
  align-items: start;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text);
}

.problem-row {
  display: grid;
  grid-column: 3;
  gap: 5px;
  min-width: 0;
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

.problem-row-head,
.compact-row-top,
.compact-row-bottom,
.problem-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.compact-row-top {
  align-items: baseline;
  flex-wrap: nowrap;
}

.compact-row-top strong {
  min-width: 0;
  overflow: hidden;
  font-size: 12.5px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-row-bottom {
  gap: 6px;
  flex-wrap: wrap;
}

.problem-target {
  min-width: 0;
  color: var(--text-faint);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.problem-row-head strong {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.problem-no,
.problem-id {
  flex-shrink: 0;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 650;
}

.problem-no {
  color: var(--red);
}

.problem-id {
  color: var(--blue);
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
  text-decoration: none;
}

.problem-id:hover {
  border-bottom-style: solid;
}

.problem-summary {
  color: var(--text-dim);
  font-size: 11.5px;
  line-height: 1.5;
}

.problem-meta {
  color: var(--text-faint);
  font-size: 10.5px;
}

.fact-chip {
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-inset);
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
  margin-left: auto;
  color: var(--blue);
}
</style>
