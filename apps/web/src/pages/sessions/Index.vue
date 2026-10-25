<script setup lang="ts">
import type { SessionFilters, SessionSort, SessionStatusFilter } from "../../api/sessions";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useSessionList, useSessionSummary } from "../../composables/useSessions";
import SearchBox from "./components/SearchBox.vue";
import SessionList from "./components/SessionList.vue";
import SessionOverview from "./components/SessionOverview.vue";
import SortSelect from "./components/SortSelect.vue";
import StatusChips from "./components/StatusChips.vue";

defineOptions({ name: "SessionsPage" });

const route = useRoute();
const router = useRouter();
const searchInput = ref(typeof route.query.q === "string" ? route.query.q : "");
let searchTimer: ReturnType<typeof setTimeout> | undefined;

const validStatuses = new Set<SessionStatusFilter>([
  "all",
  "ok",
  "problem",
  "partial",
  "fail",
]);
const validSorts = new Set<SessionSort>([
  "latest",
  "userTurns",
  "messages",
  "agents",
]);

const filters = computed<SessionFilters>(() => {
  const status = typeof route.query.status === "string"
    && validStatuses.has(route.query.status as SessionStatusFilter)
    ? route.query.status as SessionStatusFilter
    : "all";
  const sort = typeof route.query.sort === "string"
    && validSorts.has(route.query.sort as SessionSort)
    ? route.query.sort as SessionSort
    : "latest";
  return {
    q: typeof route.query.q === "string" ? route.query.q : "",
    status,
    sort,
    limit: 100,
  };
});

const selectedId = computed(() =>
  typeof route.params.sessionId === "string" ? route.params.sessionId : "",
);

const listQuery = useSessionList(filters);
const summaryQuery = useSessionSummary(
  computed(() => selectedId.value || null),
);

const items = computed(() => listQuery.data.value?.items ?? []);
const selectedItem = computed(
  () => items.value.find((item) => item.id === selectedId.value) ?? null,
);
const isListPending = computed(() => listQuery.isPending.value);
const isListSuccess = computed(() => listQuery.isSuccess.value);
const listError = computed(() => listQuery.error.value);
const isSummaryPending = computed(
  () => summaryQuery.isPending.value && Boolean(selectedId.value),
);
const summaryError = computed(() => summaryQuery.error.value);
const overviewItem = computed(
  () => summaryQuery.data.value ?? selectedItem.value,
);

function routeWithFilters(overrides: Partial<SessionFilters>) {
  const next: Record<string, string> = {};
  for (const [key, value] of Object.entries({
    q: filters.value.q,
    status: filters.value.status,
    sort: filters.value.sort,
    ...overrides,
  })) {
    if (value && !(key === "status" && value === "all") && !(key === "sort" && value === "latest")) {
      next[key] = String(value);
    }
  }
  return next;
}

async function updateFilter(overrides: Partial<SessionFilters>) {
  await router.push({
    path: selectedId.value
      ? `/sessions/${encodeURIComponent(selectedId.value)}`
      : "/sessions",
    query: routeWithFilters(overrides),
  });
}

function updateSearch(value: string) {
  searchInput.value = value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    void updateFilter({ q: value.trim() });
  }, 300);
}

function updateStatus(value: SessionStatusFilter) {
  void updateFilter({ status: value });
}

function updateSort(value: SessionSort) {
  void updateFilter({ sort: value });
}

function selectSession(sessionId: string) {
  void router.push({
    path: `/sessions/${encodeURIComponent(sessionId)}`,
    query: routeWithFilters({}),
  });
}

watch(
  () => route.query.q,
  (value) => {
    searchInput.value = typeof value === "string" ? value : "";
  },
);

watch(
  [items, selectedId, isListSuccess],
  ([currentItems, currentId, success]) => {
    if (!success) return;
    if (currentItems.length === 0) {
      if (currentId) {
        void router.replace({ path: "/sessions", query: routeWithFilters({}) });
      }
      return;
    }
    if (!currentId || !currentItems.some((item) => item.id === currentId)) {
      const firstId = currentItems[0]?.id;
      if (!firstId) return;
      void router.replace({
        path: `/sessions/${encodeURIComponent(firstId)}`,
        query: routeWithFilters({}),
      });
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => clearTimeout(searchTimer));
</script>

<template>
  <section
    class="session-browser"
    :data-selected-id="selectedId"
  >
    <aside class="sidebar">
      <header class="sidebar-head">
        <div class="sidebar-title">
          <h1>Session 浏览器</h1>
          <span
            class="count"
            data-testid="session-browser-count"
          >
            {{ items.length }} 个会话
          </span>
        </div>
        <SearchBox
          :model-value="searchInput"
          @update:model-value="updateSearch"
        />
        <div class="filters">
          <div class="filter-row">
            <span class="filter-label">状态</span>
            <StatusChips
              :model-value="filters.status ?? 'all'"
              @update:model-value="updateStatus"
            />
          </div>
          <div class="filter-row">
            <span class="filter-label">排序</span>
            <SortSelect
              :model-value="filters.sort ?? 'latest'"
              @update:model-value="updateSort"
            />
          </div>
        </div>
      </header>
      <SessionList
        :items="items"
        :selected-id="selectedId"
        :loading="isListPending"
        :error="listError"
        @retry="listQuery.refetch"
        @select="selectSession"
      />
    </aside>
    <SessionOverview
      :item="overviewItem"
      :loading="isSummaryPending"
      :error="summaryError"
      @retry="summaryQuery.refetch"
    />
  </section>
</template>

<style scoped>
.session-browser {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  width: 100%;
  height: calc(100vh - var(--shell-header-height));
  overflow: hidden;
  background: var(--bg);
}

.sidebar {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
}

.sidebar-head {
  display: grid;
  gap: 9px;
  padding: 13px 11px 10px;
  border-bottom: 1px solid var(--border);
}

.sidebar-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
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
  font-size: 11px;
}

.filters {
  display: grid;
  gap: 8px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.filter-label {
  width: 28px;
  flex-shrink: 0;
  color: var(--text-faint);
  font-size: 11px;
}

@media (max-width: 860px) {
  .session-browser {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
    overflow: visible;
  }

  .sidebar {
    height: auto;
    max-height: none;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .session-list {
    max-height: 58vh;
  }
}
</style>
