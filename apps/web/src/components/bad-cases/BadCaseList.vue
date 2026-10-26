<script setup lang="ts">
import type { BadCase } from "@harness/contracts";
import { computed, nextTick, watch } from "vue";

import EmptyState from "../ui/EmptyState.vue";
import ErrorState from "../ui/ErrorState.vue";
import LoadingSkeleton from "../ui/LoadingSkeleton.vue";
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
  }>(),
  {
    activeBadCaseId: null,
    loading: false,
    error: null,
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
    data-testid="problem-list"
    aria-labelledby="problem-list-title"
  >
    <header class="problem-list-head">
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
        <button
          class="problem-row"
          :class="{ active: problem.badCaseId === activeBadCaseId }"
          :data-bad-case-id="problem.badCaseId"
          :aria-pressed="problem.badCaseId === activeBadCaseId"
          type="button"
          @click="emit('select', problem.badCaseId)"
        >
          <span class="problem-row-head">
            <span class="problem-no">#{{ index + 1 }}</span>
            <span
              class="problem-id"
              :title="problem.badCaseId"
            >
              {{ problem.badCaseId.slice(0, 8) }}
            </span>
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
          <span class="problem-summary">{{ badCaseSummary(problem) }}</span>
          <span class="problem-meta">
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

.problem-row {
  display: grid;
  gap: 5px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.problem-row:hover {
  border-color: var(--red);
}

.problem-row.active {
  border-color: var(--red);
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--red) 12%, transparent);
}

.problem-row:focus-visible {
  outline: 2px solid var(--red);
  outline-offset: 1px;
}

.problem-row-head,
.problem-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
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
  color: var(--red);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 650;
}

.problem-id {
  color: var(--text-faint);
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
