<script setup lang="ts">
import type {
  EvolutionTarget,
  EvolutionTargetWrite,
  OverviewWindow,
  TargetOverviewItem,
  TargetState,
} from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";

import {
  TARGET_CASE_PAGE_SIZE,
  type TargetCaseFilters,
  type TargetDetailFilters,
  type TargetOverviewFilters,
} from "../../../api/overview";
import { ApiError } from "../../../api/http";
import { queryKeys } from "../../../api/queryKeys";
import { useAttributionSkillPackages } from "../../../composables/useAttributionSkillPackages";
import TargetFormDialog from "../../evolution/targets/components/TargetFormDialog.vue";
import {
  targetServerError,
  type TargetServerError,
} from "../../evolution/targets/targetErrors";
import {
  useEvolutionTargets,
  useEvolutionTargetVersions,
} from "../../../composables/useEvolutionTargets";
import {
  useOverviewTargetCases,
  useOverviewTargetDetail,
  useOverviewTargets,
  useOverviewTargetTrend,
} from "../../../composables/useOverview";
import PotentialCaseTable from "./PotentialCaseTable.vue";
import TargetDetailCard from "./TargetDetailCard.vue";
import TargetDistributions from "./TargetDistributions.vue";
import TargetSideList from "./TargetSideList.vue";
import TargetTrendChart from "./TargetTrendChart.vue";
import TargetsFilterBar from "./TargetsFilterBar.vue";
import {
  overviewCaseWindow,
  overviewDetailWindow,
  overviewSharedWindow,
  type DetailVersionLimit,
  type OverviewRangeChoice,
  type OverviewUrlState,
} from "../overviewUrl";

const props = defineProps({
  state: {
    type: Object as () => OverviewUrlState,
    required: true,
  },
  workspaceId: {
    type: String,
    required: true,
  },
  sourceOptions: {
    type: Array as () => string[],
    default: () => [],
  },
  sharedWindow: {
    type: Object as () => OverviewWindow | null,
    default: null,
  },
  canManage: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{
  patch: [value: Partial<OverviewUrlState>];
}>();

const queryClient = useQueryClient();
const workspaceId = computed(() => props.workspaceId);
const caseAnchor = ref<HTMLElement | null>(null);

const grainLabels = {
  day: "日",
  week: "周",
  month: "月",
} as const;

const sharedFilters = computed<TargetOverviewFilters>(() => ({
  ...overviewSharedWindow(props.state),
}));
const targetsQuery = useOverviewTargets(workspaceId, sharedFilters);
const targetItems = computed<TargetOverviewItem[]>(
  () => targetsQuery.data.value?.items ?? [],
);
const summary = computed(() => targetsQuery.data.value?.summary ?? null);

const trendFilters = computed<TargetOverviewFilters>(() => ({
  ...overviewSharedWindow(props.state),
  targets: props.state.targets,
  grain: props.state.grain,
}));
const trendQuery = useOverviewTargetTrend(workspaceId, trendFilters);
const buckets = computed(() => trendQuery.data.value?.buckets ?? []);
const grainEffective = computed(() => trendQuery.data.value?.grain ?? null);
const activeGrain = computed(
  () => grainEffective.value ?? props.state.grain,
);
const effectiveWindow = computed(
  () => trendQuery.data.value?.window ?? props.sharedWindow,
);

const caseTargets = computed(() =>
  props.state.caseTarget ? [props.state.caseTarget] : props.state.targets,
);
const caseFilters = computed<TargetCaseFilters>(() => ({
  ...overviewCaseWindow(props.state),
  targets: caseTargets.value.length > 0 ? caseTargets.value : undefined,
  objects: props.state.caseSource ? [props.state.caseSource] : undefined,
  states:
    props.state.caseState === "all" ? undefined : [props.state.caseState],
  page: props.state.page,
  pageSize: TARGET_CASE_PAGE_SIZE,
}));
const casesQuery = useOverviewTargetCases(workspaceId, caseFilters);
const caseItems = computed(() => casesQuery.data.value?.items ?? []);
const caseTotal = computed(() => casesQuery.data.value?.total ?? 0);
const casePages = computed(() =>
  Math.max(1, Math.ceil(caseTotal.value / TARGET_CASE_PAGE_SIZE)),
);

const detailTargetId = computed(
  () => props.state.detailTarget || targetItems.value[0]?.targetId || "",
);
const detailFilters = computed<TargetDetailFilters>(() => ({
  ...overviewDetailWindow(props.state),
  versions: props.state.detailVersions,
  versionLimit: props.state.detailLimit === "all" ? 0 : props.state.detailLimit,
}));
const detailQuery = useOverviewTargetDetail(
  workspaceId,
  detailTargetId,
  detailFilters,
);
const detail = computed(() => detailQuery.data.value ?? null);

function blockCode(error: Error | null, fallback: string): string {
  return error instanceof ApiError && error.code ? error.code : fallback;
}

const targetsCode = computed(() =>
  blockCode(targetsQuery.error.value, "OVERVIEW_TARGETS_UNAVAILABLE"),
);
const detailCode = computed(() =>
  blockCode(detailQuery.error.value, "OVERVIEW_TARGET_DETAIL_UNAVAILABLE"),
);
const casesCode = computed(() =>
  blockCode(casesQuery.error.value, "OVERVIEW_TARGET_CASES_UNAVAILABLE"),
);

const filterTargetOptions = computed(() =>
  targetItems.value.map((item) => ({
    id: item.targetId,
    name: item.objectName,
    objectType: item.objectType,
  })),
);

function patch(value: Partial<OverviewUrlState>): void {
  emit("patch", value);
}

function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
  }).format(new Date());
}

function fallbackCustomWindow(): { from: string; to: string } {
  const to = shanghaiToday();
  const [year, month, day] = to.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  const start = new Date(Date.UTC(year, month - 1, day - 89));
  return { from: start.toISOString().slice(0, 10), to };
}

function setRange(value: OverviewRangeChoice): void {
  if (value === "custom") {
    if (props.state.range === "custom") return;
    const window =
      effectiveWindow.value ?? props.sharedWindow ?? fallbackCustomWindow();
    patch({
      range: "custom",
      from: window.from,
      to: window.to,
      page: 1,
    });
    return;
  }
  patch({ range: value, from: "", to: "", page: 1 });
}

function setWindow(value: { from: string; to: string }): void {
  patch({
    range: "custom",
    from: value.from,
    to: value.to,
    page: 1,
  });
}

function toggleState(state: TargetState): void {
  const chosen = props.state.states;
  const all: TargetState[] = ["attributed", "nonTarget", "unanalyzed"];
  if (chosen.length === 0) {
    patch({ states: all.filter((item) => item !== state) });
    return;
  }
  if (chosen.includes(state)) {
    if (chosen.length === 1) return;
    patch({ states: chosen.filter((item) => item !== state) });
    return;
  }
  const next = all.filter((item) => chosen.includes(item) || item === state);
  patch({ states: next.length === all.length ? [] : next });
}

function selectBucket(value: { from: string; to: string }): void {
  patch({
    caseFrom: value.from,
    caseTo: value.to,
    page: 1,
  });
  listAnchorScroll();
}

function listAnchorScroll(): void {
  caseAnchor.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

function clearTargetFilters(): void {
  patch({
    targets: [],
    states: [],
    targetPage: 1,
    page: 1,
    caseTarget: "",
    caseSource: "",
    caseState: "all",
    caseFrom: "",
    caseTo: "",
  });
}

function setDetailTarget(targetId: string): void {
  patch({ detailTarget: targetId, detailVersions: [] });
}

function setDetailLimit(limit: DetailVersionLimit): void {
  patch({ detailLimit: limit, detailVersions: [] });
}

function setDetailWindow(value: { from: string; to: string } | null): void {
  patch({
    detailFrom: value?.from ?? "",
    detailTo: value?.to ?? "",
  });
}

/* ── target configuration CRUD, reusing the evolution-target form ── */

const {
  data: evolutionTargetsData,
  createTarget,
  updateTarget,
  deleteTarget,
} = useEvolutionTargets(workspaceId);
const dialogOpen = ref(false);
const editingTarget = ref<EvolutionTarget | null>(null);
const formError = ref<TargetServerError | null>(null);
const operationError = ref("");
const submitting = ref(false);
const editingTargetId = computed(() => editingTarget.value?.id ?? null);
const skillLibrary = useAttributionSkillPackages(workspaceId);
const versionsQuery = useEvolutionTargetVersions(workspaceId, editingTargetId);
const versions = computed(() => versionsQuery.data.value?.versions ?? []);
const versionsLoading = computed(
  () => Boolean(editingTargetId.value) && versionsQuery.isFetching.value,
);
const versionsError = computed(
  () => Boolean(editingTargetId.value) && versionsQuery.isError.value,
);

async function invalidateOverview(): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: queryKeys.overview(props.workspaceId),
  });
}

defineExpose({ openCreate });

function openCreate(): void {
  if (!props.canManage) return;
  operationError.value = "";
  editingTarget.value = null;
  formError.value = null;
  dialogOpen.value = true;
}

function openEdit(item: TargetOverviewItem): void {
  if (!props.canManage) return;
  const target =
    evolutionTargetsData.value?.items.find(
      (candidate) => candidate.id === item.targetId,
    ) ?? null;
  if (!target) {
    operationError.value = "对象配置尚未加载完成，请稍后重试。";
    return;
  }
  operationError.value = "";
  editingTarget.value = target;
  formError.value = null;
  dialogOpen.value = true;
}

async function submitTarget(body: EvolutionTargetWrite): Promise<void> {
  formError.value = null;
  submitting.value = true;
  try {
    if (editingTarget.value) {
      await updateTarget(editingTarget.value.id, body);
      ElMessage.success("进化对象已更新");
    } else {
      await createTarget(body);
      ElMessage.success("进化对象已新增");
    }
    dialogOpen.value = false;
    await invalidateOverview();
  } catch (errorValue) {
    formError.value = targetServerError(errorValue);
  } finally {
    submitting.value = false;
  }
}

async function removeTarget(item: TargetOverviewItem): Promise<void> {
  operationError.value = "";
  try {
    await ElMessageBox.confirm(
      `移除 ${item.objectName} 的配置？有进行中 run 时不可移除。`,
      "移除进化对象",
      {
        type: "warning",
        confirmButtonText: "移除",
        cancelButtonText: "取消",
        distinguishCancelAndClose: true,
      },
    );
  } catch {
    return;
  }
  try {
    await deleteTarget(item.targetId);
    const next: Partial<OverviewUrlState> = {};
    if (props.state.targets.includes(item.targetId)) {
      next.targets = props.state.targets.filter(
        (id) => id !== item.targetId,
      );
    }
    if (props.state.caseTarget === item.targetId) next.caseTarget = "";
    if (props.state.detailTarget === item.targetId) next.detailTarget = "";
    if (Object.keys(next).length > 0) patch(next);
    await invalidateOverview();
    ElMessage.success("进化对象已移除");
  } catch (error) {
    operationError.value =
      error instanceof Error ? error.message : "移除进化对象失败";
  }
}

/* ── keep URL state consistent with the loaded target set ── */

watch(
  targetItems,
  (items) => {
    if (targetsQuery.data.value === undefined) return;
    const known = new Set(items.map((item) => item.targetId));
    const next: Partial<OverviewUrlState> = {};
    const selected = props.state.targets.filter((id) => known.has(id));
    if (selected.length !== props.state.targets.length) next.targets = selected;
    if (props.state.caseTarget && !known.has(props.state.caseTarget)) {
      next.caseTarget = "";
    }
    if (props.state.detailTarget && !known.has(props.state.detailTarget)) {
      next.detailTarget = "";
    }
    if (Object.keys(next).length > 0) patch(next);
  },
  { immediate: true },
);

watch(
  targetItems,
  (items) => {
    if (targetsQuery.data.value === undefined) return;
    const pages = Math.max(1, Math.ceil(items.length / 5));
    if (props.state.targetPage > pages) patch({ targetPage: pages });
  },
);

watch(
  () => casesQuery.data.value,
  (data) => {
    if (!data) return;
    if (props.state.page > casePages.value) {
      patch({ page: casePages.value });
    }
  },
);

</script>

<template>
  <div
    class="targets-view"
    data-testid="ov-targets"
  >
    <p
      v-if="targetsQuery.error.value"
      class="load-error"
      data-testid="ov-target-load-error"
      role="alert"
    >
      对象统计与列表加载失败（{{ targetsCode }}）
      <button
        type="button"
        @click="targetsQuery.refetch()"
      >
        重试
      </button>
    </p>

    <div
      class="statstrip"
      data-testid="ov-target-stats"
    >
      <div class="ss">
        <b data-testid="ov-target-stat-targets">{{ summary?.targets ?? 0 }}</b>
        <span>进化对象</span>
      </div>
      <div class="ss">
        <b data-testid="ov-target-stat-sessions">{{ summary?.sessions ?? 0 }}</b>
        <span>关联 Session</span>
      </div>
      <div class="ss">
        <b data-testid="ov-target-stat-potential">{{ summary?.potential ?? 0 }}</b>
        <span>潜在 bad case</span>
      </div>
      <div class="ss">
        <b
          class="green"
          data-testid="ov-target-stat-attributed"
        >{{ summary?.attributed ?? 0 }}</b>
        <span>已分析 · 是该对象问题</span>
      </div>
      <div class="ss">
        <b
          class="orange"
          data-testid="ov-target-stat-nontarget"
        >{{ summary?.nonTarget ?? 0 }}</b>
        <span>已分析 · 非该对象问题</span>
      </div>
      <div class="ss">
        <b data-testid="ov-target-stat-unanalyzed">{{ summary?.unanalyzed ?? 0 }}</b>
        <span>未分析</span>
      </div>
    </div>

    <TargetsFilterBar
      :grain-effective="grainEffective"
      :options="filterTargetOptions"
      :state="state"
      :window="effectiveWindow"
      @clear="clearTargetFilters"
      @update:grain="patch({ grain: $event, page: 1 })"
      @update:range="setRange"
      @update:targets="patch({ targets: $event, page: 1 })"
      @update:window="setWindow"
    />

    <p
      v-if="operationError"
      class="operation-error"
      role="alert"
    >
      {{ operationError }}
    </p>

    <div class="target-grid">
      <section
        class="chart-card"
        data-testid="ov-target-chart-card"
      >
        <div class="card-head">
          <div>
            <h2>潜在 bad case 趋势</h2>
            <div class="hint">
              按{{ grainLabels[activeGrain] }}聚合 · 可多选进化对象与查看信息
            </div>
          </div>
        </div>
        <TargetTrendChart
          :buckets="buckets"
          :error="trendQuery.error.value"
          :grain="activeGrain"
          :loading="trendQuery.isPending.value"
          :selected-states="state.states"
          @clear-filters="clearTargetFilters"
          @retry="trendQuery.refetch()"
          @select-bucket="selectBucket"
          @toggle-state="toggleState"
        />
        <p class="chart-note">
          柱高为所选信息之和；同一 bad case 可能同时出现在多个进化对象下。
        </p>
        <TargetDistributions
          :buckets="buckets"
          :items="targetItems"
          :selected-states="state.states"
          :selected-targets="state.targets"
        />
      </section>

      <TargetSideList
        :can-manage="canManage"
        :code="targetsCode"
        :error="targetsQuery.error.value"
        :items="targetItems"
        :loading="targetsQuery.isPending.value"
        :page="state.targetPage"
        :selected="state.targets"
        @create="openCreate"
        @edit="openEdit"
        @remove="removeTarget"
        @retry="targetsQuery.refetch()"
        @toggle="
          patch({
            targets: state.targets.includes($event)
              ? state.targets.filter((id) => id !== $event)
              : [...state.targets, $event],
            page: 1,
          })
        "
        @update:page="patch({ targetPage: $event })"
      />
    </div>

    <TargetDetailCard
      :code="detailCode"
      :detail="detail"
      :error="detailQuery.error.value"
      :loading="detailQuery.isPending.value"
      :shared-window="effectiveWindow"
      :state="state"
      :targets="targetItems"
      @create="openCreate"
      @retry="detailQuery.refetch()"
      @update:limit="setDetailLimit"
      @update:target="setDetailTarget"
      @update:versions="patch({ detailVersions: $event })"
      @update:window="setDetailWindow"
    />

    <div ref="caseAnchor">
      <PotentialCaseTable
        :code="casesCode"
        :error="casesQuery.error.value"
        :filters="{
          caseTarget: state.caseTarget,
          caseSource: state.caseSource,
          caseState: state.caseState,
          caseFrom: state.caseFrom,
          caseTo: state.caseTo,
        }"
        :items="caseItems"
        :loading="casesQuery.isPending.value"
        :page="state.page"
        :page-size="TARGET_CASE_PAGE_SIZE"
        :source-options="sourceOptions"
        :target-options="targetItems"
        :total="caseTotal"
        :wid="workspaceId"
        @retry="casesQuery.refetch()"
        @update:filters="patch({ ...$event, page: 1 })"
        @update:page="patch({ page: $event })"
      />
    </div>

    <TargetFormDialog
      v-if="dialogOpen"
      v-model="dialogOpen"
      :packages="skillLibrary.packages.data.value?.items"
      :runtime-enabled="skillLibrary.packages.data.value?.runtimeEnabled"
      :packages-loading="skillLibrary.packages.isPending.value"
      :server-error="formError"
      :submitting="submitting"
      :target="editingTarget"
      :versions="versions"
      :versions-error="versionsError"
      :versions-loading="versionsLoading"
      @submit="submitTarget"
    />
  </div>
</template>

<style scoped>
.targets-view {
  min-width: 0;
}

.statstrip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  margin-bottom: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.ss {
  padding: 10px 14px;
  border-right: 1px solid var(--border);
}

.ss:last-child {
  border-right: 0;
}

.ss b {
  display: block;
  color: var(--text);
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  font-size: 18px;
  line-height: 1.2;
}

.ss b.green {
  color: var(--green);
}

.ss b.orange {
  color: var(--orange);
}

.ss span {
  color: var(--text-faint);
  font-size: 10px;
  white-space: nowrap;
}

.load-error {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
  margin: 0 0 10px;
  padding: 6px 10px;
  border: 1px solid color-mix(in srgb, var(--red) 30%, var(--border));
  border-radius: 7px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  color: var(--red);
  font-size: 11px;
}

.load-error button {
  padding: 2px 8px;
  border: 1px solid color-mix(in srgb, var(--red) 35%, var(--border));
  border-radius: 5px;
  background: var(--bg-card);
  color: var(--red);
  font-size: 10.5px;
  cursor: pointer;
}

.operation-error {
  margin: 0 0 12px;
  padding: 6px 10px;
  border: 1px solid color-mix(in srgb, var(--red) 30%, var(--border));
  border-radius: 7px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  color: var(--red);
  font-size: 11px;
}

.target-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.75fr);
  gap: 12px;
  margin-bottom: 14px;
}

.chart-card {
  min-width: 0;
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

.chart-note {
  margin: 8px 0 0;
  color: var(--text-faint);
  font-size: 10px;
}

@media (max-width: 1100px) {
  .target-grid {
    grid-template-columns: 1fr;
  }

  .statstrip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ss:nth-child(3n) {
    border-right: 0;
  }
}

@media (max-width: 640px) {
  .statstrip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ss:nth-child(3n) {
    border-right: 1px solid var(--border);
  }

  .ss:nth-child(2n) {
    border-right: 0;
  }
}
</style>
