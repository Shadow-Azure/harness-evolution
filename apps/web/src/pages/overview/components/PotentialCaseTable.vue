<script setup lang="ts">
import type {
  TargetCaseItem,
  TargetState,
} from "@harness/contracts";
import { computed, ref, watch } from "vue";

import EmptyState from "../../../components/ui/EmptyState.vue";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import type { TargetOverviewItemView } from "../../../api/overview";
import { workspacePath } from "../../../router/workspace";
import { attributionCategory } from "../../../utils/attributionCategory";
import { formatStartedAt } from "../../../utils/sessionDisplay";

const STATE_LABELS: Record<TargetState, string> = {
  attributed: "已分析 · 是该对象问题",
  nonTarget: "已分析 · 非该对象问题",
  unanalyzed: "未分析",
};

type CaseFilters = {
  caseTarget: string;
  caseSource: string;
  caseState: TargetState | "all";
  caseFrom: string;
  caseTo: string;
};

const props = defineProps({
  wid: {
    type: String,
    required: true,
  },
  items: {
    type: Array as () => TargetCaseItem[],
    default: () => [],
  },
  total: {
    type: Number,
    default: 0,
  },
  page: {
    type: Number,
    default: 1,
  },
  pageSize: {
    type: Number,
    default: 8,
  },
  targetOptions: {
    type: Array as () => TargetOverviewItemView[],
    default: () => [],
  },
  sourceOptions: {
    type: Array as () => string[],
    default: () => [],
  },
  filters: {
    type: Object as () => CaseFilters,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: Object as () => Error | null,
    default: null,
  },
  code: {
    type: String,
    default: "OVERVIEW_TARGET_CASES_UNAVAILABLE",
  },
});

const emit = defineEmits<{
  retry: [];
  "update:page": [value: number];
  "update:filters": [value: Partial<CaseFilters>];
}>();

const draftFrom = ref(props.filters.caseFrom);
const draftTo = ref(props.filters.caseTo);

watch(
  () => props.filters.caseFrom,
  (value) => {
    if (value !== draftFrom.value) draftFrom.value = value;
  },
);
watch(
  () => props.filters.caseTo,
  (value) => {
    if (value !== draftTo.value) draftTo.value = value;
  },
);

const pages = computed(() =>
  Math.max(1, Math.ceil(props.total / Math.max(1, props.pageSize))),
);
const currentPage = computed(() =>
  Math.min(Math.max(1, props.page), pages.value),
);
const filtered = computed(
  () =>
    Boolean(props.filters.caseTarget) ||
    Boolean(props.filters.caseSource) ||
    props.filters.caseState !== "all" ||
    Boolean(props.filters.caseFrom && props.filters.caseTo),
);

/** The member column only appears once a target row carries more than one member. */
const hasMemberColumn = computed(() =>
  props.targetOptions.some((item) => (item.members?.length ?? 0) > 1),
);

const emptyTitle = computed(() =>
  filtered.value
    ? "没有符合条件的潜在 bad case"
    : "这个空间还没有潜在 bad case",
);
const emptyDescription = computed(() =>
  filtered.value
    ? "调整进化对象、上报来源、状态或时间范围后再试。"
    : "配置进化对象并上报 bad case 后，这里会列出对象版本下的潜在记录。",
);

/**
 * Build the case deep link, optionally targeting one attribution report.
 * @param item Row carrying the workspace-scoped case and attribution identity.
 * @param tab Destination tab; `attr` jumps to the attribution analysis.
 * @returns Workspace error-detail URL.
 */
function caseHref(item: TargetCaseItem, tab: "desc" | "attr"): string {
  const query = new URLSearchParams({ case: item.badCaseId, tab });
  if (tab === "attr" && item.attributionId) {
    query.set("at", item.attributionId);
  }
  return `${workspacePath(
    props.wid,
    `sessions/${encodeURIComponent(item.sessionId)}/errors`,
  )}?${query.toString()}`;
}

function targetChanged(event: Event): void {
  emit("update:filters", {
    caseTarget: (event.target as HTMLSelectElement).value,
  });
}

function sourceChanged(event: Event): void {
  emit("update:filters", {
    caseSource: (event.target as HTMLSelectElement).value,
  });
}

function stateChanged(event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  emit("update:filters", {
    caseState: value === "all" ? "all" : (value as TargetState),
  });
}

function dateChanged(field: "caseFrom" | "caseTo", event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  if (field === "caseFrom") draftFrom.value = value;
  else draftTo.value = value;
  if (draftFrom.value && draftTo.value && draftFrom.value <= draftTo.value) {
    emit("update:filters", {
      caseFrom: draftFrom.value,
      caseTo: draftTo.value,
    });
  }
}

function reset(): void {
  draftFrom.value = "";
  draftTo.value = "";
  emit("update:filters", {
    caseTarget: "",
    caseSource: "",
    caseState: "all",
    caseFrom: "",
    caseTo: "",
  });
}
</script>

<template>
  <section
    class="list-card"
    data-testid="ov-target-case-list"
  >
    <div class="list-head">
      <div>
        <h2>潜在 bad case</h2>
        <div class="hint">
          按进化对象、上报来源、分析状态和时间分页查看；已分析的记录可打开归因报告。
        </div>
      </div>
    </div>

    <div
      class="filters"
      data-testid="ov-target-case-filters"
    >
      <select
        class="inp"
        data-testid="ov-target-case-target"
        :value="filters.caseTarget"
        aria-label="按进化对象筛选"
        @change="targetChanged"
      >
        <option value="">
          全部进化对象
        </option>
        <option
          v-for="item in targetOptions"
          :key="item.targetId"
          :value="item.targetId"
        >
          {{ item.objectName }}<span v-if="(item.members?.length ?? 0) > 1"> · {{ item.members?.length }} 个对象</span>
        </option>
      </select>
      <select
        class="inp"
        data-testid="ov-target-case-source"
        :value="filters.caseSource"
        aria-label="按上报来源筛选"
        @change="sourceChanged"
      >
        <option value="">
          全部上报来源
        </option>
        <option
          v-for="source in sourceOptions"
          :key="source"
          :value="source"
        >
          {{ source }}
        </option>
      </select>
      <select
        class="inp"
        data-testid="ov-target-case-state"
        :value="filters.caseState"
        aria-label="按分析状态筛选"
        @change="stateChanged"
      >
        <option value="all">
          全部状态
        </option>
        <option value="attributed">
          是该对象问题
        </option>
        <option value="nonTarget">
          非该对象问题
        </option>
        <option value="unanalyzed">
          未分析
        </option>
      </select>
      <input
        class="inp"
        data-testid="ov-target-case-from"
        type="date"
        :value="draftFrom"
        aria-label="列表开始日期"
        @change="dateChanged('caseFrom', $event)"
      >
      <span class="label">~</span>
      <input
        class="inp"
        data-testid="ov-target-case-to"
        type="date"
        :value="draftTo"
        aria-label="列表结束日期"
        @change="dateChanged('caseTo', $event)"
      >
      <button
        class="reset"
        data-testid="ov-target-case-reset"
        type="button"
        @click="reset"
      >
        重置
      </button>
    </div>

    <LoadingSkeleton
      v-if="loading"
      data-testid="ov-target-case-loading"
      label="正在加载潜在 bad case"
      :rows="5"
    />
    <ErrorState
      v-else-if="error"
      :code="code"
      data-testid="ov-target-case-error"
      message="潜在 bad case 列表加载失败，请重试。"
      @retry="emit('retry')"
    />
    <EmptyState
      v-else-if="items.length === 0 && total === 0"
      :description="emptyDescription"
      :title="emptyTitle"
      data-testid="ov-target-case-empty"
    />
    <template v-else>
      <div class="table-scroll">
        <table class="case-table">
          <thead>
            <tr>
              <th>潜在 bad case</th>
              <th>{{ hasMemberColumn ? "成员" : "进化对象" }}</th>
              <th>bad case 上报来源</th>
              <th>状态</th>
              <th>上报时间</th>
              <th>Session</th>
              <th>归因报告 ID</th>
              <th>归因分类</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="items.length === 0">
              <td
                colspan="8"
                class="page-empty"
              >
                当前页没有记录，请返回上一页。
              </td>
            </tr>
            <tr
              v-for="item in items"
              :key="`${item.badCaseId}-${item.objectName}-${item.objectVersion}`"
              data-testid="ov-target-case-row"
            >
              <td class="case-cell">
                <a
                  class="idlink"
                  :href="caseHref(item, 'desc')"
                  target="_blank"
                  rel="noopener"
                  :title="`打开 ${item.badCaseId} 的 Session 错误详情`"
                >{{ item.badCaseId }}</a>
                <span class="case-title">{{ item.title }}</span>
              </td>
              <td
                class="target-cell"
                :data-member-column="hasMemberColumn ? 'true' : undefined"
              >
                <span class="chip kind">{{ item.objectType }}</span>
                <span class="target-version">{{ item.objectName }}@{{ item.objectVersion }}</span>
              </td>
              <td><span class="chip">{{ item.source }}</span></td>
              <td>
                <span
                  class="state-badge"
                  :class="item.state"
                >{{ STATE_LABELS[item.state] }}</span>
              </td>
              <td class="mono">
                {{ formatStartedAt(item.createdAt) }}
              </td>
              <td
                class="mono"
                :title="item.sessionId"
              >
                {{ item.sessionId.slice(0, 13) }}…
              </td>
              <td class="mono">
                <a
                  v-if="item.attributionId"
                  class="idlink"
                  :href="caseHref(item, 'attr')"
                  target="_blank"
                  rel="noopener"
                  :title="`打开归因 ${item.attributionId}`"
                >{{ item.attributionId }}</a>
                <span
                  v-else
                  class="faint"
                >—</span>
              </td>
              <td class="mono">
                <span v-if="item.category">{{ attributionCategory(item.category) }}</span>
                <span
                  v-else
                  class="faint"
                >—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        class="pager"
        data-testid="ov-target-case-pager"
      >
        <span class="info">共 {{ total }} 条 · 第 {{ currentPage }} / {{ pages }} 页</span>
        <button
          :disabled="currentPage <= 1"
          data-testid="ov-target-case-prev"
          type="button"
          @click="emit('update:page', currentPage - 1)"
        >
          ← 上一页
        </button>
        <button
          :disabled="currentPage >= pages"
          data-testid="ov-target-case-next"
          type="button"
          @click="emit('update:page', currentPage + 1)"
        >
          下一页 →
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.list-card {
  padding: 14px 16px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.list-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
}

.hint {
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.55;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
  padding: 10px 0 12px;
}

.inp {
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text);
  font-size: 11px;
}

select.inp {
  min-width: 130px;
}

.label {
  color: var(--text-faint);
  font-size: 10px;
}

.reset {
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  cursor: pointer;
}

.reset:hover {
  border-color: var(--text-faint);
  color: var(--text);
}

.table-scroll {
  overflow-x: auto;
}

.case-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.case-table th {
  padding: 7px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 500;
  text-align: left;
  white-space: nowrap;
}

.case-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  vertical-align: top;
}

.case-table tr:last-child td {
  border-bottom: 0;
}

.page-empty {
  padding: 18px 8px;
  color: var(--text-faint);
  font-size: 11px;
  text-align: center;
}

.case-cell {
  min-width: 160px;
  max-width: 260px;
}

.idlink {
  color: var(--blue);
  font-family: var(--mono);
  font-size: 10.5px;
  text-decoration: none;
}

.idlink:hover {
  text-decoration: underline;
}

.case-title {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: var(--text-dim);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 9.5px;
  white-space: nowrap;
}

.chip.kind {
  border-radius: 4px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9px;
}

.target-cell {
  white-space: nowrap;
}

.target-version {
  display: inline-block;
  margin-left: 5px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 10px;
  white-space: nowrap;
}

.state-badge {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 9.5px;
  white-space: nowrap;
}

.state-badge.attributed {
  border-color: color-mix(in srgb, var(--green) 32%, var(--border));
  background: color-mix(in srgb, var(--green) 7%, var(--bg-card));
  color: var(--green);
}

.state-badge.nonTarget {
  border-color: color-mix(in srgb, var(--orange) 32%, var(--border));
  background: color-mix(in srgb, var(--orange) 7%, var(--bg-card));
  color: var(--orange);
}

.state-badge.unanalyzed {
  color: var(--text-faint);
}

.mono {
  font-family: var(--mono);
  font-size: 10px;
  white-space: nowrap;
}

.faint {
  color: var(--text-faint);
}

.pager {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10px;
}

.pager .info {
  margin-right: auto;
}

.pager button {
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  cursor: pointer;
}

.pager button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
