<script setup lang="ts">
import type {
  OverviewBadCaseType,
  OverviewGrain,
  OverviewRange,
} from "@harness/contracts";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { OVERVIEW_PAGE_SIZE } from "../../api/overview";
import { ApiError } from "../../api/http";
import {
  useOverviewCases,
  useOverviewSources,
  useOverviewSummary,
  useOverviewTrend,
} from "../../composables/useOverview";
import { useWorkspaceId } from "../../composables/useWorkspaceId";
import { workspacePath } from "../../router/workspace";
import { useAuthStore } from "../../stores/auth";
import { canManageWorkspace } from "../../utils/workspaceDisplay";
import LaunchWizard from "../evolution/components/LaunchWizard.vue";
import BadCaseTable from "./components/BadCaseTable.vue";
import FilterBar from "./components/FilterBar.vue";
import OverviewOpsContext from "./components/OverviewOpsContext.vue";
import SourceBars from "./components/SourceBars.vue";
import StackedBucketChart from "./components/StackedBucketChart.vue";
import StatStrip from "./components/StatStrip.vue";
import TargetsOverview from "./components/TargetsOverview.vue";
import {
  bucketWindow,
  DEFAULT_OVERVIEW_STATE,
  overviewListWindow,
  overviewQuery,
  overviewWindowFilters,
  parseOverviewQuery,
  sameOverviewQuery,
  type OverviewRangeChoice,
  type OverviewTab,
  type OverviewUrlState,
} from "./overviewUrl";

defineOptions({ name: "OverviewPage" });

const route = useRoute();
const router = useRouter();
const workspaceId = useWorkspaceId();
const auth = useAuthStore();

const filterBar = ref<InstanceType<typeof FilterBar> | null>(null);
const targetsOverview = ref<InstanceType<typeof TargetsOverview> | null>(null);
const listAnchor = ref<HTMLElement | null>(null);

const parsed = computed(() =>
  parseOverviewQuery(route.query as Record<string, unknown>),
);
const state = computed(() => parsed.value.state);

const summaryFilters = computed(() => overviewWindowFilters(state.value));
const trendFilters = computed(() => ({
  ...overviewWindowFilters(state.value),
  grain: state.value.grain,
}));
// The list is its own query: no global range/objects leak in, and an empty date
// pair means "all time" rather than the chart's 90-day default.
const caseFilters = computed(() => {
  const window = overviewListWindow(state.value);
  return {
    ...(window ?? { allTime: true }),
    objects: state.value.listObject ? [state.value.listObject] : [],
    badCaseType: state.value.type,
    page: state.value.page,
    pageSize: OVERVIEW_PAGE_SIZE,
  };
});

const casesTabActive = computed(() => state.value.tab === "cases");
const summaryQuery = useOverviewSummary(workspaceId, summaryFilters);
const trendQuery = useOverviewTrend(workspaceId, trendFilters, casesTabActive);
const sourcesQuery = useOverviewSources(
  workspaceId,
  summaryFilters,
  casesTabActive,
);
const casesQuery = useOverviewCases(workspaceId, caseFilters, casesTabActive);

const workspaceName = computed(
  () => auth.workspaceById(workspaceId.value)?.name ?? "",
);
const workspace = computed(() => auth.workspaceById(workspaceId.value));
const canManage = computed(() => canManageWorkspace(workspace.value?.role));
const wizardOpen = ref(false);
const summary = computed(() => summaryQuery.data.value ?? null);
const objects = computed(() => summary.value?.objects ?? []);
const buckets = computed(() => trendQuery.data.value?.buckets ?? []);
const sources = computed(() => sourcesQuery.data.value?.items ?? []);
const caseItems = computed(() => casesQuery.data.value?.items ?? []);
const caseTotal = computed(() => casesQuery.data.value?.total ?? 0);
const grainEffective = computed<OverviewGrain | null>(
  () => trendQuery.data.value?.grain ?? null,
);
/** Bucket grain the server actually used, which may be coarser than requested. */
const activeGrain = computed<OverviewGrain>(
  () => grainEffective.value ?? state.value.grain,
);
const casePages = computed(() =>
  Math.max(1, Math.ceil(caseTotal.value / OVERVIEW_PAGE_SIZE)),
);
const filterWindow = computed(() => {
  if (state.value.range === "custom") {
    return { from: state.value.from, to: state.value.to };
  }
  return summary.value?.window ?? trendQuery.data.value?.window ?? null;
});
const listFiltered = computed(
  () =>
    Boolean(state.value.listFrom && state.value.listTo) ||
    Boolean(state.value.listObject) ||
    state.value.type !== "all",
);
const grainLabels: Record<OverviewGrain, string> = {
  day: "日",
  week: "周",
  month: "月",
};

/**
 * Show the API's own error code, falling back only when it carries none.
 * @param error Block-level query failure, if any.
 * @param fallback Page-owned pseudo code used for non-API failures.
 * @returns Stable code rendered by `ErrorState`.
 */
function blockErrorCode(error: Error | null, fallback: string): string {
  return error instanceof ApiError && error.code ? error.code : fallback;
}

const summaryCode = computed(() =>
  blockErrorCode(summaryQuery.error.value, "OVERVIEW_SUMMARY_UNAVAILABLE"),
);
const trendCode = computed(() =>
  blockErrorCode(trendQuery.error.value, "OVERVIEW_TREND_UNAVAILABLE"),
);
const sourcesCode = computed(() =>
  blockErrorCode(sourcesQuery.error.value, "OVERVIEW_SOURCES_UNAVAILABLE"),
);
const casesCode = computed(() =>
  blockErrorCode(casesQuery.error.value, "OVERVIEW_CASES_UNAVAILABLE"),
);

/**
 * Return today's Asia/Shanghai calendar date as `YYYY-MM-DD`.
 * @returns Local Shanghai date used to prefill a custom window.
 */
function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
  }).format(new Date());
}

function defaultCustomWindow(): { from: string; to: string } {
  const to = shanghaiToday();
  const [year, month, day] = to.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  const start = new Date(Date.UTC(year, month - 1, day - 89));
  return { from: start.toISOString().slice(0, 10), to };
}

async function replaceState(patch: Partial<OverviewUrlState>): Promise<void> {
  const next = { ...state.value, ...patch };
  await router.replace({ path: route.path, query: overviewQuery(next) });
}

function setTab(value: OverviewTab): void {
  if (state.value.tab === value) return;
  void replaceState({ tab: value, page: 1 });
}

function applyTargetsPatch(patch: Partial<OverviewUrlState>): void {
  void replaceState(patch);
}

function setRange(value: OverviewRangeChoice): void {
  if (value === "custom") {
    if (state.value.range === "custom") return;
    // Prefill from the window currently on screen (server-confirmed), so
    // switching from 7/30/90 days keeps the same boundaries instead of
    // jumping to the 90-day fallback.
    const { from, to } = summary.value?.window ?? defaultCustomWindow();
    void replaceState({ range: "custom", from, to });
    return;
  }
  const range = value as OverviewRange;
  void replaceState({ range, from: "", to: "" });
}

function setWindow(value: { from: string; to: string }): void {
  void replaceState({
    range: "custom",
    from: value.from,
    to: value.to,
  });
}

function setGrain(value: OverviewGrain): void {
  void replaceState({ grain: value });
}

function setObjects(value: string[]): void {
  void replaceState({ objects: value });
}

function clearFilters(): void {
  // The chart/stat filters and the list filters are independent, so this only
  // resets the global window, grain and source selection.
  void replaceState({
    range: DEFAULT_OVERVIEW_STATE.range,
    from: "",
    to: "",
    grain: DEFAULT_OVERVIEW_STATE.grain,
    objects: [],
  });
}

function clearListFilters(): void {
  void replaceState({
    listFrom: "",
    listTo: "",
    listObject: "",
    type: "all",
    page: 1,
  });
}

function applyListFilters(patch: {
  from?: string;
  to?: string;
  object?: string;
  type?: OverviewBadCaseType;
}): void {
  const next: Partial<OverviewUrlState> = { page: 1 };
  if (patch.from !== undefined || patch.to !== undefined) {
    next.listFrom = patch.from ?? "";
    next.listTo = patch.to ?? "";
  }
  if (patch.object !== undefined) next.listObject = patch.object;
  if (patch.type !== undefined) next.type = patch.type;
  void replaceState(next);
}

function setPage(page: number): void {
  void router.push({
    path: route.path,
    query: overviewQuery({ ...state.value, page }),
  });
}

function selectBucket(value: { bucket: string; from: string; to: string }): void {
  // Resolve the window against the grain the server actually used: a day
  // request downgraded to weeks must still filter Monday..Sunday. The bucket
  // only narrows the list; it must not rewrite the chart's own window.
  const window = bucketWindow(value.bucket, activeGrain.value) ?? value;
  void replaceState({
    listFrom: window.from,
    listTo: window.to,
    page: 1,
  });
}

function selectType(value: "self" | "discovery"): void {
  void replaceState({ type: state.value.type === value ? "all" : value, page: 1 });
  listAnchor.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

function focusSources(): void {
  filterBar.value?.focusSources();
}

function openLaunchWizard(): void {
  if (!canManage.value) return;
  wizardOpen.value = true;
}

/**
 * Follow the accepted run while keeping the overview URL in browser history.
 * @param mode Launched run mode.
 * @param runId Accepted run identifier.
 * @returns A navigation promise after the wizard closes.
 */
async function onLaunched(
  mode: "full" | "cluster_only",
  runId: string,
): Promise<void> {
  wizardOpen.value = false;
  await router.push(
    workspacePath(
      workspaceId.value,
      mode === "full"
        ? `evolution/runs/${encodeURIComponent(runId)}`
        : `evolution/cluster/${encodeURIComponent(runId)}`,
    ),
  );
}

/**
 * Keep the URL canonical without touching the workspace's own filters.
 *
 * The workspace picker is responsible for opening another workspace with the
 * default overview query; this watcher only normalizes the current URL. That
 * keeps browser back/forward honest: returning to workspace A restores A's
 * range/objects/type instead of rewriting the history entry to the defaults.
 */
watch(
  [workspaceId, parsed],
  () => {
    if (route.name !== "workspace-overview") return;
    if (sameOverviewQuery(route.query, overviewQuery(parsed.value.state))) return;
    void router.replace({
      path: route.path,
      query: overviewQuery(parsed.value.state),
    });
  },
  { immediate: true, flush: "post" },
);

/**
 * Clamp a URL page beyond the last page returned by the API.
 *
 * The list endpoint still reports the authoritative filtered total on an empty
 * page, so the page can redirect to the last valid page instead of showing the
 * "workspace has no bad cases" empty state.
 */
watch(
  () => casesQuery.data.value,
  (data) => {
    if (!data || route.name !== "workspace-overview") return;
    if (state.value.tab !== "cases") return;
    if (state.value.page <= casePages.value) return;
    void router.replace({
      path: route.path,
      query: overviewQuery({ ...state.value, page: casePages.value }),
    });
  },
  { immediate: true },
);

/**
 * A missing workspace is a whole-page condition: send the person to the chooser
 * instead of rendering four block-level errors whose retry can never succeed.
 */
let redirectingToChooser = false;
watch(
  [summaryQuery.error, trendQuery.error, sourcesQuery.error, casesQuery.error],
  (errors) => {
    if (redirectingToChooser) return;
    const missing = errors.some(
      (error) =>
        error instanceof ApiError &&
        (error.status === 404 || error.code === "WORKSPACE_NOT_FOUND"),
    );
    if (!missing) return;
    redirectingToChooser = true;
    void router.replace({
      path: "/workspaces",
      query: { reason: "forbidden" },
    });
  },
  { immediate: true },
);
</script>

<template>
  <section
    class="overview-page"
    data-testid="overview-page"
  >
    <header class="page-head">
      <div>
        <h1>工作空间总览</h1>
        <p class="sub">
          {{ workspaceName }} ·
          {{ state.tab === "cases"
            ? "从 bad case 上报来源与时间维度观察自身存在问题 / 发现前置步骤问题的分布，并下钻到 Session 错误详情。"
            : "从进化对象与时间维度观察潜在 bad case、归因状态和上报来源，并下钻到对应 Session。" }}
        </p>
      </div>
      <div class="head-actions">
        <template v-if="state.tab === 'cases'">
          <template v-if="canManage">
            <RouterLink
              class="head-btn"
              data-testid="ov-action-ingest"
              :to="{ path: workspacePath(workspaceId, 'admin'), query: { tab: 'ingest' } }"
            >
              上报接入
            </RouterLink>
            <button
              class="head-btn primary"
              data-testid="ov-action-launch"
              type="button"
              @click="openLaunchWizard"
            >
              启动自进化
            </button>
          </template>
          <span
            v-else
            class="readonly"
            data-testid="ov-readonly-actions"
          >只读访问 · 上报与启动由空间管理员执行</span>
        </template>
        <template v-else>
          <template v-if="canManage">
            <button
              class="head-btn"
              data-testid="ov-target-create"
              type="button"
              @click="targetsOverview?.openCreate()"
            >
              + 新增进化对象
            </button>
            <button
              class="head-btn primary"
              data-testid="ov-target-launch"
              type="button"
              @click="openLaunchWizard"
            >
              启动自进化
            </button>
          </template>
          <span
            v-else
            class="readonly"
          >只读访问</span>
        </template>
      </div>
    </header>

    <div class="view-switch">
      <div
        class="seg"
        role="tablist"
        aria-label="总览视图"
      >
        <button
          :class="{ active: state.tab === 'cases' }"
          data-testid="ov-tab-cases"
          role="tab"
          type="button"
          :aria-selected="state.tab === 'cases'"
          @click="setTab('cases')"
        >
          bad case 总览
        </button>
        <button
          :class="{ active: state.tab === 'targets' }"
          data-testid="ov-tab-targets"
          role="tab"
          type="button"
          :aria-selected="state.tab === 'targets'"
          @click="setTab('targets')"
        >
          进化对象总览
        </button>
      </div>
    </div>

    <template v-if="state.tab === 'cases'">
      <StatStrip
        :code="summaryCode"
        :error="summaryQuery.error.value"
        :loading="summaryQuery.isPending.value"
        :totals="summary?.totals ?? null"
        @focus-sources="focusSources"
        @retry="summaryQuery.refetch()"
        @select-type="selectType"
      />

      <FilterBar
        ref="filterBar"
        :grain-effective="grainEffective"
        :objects-loading="
          summaryQuery.isPending.value && state.objects.length === 0
        "
        :options="objects"
        :state="state"
        :window="filterWindow"
        @clear="clearFilters"
        @update:grain="setGrain"
        @update:objects="setObjects"
        @update:range="setRange"
        @update:window="setWindow"
      />

      <div class="ov-grid">
        <section
          class="chart-card"
          data-testid="ov-chart-card"
        >
          <div class="card-head">
            <div>
              <h2>bad case 趋势</h2>
              <div class="hint">
                按{{ grainLabels[activeGrain] }}聚合 · 悬停查看自身存在问题 /
                发现前置步骤问题明细 · 点击时间桶按该桶过滤列表
              </div>
            </div>
            <span class="spacer" />
            <div class="legend">
              <span><i class="self" />自身存在问题</span>
              <span><i class="discovery" />发现前置步骤问题</span>
            </div>
          </div>
          <StackedBucketChart
            :buckets="buckets"
            :code="trendCode"
            :error="trendQuery.error.value"
            :grain="activeGrain"
            :loading="trendQuery.isPending.value"
            @clear-filters="clearFilters"
            @retry="trendQuery.refetch()"
            @select-bucket="selectBucket"
          />
          <SourceBars
            :buckets="buckets"
            :code="sourcesCode"
            :error="sourcesQuery.error.value"
            :filters="summaryFilters"
            :grain="activeGrain"
            :loading="sourcesQuery.isPending.value"
            :sources="sources"
            :window="filterWindow"
            :workspace-id="workspaceId"
            @retry="sourcesQuery.refetch()"
          />
        </section>

        <div class="ov-side-slot">
          <OverviewOpsContext
            :can-manage="canManage"
            :totals="summary?.totals ?? null"
            :workspace="workspace"
            :workspace-id="workspaceId"
          />
        </div>

        <div
          ref="listAnchor"
          class="ov-list"
          data-testid="ov-case-list-region"
        >
          <BadCaseTable
            :code="casesCode"
            :error="casesQuery.error.value"
            :filtered="listFiltered"
            :from="state.listFrom"
            :items="caseItems"
            :loading="casesQuery.isPending.value"
            :object="state.listObject"
            :object-options="objects"
            :page="state.page"
            :page-size="OVERVIEW_PAGE_SIZE"
            :to="state.listTo"
            :total="caseTotal"
            :type="state.type"
            :wid="workspaceId"
            @clear-filters="clearListFilters"
            @retry="casesQuery.refetch()"
            @update:filters="applyListFilters"
            @update:page="setPage"
          />
        </div>
      </div>
    </template>
    <TargetsOverview
      v-else
      ref="targetsOverview"
      :can-manage="canManage"
      :shared-window="summary?.window ?? null"
      :source-options="objects"
      :state="state"
      :workspace-id="workspaceId"
      @patch="applyTargetsPatch"
    />
    <LaunchWizard
      v-if="wizardOpen"
      :wid="workspaceId"
      @close="wizardOpen = false"
      @launched="onLaunched"
    />
  </section>
</template>

<style scoped>
.overview-page {
  width: min(1180px, 100%);
  height: 100%;
  margin: 0 auto;
  padding: 18px 20px 64px;
  overflow-y: auto;
}

.page-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.page-head h1 {
  margin: 0;
  color: var(--text);
  font-size: var(--font-title);
  font-weight: 650;
}

.sub {
  max-width: 780px;
  margin: 3px 0 0;
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.6;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.head-btn {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-family: inherit;
  font-size: 11px;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
}

.head-btn:hover {
  border-color: var(--blue);
  color: var(--text);
}

.head-btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: var(--text-on-accent);
}

.head-btn.primary:hover {
  border-color: var(--blue-deep);
  background: var(--blue-deep);
  color: var(--text-on-accent);
}

.head-btn:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--blue) 45%, transparent);
  outline-offset: 1px;
}

.readonly {
  padding: 2px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 10.5px;
  white-space: nowrap;
}

.view-switch {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
  margin-bottom: 10px;
}

.seg {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
}

.seg button {
  padding: 5px 14px;
  border: 0;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
}

.seg button:first-child {
  border-left: 0;
}

.seg button.active {
  background: var(--bg-card);
  color: var(--text);
  font-weight: 650;
}

.seg button:disabled {
  color: var(--text-faint);
  cursor: not-allowed;
}

.ov-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 282px;
  gap: 14px;
  align-items: start;
  margin-bottom: 14px;
}

.ov-side-slot {
  min-width: 0;
}

.ov-list {
  grid-column: 1 / -1;
  min-width: 0;
}

.chart-card {
  min-width: 0;
  margin-bottom: 0;
  padding: 14px 16px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.card-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.card-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 13.5px;
  font-weight: 650;
}

.card-head .hint {
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.55;
}

.spacer {
  flex: 1;
}

.legend {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--text-dim);
  font-size: 10.5px;
}

.legend i {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 4px;
  border-radius: 2px;
  vertical-align: -1px;
}

.legend i.self {
  background: var(--blue);
  opacity: 0.82;
}

.legend i.discovery {
  background: var(--purple);
  opacity: 0.82;
}

@media (max-width: 1024px) {
  .ov-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .chart-card {
    order: 1;
  }

  .ov-list {
    order: 2;
    grid-column: auto;
  }

  .ov-side-slot {
    order: 3;
  }
}

@media (max-width: 640px) {
  .overview-page {
    height: auto;
    padding: 14px 12px 48px;
  }

  .readonly {
    margin-left: 0;
  }
}
</style>
