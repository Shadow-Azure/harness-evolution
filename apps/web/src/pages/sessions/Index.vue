<script setup lang="ts">
import type { SessionFilters, SessionSort, SessionStatusFilter } from "../../api/sessions";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  useSessionList,
  useSessionSummary,
  useSessionTree,
} from "../../composables/useSessions";
import { parseSessionDeepLink } from "../../router/deepLink";
import SearchBox from "./components/SearchBox.vue";
import SessionList from "./components/SessionList.vue";
import SessionOverview from "./components/SessionOverview.vue";
import SortSelect from "./components/SortSelect.vue";
import StatusChips from "./components/StatusChips.vue";

defineOptions({ name: "SessionsPage" });

const route = useRoute();
const router = useRouter();
const searchInput = ref(typeof route.query.q === "string" ? route.query.q : "");
const deepLinkNotice = ref("");
let noticeOwnedPath: string | null = null;
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let searchRevision = 0;

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

const rawSessionId = computed(() =>
  typeof route.params.sessionId === "string" ? route.params.sessionId : "",
);
const deepLinkResult = computed(() =>
  rawSessionId.value
    ? parseSessionDeepLink(
        rawSessionId.value,
        route.query as Record<string, unknown>,
      )
    : null,
);
const deepLinkError = computed(() =>
  deepLinkResult.value && !deepLinkResult.value.ok
    ? deepLinkResult.value
    : null,
);
const deepLinkState = computed(() =>
  deepLinkResult.value?.ok ? deepLinkResult.value.state : null,
);
const selectedId = computed(() => deepLinkState.value?.sessionId ?? "");
const activeStatus = computed<SessionStatusFilter>(() => {
  if (filters.value.status === "all" || filters.value.status === "ok") {
    return filters.value.status;
  }
  return "problem";
});

const listQuery = useSessionList(filters);
const summaryQuery = useSessionSummary(
  computed(() => selectedId.value || null),
);
const treeQuery = useSessionTree(
  computed(() => selectedId.value || null),
);

const expandedBySession = ref<Record<string, string[]>>({});

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
const sessionTree = computed(() => treeQuery.data.value ?? null);
const treeError = computed(() => treeQuery.error.value);
const isTreePending = computed(
  () => treeQuery.isPending.value && Boolean(selectedId.value),
);
const overviewItem = computed(
  () => summaryQuery.data.value ?? selectedItem.value,
);
const expandedAgentIds = computed(
  () => expandedBySession.value[selectedId.value] ?? [],
);
const requestedAgentId = computed(
  () => deepLinkState.value?.agentId ?? null,
);
const mainAgentId = computed(
  () =>
    sessionTree.value?.agents.find((agent) => agent.kind === "main")?.agentId
    ?? null,
);
const activeAgentId = computed(() => {
  const requested = requestedAgentId.value;
  if (!requested) {
    return mainAgentId.value;
  }
  if (!sessionTree.value) {
    return requested;
  }
  return sessionTree.value.agents.some((agent) => agent.agentId === requested)
    ? requested
    : mainAgentId.value;
});
const requestedEventIndex = computed(
  () => deepLinkState.value?.eventIndex ?? null,
);
const activeEventIndex = computed(() => {
  const agentId = requestedAgentId.value;
  const eventIndex = requestedEventIndex.value;
  if (!agentId || eventIndex === null || !sessionTree.value) {
    return null;
  }
  const agent = sessionTree.value.agents.find(
    (candidate) => candidate.agentId === agentId,
  );
  return agent && eventIndex >= 0 && eventIndex < agent.events.length
    ? eventIndex
    : null;
});

function routeWithFilters(
  overrides: Partial<SessionFilters>,
  preserveDeepLink = true,
) {
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
  if (preserveDeepLink && deepLinkState.value?.agentId) {
    next.agent = deepLinkState.value.agentId;
    if (deepLinkState.value.eventIndex !== null) {
      next.evidence = String(deepLinkState.value.eventIndex);
    }
  }
  return next;
}

function sameStringQuery(
  current: Record<string, unknown>,
  next: Record<string, string>,
) {
  const currentEntries = Object.entries(current)
    .map(([key, value]) => [key, typeof value === "string" ? value : null] as const)
    .sort(([left], [right]) => left.localeCompare(right));
  const nextEntries = Object.entries(next)
    .sort(([left], [right]) => left.localeCompare(right));
  return currentEntries.length === nextEntries.length
    && currentEntries.every(([key, value], index) =>
      value !== null
      && key === nextEntries[index]?.[0]
      && value === nextEntries[index]?.[1],
    );
}

function ownDeepLinkNotice(message: string, targetPath: string, query: Record<string, string>) {
  deepLinkNotice.value = message;
  noticeOwnedPath = router.resolve({ path: targetPath, query }).fullPath;
}

async function updateFilter(overrides: Partial<SessionFilters>) {
  deepLinkNotice.value = "";
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
  const revision = ++searchRevision;
  searchTimer = setTimeout(() => {
    searchTimer = undefined;
    if (revision !== searchRevision) return;
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
  deepLinkNotice.value = "";
  void router.push({
    path: `/sessions/${encodeURIComponent(sessionId)}`,
    query: routeWithFilters({}, false),
  });
}

function toggleExpanded(agentId: string) {
  if (!selectedId.value) return;
  const current = expandedBySession.value[selectedId.value] ?? [];
  expandedBySession.value = {
    ...expandedBySession.value,
    [selectedId.value]: current.includes(agentId)
      ? current.filter((id) => id !== agentId)
      : [...current, agentId],
  };
}

function collapseAllBranches() {
  if (!selectedId.value) return;
  expandedBySession.value = {
    ...expandedBySession.value,
    [selectedId.value]: [],
  };
}

function agentAncestors(
  agents: NonNullable<typeof sessionTree.value>["agents"],
  targetAgentId: string,
): string[] {
  const byId = new Map(agents.map((agent) => [agent.agentId, agent]));
  const ancestors: string[] = [];
  const seen = new Set<string>([targetAgentId]);
  let parentId = byId.get(targetAgentId)?.parentAgentId ?? null;
  while (parentId && !seen.has(parentId)) {
    ancestors.push(parentId);
    seen.add(parentId);
    parentId = byId.get(parentId)?.parentAgentId ?? null;
  }
  return ancestors;
}

function selectAgent(agentId: string) {
  if (!selectedId.value) return;
  deepLinkNotice.value = "";
  void router.push({
    path: `/sessions/${encodeURIComponent(selectedId.value)}`,
    query: {
      ...routeWithFilters({}, false),
      agent: agentId,
    },
  });
}

watch(
  () => route.query.q,
  (value) => {
    searchRevision += 1;
    clearTimeout(searchTimer);
    searchTimer = undefined;
    searchInput.value = typeof value === "string" ? value : "";
  },
);

watch(
  () => route.fullPath,
  (fullPath) => {
    if (noticeOwnedPath !== null && fullPath !== noticeOwnedPath) {
      deepLinkNotice.value = "";
      noticeOwnedPath = null;
    }
  },
);

watch(
  [deepLinkResult, () => route.query],
  ([result]) => {
    if (!result?.ok) return;
    const next = routeWithFilters({}, false);
    Object.assign(next, result.canonicalQuery);
    if (sameStringQuery(route.query, next)) return;
    void router.replace({
      path: `/sessions/${encodeURIComponent(result.state.sessionId)}`,
      query: next,
    });
  },
  { immediate: true, flush: "post" },
);

watch(
  [items, selectedId, isListSuccess, deepLinkError],
  ([currentItems, currentId, success, invalidLink]) => {
    if (!success) return;
    if (invalidLink) return;
    if (!currentId) {
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

watch(
  [
    selectedId,
    requestedAgentId,
    requestedEventIndex,
    () => treeQuery.data.value,
  ],
  ([currentId, , , currentTree]) => {
    const currentAgents = currentTree?.agents;
    if (!currentId || !currentAgents?.length) return;
    const requested = requestedAgentId.value;
    if (
      !requested &&
      currentAgents.some((agent) => agent.kind === "main")
    ) {
      return;
    }
    if (!requested) return;
    const agent = currentAgents.find(
      (candidate) => candidate.agentId === requested,
    );
    if (!agent) {
      const targetPath = `/sessions/${encodeURIComponent(currentId)}`;
      const targetQuery = routeWithFilters({}, false);
      ownDeepLinkNotice(
        "链接中的 Agent 已不存在，已返回主会话。",
        targetPath,
        targetQuery,
      );
      void router.replace({
        path: targetPath,
        query: targetQuery,
      });
      return;
    }
    const requiredExpanded = agentAncestors(currentAgents, agent.agentId);
    const currentExpanded = expandedBySession.value[currentId] ?? [];
    const missingExpanded = requiredExpanded.filter(
      (agentId) => !currentExpanded.includes(agentId),
    );
    if (missingExpanded.length > 0) {
      expandedBySession.value = {
        ...expandedBySession.value,
        [currentId]: [...currentExpanded, ...missingExpanded],
      };
    }
    if (
      requestedEventIndex.value !== null &&
      (requestedEventIndex.value < 0 ||
        requestedEventIndex.value >= agent.events.length)
    ) {
      const targetPath = `/sessions/${encodeURIComponent(currentId)}`;
      const targetQuery = {
        ...routeWithFilters({}, false),
        agent: agent.agentId,
      };
      ownDeepLinkNotice(
        "链接中的证据位置无效，已定位到 Agent。",
        targetPath,
        targetQuery,
      );
      void router.replace({
        path: targetPath,
        query: targetQuery,
      });
      return;
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  searchRevision += 1;
  clearTimeout(searchTimer);
  searchTimer = undefined;
});
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
              :model-value="activeStatus"
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
        <p
          v-if="deepLinkError || deepLinkNotice"
          class="deep-link-notice"
          data-testid="deep-link-notice"
          role="alert"
        >
          {{ deepLinkError?.message ?? deepLinkNotice }}
        </p>
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
      v-if="!deepLinkError"
      :active-agent-id="activeAgentId"
      :active-event-index="activeEventIndex"
      :expanded-agent-ids="expandedAgentIds"
      :item="overviewItem"
      :loading="isSummaryPending"
      :tree="sessionTree"
      :tree-error="treeError"
      :tree-loading="isTreePending"
      :error="summaryError"
      @collapse-all="collapseAllBranches"
      @node-select="selectAgent"
      @retry="summaryQuery.refetch"
      @toggle-expanded="toggleExpanded"
      @tree-retry="treeQuery.refetch"
    />
    <section
      v-else
      class="overview"
      data-testid="deep-link-error"
    >
      <div class="deep-link-error">
        <strong>Session 深链无效</strong>
        <span>{{ deepLinkError.message }}</span>
      </div>
    </section>
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

.deep-link-notice {
  margin: 0;
  padding: 6px 8px;
  border: 1px solid color-mix(in srgb, var(--orange) 32%, var(--border));
  border-radius: 7px;
  background: color-mix(in srgb, var(--orange) 7%, var(--bg-card));
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.5;
}

.overview {
  min-width: 0;
  overflow-y: auto;
  padding: 18px 20px;
}

.deep-link-error {
  display: grid;
  gap: 6px;
  padding: 16px;
  border: 1px solid var(--state-error-border);
  border-left: 3px solid var(--red);
  border-radius: var(--radius-md);
  background: var(--state-error-surface);
  color: var(--text-dim);
}

.deep-link-error strong {
  color: var(--state-error-text);
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
