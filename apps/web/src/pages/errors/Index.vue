<script setup lang="ts">
import type {
  BadCase,
  SessionListItem,
  SessionTree,
} from "@harness/contracts";
import {
  computed,
  defineAsyncComponent,
  nextTick,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  useBadCase,
  useBadCaseAnalysis,
  useProbe,
} from "../../composables/useBadCases";
import {
  useSessionBadCases,
  useSessionSummary,
  useSessionTree,
} from "../../composables/useSessions";
import { ApiError } from "../../api/http";
import { parseSessionDeepLink } from "../../router/deepLink";
import ErrorState from "../../components/ui/ErrorState.vue";
import EmptyState from "../../components/ui/EmptyState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { formatStartedAt } from "../../utils/sessionDisplay";
import AttributionReport from "./components/AttributionReport.vue";
import ErrorSidebar from "./components/ErrorSidebar.vue";
import ProblemDescription from "./components/ProblemDescription.vue";

defineOptions({ name: "ErrorsPage" });

const AgentTree = defineAsyncComponent(
  () => import("../../components/agent-tree/AgentTree.vue"),
);

const route = useRoute();
const router = useRouter();
const expandedAgentIds = ref<string[]>([]);

const rawSessionId = computed(() =>
  typeof route.params.sessionId === "string" ? route.params.sessionId : "",
);
const deepLink = computed(() =>
  parseSessionDeepLink(
    rawSessionId.value,
    route.query as Record<string, unknown>,
    "error",
  ),
);
const sessionId = computed(() =>
  deepLink.value?.ok ? deepLink.value.state.sessionId : "",
);
const selectedBadCaseId = computed(() =>
  deepLink.value?.ok ? deepLink.value.state.badCaseId : null,
);
const activeTab = computed<"desc" | "attr">(() =>
  deepLink.value?.ok ? deepLink.value.state.tab : "desc",
);

const problemsQuery = useSessionBadCases(
  computed(() => sessionId.value || null),
);
const summaryQuery = useSessionSummary(
  computed(() => sessionId.value || null),
);
const treeQuery = useSessionTree(
  computed(() => sessionId.value || null),
);
const detailQuery = useBadCase(
  computed(() => selectedBadCaseId.value),
  sessionId,
);
const analysisQuery = useBadCaseAnalysis(
  computed(() => selectedBadCaseId.value),
  sessionId,
);
const probeId = computed(() =>
  activeTab.value === "attr" &&
  analysisQuery.data.value?.status === "analyzed_issue"
    ? analysisQuery.data.value.probeId
    : null,
);
const probeQuery = useProbe(computed(() => probeId.value));

const problems = computed(() => problemsQuery.data.value?.items ?? []);
const session = computed<SessionListItem | null>(
  () => summaryQuery.data.value ?? null,
);
const analyzedCount = computed(
  () =>
    problems.value.filter(
      (problem) => problem.analysis.status !== "unanalyzed",
    ).length,
);
const selectedFromList = computed(() =>
  problems.value.find(
    (problem) => problem.badCaseId === selectedBadCaseId.value,
  ) ?? null,
);
const selectedProblem = computed<BadCase | null>(
  () => detailQuery.data.value ?? selectedFromList.value,
);
const sessionTree = computed<SessionTree | null>(
  () => treeQuery.data.value ?? null,
);
const flowTree = computed<SessionTree | null>(() => {
  if (!sessionTree.value) return null;
  if (!selectedBadCaseId.value) return sessionTree.value;
  return {
    ...sessionTree.value,
    badCases: sessionTree.value.badCases.filter(
      (problem) => problem.badCaseId === selectedBadCaseId.value,
    ),
  };
});
const flowProblems = computed(() =>
  selectedBadCaseId.value && selectedProblem.value
    ? [selectedProblem.value]
    : problems.value,
);
const selectedIndex = computed(() => {
  const index = problems.value.findIndex(
    (problem) => problem.badCaseId === selectedBadCaseId.value,
  );
  return index >= 0 ? index + 1 : null;
});
const flowNote = computed(() => {
  if (!selectedProblem.value) {
    return `全部错误 · ${problems.value.length} 个`;
  }
  const prefix = selectedIndex.value ? `#${selectedIndex.value} · ` : "";
  return `仅显示 ${prefix}${selectedProblem.value.title}`;
});
const fallbackObject = computed(() => {
  const problem = selectedProblem.value;
  if (!problem) return "";
  return problem.objectVersion
    ? `${problem.objectName} @ ${problem.objectVersion}`
    : problem.objectName;
});

const routeFatalError = computed(() => {
  if (!rawSessionId.value) return null;
  if (deepLink.value && !deepLink.value.ok) {
    return {
      code: deepLink.value.code,
      message: deepLink.value.message,
      retry: false,
    };
  }
  const error = detailQuery.error.value ?? analysisQuery.error.value;
  if (error instanceof ApiError && error.status === 409) {
    return {
      code: error.code,
      message: "问题不属于当前 Session。",
      retry: false,
    };
  }
  if (error instanceof ApiError && error.status === 404) {
    return {
      code: error.code,
      message: "问题不存在或已删除。",
      retry: false,
    };
  }
  if (error) {
    return {
      code: "BAD_CASE_UNAVAILABLE",
      message: "问题详情读取失败，请重试。",
      retry: true,
    };
  }
  return null;
});

const detailLoading = computed(
  () =>
    Boolean(selectedBadCaseId.value) &&
    !selectedFromList.value &&
    detailQuery.isPending.value,
);
const flowLoading = computed(
  () => treeQuery.isPending.value && Boolean(sessionId.value),
);

function routeQuery(caseId: string | null, tab: "desc" | "attr") {
  if (!caseId) return {};
  return { case: caseId, tab };
}

function selectBadCase(badCaseId: string) {
  if (selectedBadCaseId.value === badCaseId) return;
  expandedAgentIds.value = [];
  void router.push({
    path: `/sessions/${encodeURIComponent(sessionId.value)}/errors`,
    query: routeQuery(badCaseId, "desc"),
  });
}

function showAllErrors() {
  expandedAgentIds.value = [];
  void router.push({
    path: `/sessions/${encodeURIComponent(sessionId.value)}/errors`,
  });
}

function selectTab(tab: "desc" | "attr") {
  if (!selectedBadCaseId.value) return;
  void router.push({
    path: `/sessions/${encodeURIComponent(sessionId.value)}/errors`,
    query: routeQuery(selectedBadCaseId.value, tab),
  });
}

function moveTab(direction: -1 | 1) {
  const target = direction === -1 ? "desc" : "attr";
  selectTab(target);
  void nextTick(() => {
    document.getElementById(`${target}-tab`)?.focus();
  });
}

function tabEdge(edge: "first" | "last") {
  const target = edge === "first" ? "desc" : "attr";
  selectTab(target);
  void nextTick(() => {
    document.getElementById(`${target}-tab`)?.focus();
  });
}

function retryDetail() {
  void Promise.all([
    detailQuery.refetch(),
    analysisQuery.refetch(),
  ]);
}

function retryProblems() {
  void problemsQuery.refetch();
}

function retryTree() {
  void treeQuery.refetch();
}

function ancestorsOf(agentId: string | null): string[] {
  if (!agentId || !sessionTree.value) return [];
  const byId = new Map(
    sessionTree.value.agents.map((agent) => [agent.agentId, agent]),
  );
  const ancestors: string[] = [];
  const seen = new Set<string>([agentId]);
  let parent = byId.get(agentId)?.parentAgentId ?? null;
  while (parent && !seen.has(parent)) {
    ancestors.push(parent);
    seen.add(parent);
    parent = byId.get(parent)?.parentAgentId ?? null;
  }
  return ancestors;
}

watch(
  [selectedProblem, sessionTree],
  async () => {
    if (!selectedProblem.value || !sessionTree.value) return;
    expandedAgentIds.value = ancestorsOf(
      selectedProblem.value.anchor.agentId,
    );
    await nextTick();
  },
  { immediate: true },
);

function toggleExpanded(agentId: string) {
  expandedAgentIds.value = expandedAgentIds.value.includes(agentId)
    ? expandedAgentIds.value.filter((id) => id !== agentId)
    : [...expandedAgentIds.value, agentId];
}
</script>

<template>
  <section
    class="errors-workspace"
    data-testid="errors-workspace"
  >
    <ErrorState
      v-if="routeFatalError"
      class="page-error"
      :code="routeFatalError.code"
      :message="routeFatalError.message"
      :retryable="routeFatalError.retry"
      @retry="retryDetail"
    />
    <template v-else>
      <ErrorSidebar
        :active-bad-case-id="selectedBadCaseId"
        :error="problemsQuery.error.value"
        :loading="problemsQuery.isPending.value"
        :problems="problems"
        :session="session"
        :session-id="sessionId"
        @all="showAllErrors"
        @retry="retryProblems"
        @select="selectBadCase"
      />

      <main
        class="error-main"
        aria-live="polite"
      >
        <LoadingSkeleton
          v-if="detailLoading"
          label="正在读取问题详情"
          :rows="5"
        />
        <template v-else>
          <header class="error-head">
            <div class="error-heading">
              <h1>错误详情</h1>
              <div class="error-meta">
                <time
                  v-if="session"
                  :datetime="session.startedAt"
                >{{ formatStartedAt(session.startedAt) }} 开始</time>
                <span
                  class="root-session-id"
                  data-testid="error-meta-root-session-id"
                  :title="`根会话 ID: ${sessionId}`"
                >根会话 ID · <span class="mono">{{ sessionId }}</span></span>
                <span
                  v-if="session?.repo"
                  class="repo-chip"
                >{{ session.repo }}</span>
                <span>{{ problems.length }} 个错误</span>
                <span>{{ analyzedCount }} 个已分析</span>
              </div>
            </div>
            <RouterLink
              class="overview-link"
              :to="`/sessions/${encodeURIComponent(sessionId)}`"
            >
              返回 Session
            </RouterLink>
          </header>

          <section
            class="flow-panel"
            aria-labelledby="error-flow-title"
          >
            <header class="flow-head">
              <strong id="error-flow-title">执行流</strong>
              <span>{{ flowNote }}</span>
            </header>
            <LoadingSkeleton
              v-if="flowLoading"
              label="正在读取 Agent 执行流"
              :rows="4"
            />
            <ErrorState
              v-else-if="treeQuery.error.value"
              code="SESSION_TREE_UNAVAILABLE"
              message="Agent 执行流读取失败，请重试。"
              @retry="retryTree"
            />
            <AgentTree
              v-else-if="flowTree"
              :active-bad-case-id="selectedBadCaseId"
              :expanded="expandedAgentIds"
              height="413px"
              :problems="flowProblems"
              :tree="flowTree"
              @badcase-select="selectBadCase"
              @toggle-expanded="toggleExpanded"
            />
            <EmptyState
              v-else
              description="当前 Session 没有可展示的 Agent 执行流。"
              title="暂无执行流"
            />
          </section>

          <section class="detail-panel">
            <div
              class="detail-tabs"
              role="tablist"
              aria-label="问题详情"
            >
              <button
                id="desc-tab"
                aria-controls="desc-panel"
                :aria-selected="activeTab === 'desc'"
                :class="{ active: activeTab === 'desc' }"
                role="tab"
                :tabindex="activeTab === 'desc' ? 0 : -1"
                type="button"
                @click="selectTab('desc')"
                @keydown.left.prevent="moveTab(-1)"
                @keydown.right.prevent="moveTab(1)"
                @keydown.home.prevent="tabEdge('first')"
                @keydown.end.prevent="tabEdge('last')"
              >
                问题描述
              </button>
              <button
                id="attr-tab"
                aria-controls="attr-panel"
                :aria-selected="activeTab === 'attr'"
                :class="{ active: activeTab === 'attr' }"
                role="tab"
                :tabindex="activeTab === 'attr' ? 0 : -1"
                type="button"
                @click="selectTab('attr')"
                @keydown.left.prevent="moveTab(-1)"
                @keydown.right.prevent="moveTab(1)"
                @keydown.home.prevent="tabEdge('first')"
                @keydown.end.prevent="tabEdge('last')"
              >
                归因分析
              </button>
            </div>
            <div
              v-show="activeTab === 'desc'"
              id="desc-panel"
              aria-labelledby="desc-tab"
              role="tabpanel"
              tabindex="0"
            >
              <ProblemDescription
                v-if="selectedProblem"
                :index="selectedIndex"
                :problem="selectedProblem"
              />
              <div
                v-else
                class="err-empty"
              >
                从左侧选择一个错误，查看问题描述与归因分析。
              </div>
            </div>
            <div
              v-show="activeTab === 'attr'"
              id="attr-panel"
              aria-labelledby="attr-tab"
              role="tabpanel"
              tabindex="0"
            >
              <AttributionReport
                v-if="selectedProblem"
                :analysis="analysisQuery.data.value ?? null"
                :analysis-error="analysisQuery.error.value"
                :analysis-loading="analysisQuery.isPending.value"
                :fallback-object="fallbackObject"
                :probe="probeQuery.data.value ?? null"
                :probe-error="probeQuery.error.value"
                :probe-loading="probeQuery.isPending.value && Boolean(probeId)"
                :session-id="sessionId"
                @probe-retry="probeQuery.refetch()"
                @retry="analysisQuery.refetch()"
              />
              <div
                v-else
                class="err-empty"
              >
                从左侧选择一个错误，查看问题描述与归因分析。
              </div>
            </div>
          </section>
        </template>
      </main>
    </template>
  </section>
</template>

<style scoped>
.errors-workspace {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  height: calc(100vh - var(--shell-header-height));
  min-height: 0;
  background: var(--bg);
}

.page-error {
  grid-column: 1 / -1;
  margin: 24px;
}

.error-main {
  min-width: 0;
  overflow-y: auto;
  padding: 16px 20px 24px;
}

.error-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.error-heading {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.error-heading h1 {
  margin: 0;
  color: var(--text);
  font-size: var(--font-title);
  font-weight: var(--weight-bold);
}

.status-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.status-dot.neutral {
  background: var(--text-faint);
}

.status-dot.green {
  background: var(--green);
}

.status-dot.purple {
  background: var(--purple);
}

.status-dot.orange {
  background: var(--orange);
}

.status-dot.red {
  background: var(--red);
}

.state-chip {
  padding: 1px 8px;
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

.state-chip.orange {
  color: var(--orange);
}

.state-chip.red {
  color: var(--red);
}

.error-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--text-dim);
  font-size: 12px;
}

.root-session-id {
  color: var(--text-faint);
  overflow-wrap: anywhere;
}

.root-session-id .mono {
  color: var(--text-dim);
  font-size: 11px;
}

.mono {
  font-family: var(--mono);
}

.overview-link {
  margin-left: auto;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  color: var(--text-dim);
  font-size: 11.5px;
  text-decoration: none;
  white-space: nowrap;
}

.overview-link:hover {
  border-color: var(--blue);
  color: var(--text);
}

.flow-panel,
.detail-panel {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
}

.detail-panel {
  margin-top: 14px;
  box-shadow: var(--shadow-card);
}

.detail-panel [role="tabpanel"] {
  min-height: 260px;
}

.flow-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-size: 12px;
  font-weight: var(--weight-bold);
}

.flow-head span {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 10.5px;
}

.flow-panel :deep(.agent-tree) {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.detail-tabs {
  display: flex;
  gap: 4px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border);
}

.detail-tabs button {
  padding: 10px 12px 9px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
}

.detail-tabs button.active {
  border-bottom-color: var(--blue);
  color: var(--text);
  font-weight: 600;
}

.detail-tabs button:disabled {
  cursor: default;
  opacity: 0.55;
}

.err-empty {
  display: grid;
  min-height: 260px;
  box-sizing: border-box;
  place-items: center;
  padding: 28px 4px;
  color: var(--text-faint);
  font-size: 12px;
  text-align: center;
}

.detail-empty {
  display: grid;
  place-content: center;
  gap: 4px;
  margin-top: 14px;
  padding: 42px 16px;
  border: 1px dashed var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  color: var(--text-faint);
  text-align: center;
}

.detail-empty strong {
  color: var(--text-dim);
  font-size: 13px;
}

@media (max-width: 860px) {
  .errors-workspace {
    grid-template-columns: 1fr;
    height: auto;
  }

  .error-sidebar {
    max-height: 44vh;
  }

  .error-main {
    overflow: visible;
  }

  .error-head {
    flex-wrap: wrap;
  }

  .overview-link {
    margin-left: 0;
  }
}
</style>
