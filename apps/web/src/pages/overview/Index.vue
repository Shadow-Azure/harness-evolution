<script setup lang="ts">
import type { OverviewGrain, OverviewRange } from "@harness/contracts";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { OVERVIEW_PAGE_SIZE } from "../../api/overview";
import {
  useOverviewCases,
  useOverviewSources,
  useOverviewSummary,
  useOverviewTrend,
} from "../../composables/useOverview";
import { useWorkspaceId } from "../../composables/useWorkspaceId";
import { useAuthStore } from "../../stores/auth";
import BadCaseTable from "./components/BadCaseTable.vue";
import FilterBar from "./components/FilterBar.vue";
import SourceBars from "./components/SourceBars.vue";
import StackedBucketChart from "./components/StackedBucketChart.vue";
import StatStrip from "./components/StatStrip.vue";
import {
  DEFAULT_OVERVIEW_STATE,
  overviewQuery,
  overviewWindowFilters,
  parseOverviewQuery,
  sameOverviewQuery,
  type OverviewRangeChoice,
  type OverviewUrlState,
} from "./overviewUrl";

defineOptions({ name: "OverviewPage" });

const route = useRoute();
const router = useRouter();
const workspaceId = useWorkspaceId();
const auth = useAuthStore();

const filterBar = ref<InstanceType<typeof FilterBar> | null>(null);
const listAnchor = ref<HTMLElement | null>(null);
const targetsNotice = ref(false);
let lastWorkspaceId: string | null = null;

const parsed = computed(() =>
  parseOverviewQuery(route.query as Record<string, unknown>),
);
const state = computed(() => parsed.value.state);

const summaryFilters = computed(() => overviewWindowFilters(state.value));
const trendFilters = computed(() => ({
  ...overviewWindowFilters(state.value),
  grain: state.value.grain,
}));
const caseFilters = computed(() => ({
  ...overviewWindowFilters(state.value),
  badCaseType: state.value.type,
  page: state.value.page,
  pageSize: OVERVIEW_PAGE_SIZE,
}));

const summaryQuery = useOverviewSummary(workspaceId, summaryFilters);
const trendQuery = useOverviewTrend(workspaceId, trendFilters);
const sourcesQuery = useOverviewSources(workspaceId, summaryFilters);
const casesQuery = useOverviewCases(workspaceId, caseFilters);

const workspaceName = computed(
  () => auth.workspaceById(workspaceId.value)?.name ?? "",
);
const summary = computed(() => summaryQuery.data.value ?? null);
const objects = computed(() => summary.value?.objects ?? []);
const buckets = computed(() => trendQuery.data.value?.buckets ?? []);
const sources = computed(() => sourcesQuery.data.value?.items ?? []);
const caseItems = computed(() => casesQuery.data.value?.items ?? []);
const caseTotal = computed(() => casesQuery.data.value?.total ?? 0);
const grainEffective = computed<OverviewGrain | null>(
  () => trendQuery.data.value?.grain ?? null,
);
const filterWindow = computed(() => {
  if (state.value.range === "custom") {
    return { from: state.value.from, to: state.value.to };
  }
  return summary.value?.window ?? null;
});
const isFiltered = computed(
  () =>
    state.value.objects.length > 0 ||
    state.value.type !== "all" ||
    state.value.range !== DEFAULT_OVERVIEW_STATE.range,
);
const grainLabels: Record<OverviewGrain, string> = {
  day: "日",
  week: "周",
  month: "月",
};

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

function setRange(value: OverviewRangeChoice): void {
  if (value === "custom") {
    if (state.value.range === "custom") return;
    const { from, to } =
      summary.value?.window && state.value.range === DEFAULT_OVERVIEW_STATE.range
        ? summary.value.window
        : defaultCustomWindow();
    void replaceState({ range: "custom", from, to, page: 1 });
    return;
  }
  const range = value as OverviewRange;
  void replaceState({ range, from: "", to: "", page: 1 });
}

function setWindow(value: { from: string; to: string }): void {
  void replaceState({
    range: "custom",
    from: value.from,
    to: value.to,
    page: 1,
  });
}

function setGrain(value: OverviewGrain): void {
  void replaceState({ grain: value, page: 1 });
}

function setObjects(value: string[]): void {
  void replaceState({ objects: value, page: 1 });
}

function clearFilters(): void {
  void replaceState({ ...DEFAULT_OVERVIEW_STATE });
}

function setPage(page: number): void {
  void router.push({
    path: route.path,
    query: overviewQuery({ ...state.value, page }),
  });
}

function selectBucket(value: { from: string; to: string }): void {
  void replaceState({
    range: "custom",
    from: value.from,
    to: value.to,
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

watch(
  () => parsed.value.targetsRequested,
  (requested) => {
    if (requested) targetsNotice.value = true;
  },
  { immediate: true },
);

/**
 * Keep the URL canonical and reset foreign filters when the workspace changes.
 *
 * One watcher owns both jobs: two independent watchers raced when a workspace
 * switch and a canonicalization replace landed in the same tick, and the
 * canonicalization navigation cancelled the reset.
 */
watch(
  [workspaceId, parsed],
  ([wid]) => {
    if (lastWorkspaceId !== null && wid !== lastWorkspaceId) {
      lastWorkspaceId = wid;
      targetsNotice.value = false;
      void router.replace({
        path: route.path,
        query: overviewQuery(DEFAULT_OVERVIEW_STATE),
      });
      return;
    }
    lastWorkspaceId = wid;
    if (sameOverviewQuery(route.query, overviewQuery(parsed.value.state))) return;
    void router.replace({
      path: route.path,
      query: overviewQuery(parsed.value.state),
    });
  },
  { immediate: true, flush: "post" },
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
          {{ workspaceName }} · 从 bad case 上报来源与时间维度观察自身存在问题 /
          发现前置步骤问题的分布，并下钻到 Session 错误详情。
        </p>
      </div>
      <span class="readonly">只读视图 · 筛选条件保存在地址栏</span>
    </header>

    <div class="view-switch">
      <div
        class="seg"
        role="tablist"
        aria-label="总览视图"
      >
        <button
          class="active"
          data-testid="ov-tab-cases"
          role="tab"
          type="button"
          aria-selected="true"
        >
          bad case 总览
        </button>
        <button
          data-testid="ov-tab-targets"
          disabled
          role="tab"
          type="button"
          aria-selected="false"
          title="进化对象总览将在 M11 提供"
        >
          进化对象总览
        </button>
      </div>
      <p
        v-if="targetsNotice"
        class="targets-notice"
        data-testid="ov-targets-notice"
        role="status"
      >
        进化对象总览将在 M11 提供，已切回 bad case 总览。
      </p>
    </div>

    <StatStrip
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

    <section
      class="chart-card"
      data-testid="ov-chart-card"
    >
      <div class="card-head">
        <div>
          <h2>bad case 趋势</h2>
          <div class="hint">
            按{{ grainLabels[state.grain] }}聚合 · 悬停查看自身存在问题 /
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
        :error="trendQuery.error.value"
        :grain="state.grain"
        :loading="trendQuery.isPending.value"
        @clear-filters="clearFilters"
        @retry="trendQuery.refetch()"
        @select-bucket="selectBucket"
      />
      <SourceBars
        :error="sourcesQuery.error.value"
        :loading="sourcesQuery.isPending.value"
        :sources="sources"
        @retry="sourcesQuery.refetch()"
      />
    </section>

    <div ref="listAnchor">
      <BadCaseTable
        :error="casesQuery.error.value"
        :filtered="isFiltered"
        :items="caseItems"
        :loading="casesQuery.isPending.value"
        :page="state.page"
        :page-size="OVERVIEW_PAGE_SIZE"
        :total="caseTotal"
        :type="state.type"
        :wid="workspaceId"
        @clear-filters="clearFilters"
        @retry="casesQuery.refetch()"
        @update:page="setPage"
      />
    </div>
  </section>
</template>

<style scoped>
.overview-page {
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: 18px 20px 64px;
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

.readonly {
  margin-left: auto;
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

.targets-notice {
  margin: 0;
  padding: 4px 9px;
  border: 1px solid color-mix(in srgb, var(--orange) 32%, var(--border));
  border-radius: 7px;
  background: color-mix(in srgb, var(--orange) 7%, var(--bg-card));
  color: var(--text-dim);
  font-size: 11px;
}

.chart-card {
  margin-bottom: 14px;
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

@media (max-width: 640px) {
  .overview-page {
    padding: 14px 12px 48px;
  }

  .readonly {
    margin-left: 0;
  }
}
</style>
