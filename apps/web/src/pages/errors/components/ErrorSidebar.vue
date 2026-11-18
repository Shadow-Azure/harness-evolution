<script setup lang="ts">
import type { BadCase, SessionListItem } from "@harness/contracts";
import { computed, ref, watch } from "vue";

import EmptyState from "../../../components/ui/EmptyState.vue";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { workspacePath } from "../../../router/workspace";
import { shortBadCaseId } from "../../../utils/badCaseId";
import CaseGroup from "./CaseGroup.vue";
import { traceStatusLabel, type TraceStatusDetails } from "../traceStatus";

type Filter = "all" | "attr" | "none";

const props = defineProps<{
  wid: string;
  problems: BadCase[];
  session: SessionListItem | null;
  sessionId: string;
  activeBadCaseId: string | null;
  selectedAttributionId: string | null;
  selectedAttributionPage: number | null;
  loading: boolean;
  error: Error | null;
  canStart: boolean;
  trace: TraceStatusDetails | null;
  traceAttributionCount: number;
  traceAttributionLoading: boolean;
  traceAttributionError: boolean;
}>();

const emit = defineEmits<{
  retry: [];
  "retry-attributions": [];
  start: [badCaseId: string];
}>();

const filter = ref<Filter>("all");
const expanded = ref<Set<string>>(new Set());
const pages = ref<Record<string, number>>({});

const traceLabel = computed(() =>
  props.trace ? traceStatusLabel(props.trace.syncStatus) : "",
);
const sidebarTitle = computed(
  () =>
    props.trace?.title ||
    props.session?.title ||
    props.problems[0]?.sessionTitle ||
    props.sessionId,
);
const sidebarCount = computed(() =>
  props.trace ? 1 : props.problems.length,
);
const attributedCount = computed(
  () => props.problems.filter((problem) => problem.attributionCount > 0).length,
);
const pendingCount = computed(
  () => props.problems.length - attributedCount.value,
);
const problemIndex = computed(
  () =>
    new Map(
      props.problems.map((problem, index) => [problem.badCaseId, index + 1]),
    ),
);
const visibleProblems = computed(() =>
  props.problems.filter((problem) => {
    if (filter.value === "attr") return problem.attributionCount > 0;
    if (filter.value === "none") return problem.attributionCount === 0;
    return true;
  }),
);
const allErrorsLink = computed(() =>
  workspacePath(
    props.wid,
    `sessions/${encodeURIComponent(props.sessionId)}/errors`,
  ),
);

watch(
  [() => props.activeBadCaseId, () => props.selectedAttributionPage],
  ([badCaseId, selectedPage]) => {
    if (!badCaseId) return;
    if (!expanded.value.has(badCaseId)) {
      const next = new Set(expanded.value);
      next.add(badCaseId);
      expanded.value = next;
    }
    if (
      selectedPage !== null &&
      pages.value[badCaseId] !== selectedPage
    ) {
      pages.value = { ...pages.value, [badCaseId]: selectedPage };
    } else if (pages.value[badCaseId] === undefined) {
      pages.value = { ...pages.value, [badCaseId]: 1 };
    }
  },
  { immediate: true },
);

watch(
  () => props.wid,
  () => {
    filter.value = "all";
    expanded.value = new Set();
    pages.value = {};
  },
);

function isExpanded(badCaseId: string): boolean {
  return expanded.value.has(badCaseId);
}

function toggle(badCaseId: string): void {
  const next = new Set(expanded.value);
  if (next.has(badCaseId)) {
    next.delete(badCaseId);
  } else {
    next.add(badCaseId);
    if (pages.value[badCaseId] === undefined) {
      pages.value = { ...pages.value, [badCaseId]: 1 };
    }
  }
  expanded.value = next;
}

function pageOf(badCaseId: string): number {
  return pages.value[badCaseId] ?? 1;
}

function setPage(badCaseId: string, page: number): void {
  pages.value = { ...pages.value, [badCaseId]: Math.max(1, page) };
}

function setFilter(next: Filter): void {
  filter.value = next;
}
</script>

<template>
  <aside
    class="error-sidebar"
    aria-label="bad case 列表"
  >
    <header class="sidebar-heading">
      <div class="sidebar-title">
        <h1>bad case</h1>
        <span class="count">{{ sidebarCount }} 个</span>
      </div>
      <div
        class="session-title"
        :title="sidebarTitle"
      >
        {{ sidebarTitle }}
      </div>
      <div
        class="session-id"
        data-testid="error-root-session-id"
        :title="`根会话 ID: ${sessionId}`"
      >
        根会话 ID · {{ sessionId }}
      </div>
      <RouterLink
        v-if="!trace || session"
        class="sidebar-back"
        :to="workspacePath(wid, `sessions/${encodeURIComponent(sessionId)}`)"
      >
        ← 返回 Session
      </RouterLink>
      <span
        v-else
        class="sidebar-back is-disabled"
        aria-disabled="true"
        data-testid="sidebar-back-unavailable"
        title="Session 尚未落库"
      >
        ← 返回 Session
      </span>
    </header>

    <div
      v-if="!trace"
      class="sidebar-filter"
      role="group"
      aria-label="筛选 bad case"
    >
      <button
        type="button"
        class="chip"
        :class="{ active: filter === 'all' }"
        :aria-pressed="filter === 'all'"
        @click="setFilter('all')"
      >
        全部
      </button>
      <button
        type="button"
        class="chip"
        :class="{ active: filter === 'attr' }"
        :aria-pressed="filter === 'attr'"
        @click="setFilter('attr')"
      >
        有归因 {{ attributedCount }}
      </button>
      <button
        type="button"
        class="chip"
        :class="{ active: filter === 'none' }"
        :aria-pressed="filter === 'none'"
        @click="setFilter('none')"
      >
        待归因 {{ pendingCount }}
      </button>
    </div>

    <div class="sidebar-list">
      <section
        v-if="trace"
        class="trace-case"
        data-testid="trace-case-sidebar"
      >
        <div class="trace-case-head">
          <span
            class="case-id"
            :title="trace.badCaseId"
          >{{ shortBadCaseId(trace.badCaseId) }}</span>
          <span
            v-if="trace.objectName"
            class="object-name"
          >{{ trace.objectName }}</span>
          <span
            class="trace-status-chip"
            :class="`trace-${trace.syncStatus}`"
            data-testid="sidebar-trace-status"
          >{{ traceLabel }}</span>
        </div>
        <div class="attr-list-title">
          归因分析 · 按进化对象
        </div>
        <LoadingSkeleton
          v-if="traceAttributionLoading"
          label="正在读取归因"
          :rows="2"
        />
        <ErrorState
          v-else-if="traceAttributionError"
          code="ATTRIBUTIONS_UNAVAILABLE"
          message="归因列表读取失败，请重试。"
          @retry="emit('retry-attributions')"
        />
        <div
          v-else-if="traceAttributionCount === 0"
          class="attr-empty"
          data-testid="trace-case-attributions-empty"
        >
          暂无归因。尚未进入自进化。
        </div>
        <div
          v-else
          class="trace-case-count"
          data-testid="trace-case-attributions-count"
        >
          {{ traceAttributionCount }} 条归因
        </div>
      </section>
      <template v-else>
        <RouterLink
          class="all-errors"
          :class="{ active: activeBadCaseId === null }"
          :to="allErrorsLink"
          data-testid="all-bad-cases"
        >
          <span>全部 bad case</span>
          <b>{{ problems.length }}</b>
        </RouterLink>
        <LoadingSkeleton
          v-if="loading"
          label="正在读取 bad case"
          :rows="3"
        />
        <ErrorState
          v-else-if="error"
          code="BAD_CASES_UNAVAILABLE"
          message="bad case 列表读取失败，请重试。"
          @retry="emit('retry')"
        />
        <EmptyState
          v-else-if="visibleProblems.length === 0"
          description="当前筛选条件下没有 bad case。"
          title="没有匹配的 bad case"
        />
        <template v-else>
          <CaseGroup
            v-for="(problem, index) in visibleProblems"
            :key="problem.badCaseId"
            :wid="wid"
            :session-id="sessionId"
            :problem="problem"
            :index="problemIndex.get(problem.badCaseId) ?? index + 1"
            :expanded="isExpanded(problem.badCaseId)"
            :page="pageOf(problem.badCaseId)"
            :active="problem.badCaseId === activeBadCaseId"
            :selected-attribution-id="selectedAttributionId"
            :can-start="canStart"
            @toggle="toggle(problem.badCaseId)"
            @page="setPage(problem.badCaseId, $event)"
            @start="emit('start', problem.badCaseId)"
          />
        </template>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.error-sidebar {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
}

.sidebar-heading {
  display: grid;
  gap: 3px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border);
}

.sidebar-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.sidebar-title h1 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  font-weight: 650;
}

.count {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 11.5px;
}

.session-title,
.session-id {
  overflow: hidden;
  color: var(--text-dim);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-id {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}

.sidebar-back {
  width: fit-content;
  margin-top: 5px;
  color: var(--blue);
  font-size: 11.5px;
  text-decoration: none;
}

.sidebar-back:hover {
  text-decoration: underline;
}

.sidebar-back.is-disabled {
  color: var(--text-faint);
  cursor: default;
}

.sidebar-back.is-disabled:hover {
  text-decoration: none;
}

.sidebar-filter {
  display: flex;
  gap: 4px;
  padding: 8px 10px 0;
}

.chip {
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 10px;
}

.chip.active,
.chip:hover {
  border-color: var(--blue);
  color: var(--text);
}

.chip.active {
  background: color-mix(in srgb, var(--blue) 9%, var(--bg-card));
}

.sidebar-list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding: 10px;
}

.all-errors {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font-size: 12px;
  text-decoration: none;
}

.all-errors.active,
.all-errors:hover {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
  color: var(--text);
}

.all-errors b {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 11px;
}

.trace-status-chip {
  width: fit-content;
  padding: 1px 8px;
  border: 1px solid currentColor;
  border-radius: 999px;
  color: var(--orange);
  font-size: 10px;
  white-space: nowrap;
}

.trace-status-chip.trace-ready {
  color: var(--green);
}

.trace-case {
  display: grid;
  gap: 9px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-card);
}

.trace-case-head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.case-id {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 11px;
}

.object-name {
  overflow: hidden;
  max-width: 130px;
  color: var(--text-faint);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attr-list-title {
  color: var(--text-faint);
  font-size: 10px;
  letter-spacing: 0.02em;
}

.attr-empty {
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}

.trace-case-count {
  color: var(--text-dim);
  font-size: 11px;
}
</style>
