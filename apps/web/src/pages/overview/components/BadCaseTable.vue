<script setup lang="ts">
import type {
  BadCaseListItem,
  BadCaseTraceStatus,
  OverviewBadCaseType,
} from "@harness/contracts";
import { computed } from "vue";
import { RouterLink } from "vue-router";

import EmptyState from "../../../components/ui/EmptyState.vue";
import ErrorState from "../../../components/ui/ErrorState.vue";
import { workspacePath } from "../../../router/workspace";
import { formatStartedAt } from "../../../utils/sessionDisplay";

const props = defineProps({
  wid: {
    type: String,
    required: true,
  },
  items: {
    type: Array as () => BadCaseListItem[],
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
  type: {
    type: String as () => OverviewBadCaseType,
    default: "all",
  },
  filtered: {
    type: Boolean,
    default: false,
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
    default: "OVERVIEW_CASES_UNAVAILABLE",
  },
});

const emit = defineEmits<{
  retry: [];
  "update:page": [value: number];
  "clear-filters": [];
}>();

const pages = computed(() =>
  Math.max(1, Math.ceil(props.total / Math.max(1, props.pageSize))),
);
const currentPage = computed(() =>
  Math.min(Math.max(1, props.page), pages.value),
);
const outOfRange = computed(
  () =>
    props.total > 0 && props.items.length === 0 && props.page > pages.value,
);
const emptyTitle = computed(() =>
  props.filtered
    ? "当前筛选没有命中 bad case"
    : "这个空间还没有 bad case",
);
const emptyDescription = computed(() =>
  props.filtered
    ? "清空来源、类型或调整时间范围后再试。"
    : "上报 bad case 后，这里会按上报时间倒序列出最近的问题。",
);
const typeLabels: Record<OverviewBadCaseType, string> = {
  all: "全部类型",
  self: "自身存在问题",
  discovery: "发现前置步骤问题",
};
const traceLabels: Record<BadCaseTraceStatus, string> = {
  ready: "就绪",
  pending: "未同步",
  syncing: "同步中",
  failed: "同步失败",
  unavailable: "无可用轨迹",
};

/**
 * Whether one row's normalized Session can already be opened as error detail.
 * @param item Overview row carrying the derived trace state.
 * @returns True only for a ready, readable trace.
 */
function traceReady(item: BadCaseListItem): boolean {
  return item.sessionReady && item.syncStatus === "ready";
}

/**
 * Build the deep link that opens one problem's description tab.
 * @param item Row carrying the workspace-scoped bad-case identity.
 * @returns Workspace error-detail URL with `case` and `tab=desc`.
 */
function caseHref(item: BadCaseListItem): string {
  const query = new URLSearchParams({
    case: item.badCaseId,
    tab: "desc",
  });
  return `${workspacePath(
    props.wid,
    `sessions/${encodeURIComponent(item.sessionId)}/errors`,
  )}?${query.toString()}`;
}
</script>

<template>
  <section
    class="list-card"
    data-testid="ov-case-list"
  >
    <div class="list-head">
      <div>
        <h2>bad case 列表</h2>
        <div class="hint">
          时间段、上报来源、问题类型均可选；点击 ID 在新窗口打开错误详情，无可用轨迹时从「轨迹」列查看状态。
        </div>
      </div>
      <div class="list-meta">
        <span
          v-if="type !== 'all'"
          class="type-chip"
          data-testid="ov-type-chip"
        >
          类型：{{ typeLabels[type] }}
          <button
            type="button"
            aria-label="清除类型筛选"
            data-testid="ov-type-clear"
            @click="emit('clear-filters')"
          >
            ×
          </button>
        </span>
        <span
          class="total"
          data-testid="ov-case-total"
        >共 {{ total }} 条</span>
      </div>
    </div>

    <div
      v-if="loading"
      class="table-loading"
      role="status"
      aria-label="正在加载 bad case 列表"
      data-testid="ov-case-loading"
    >
      <div
        v-for="row in 4"
        :key="row"
        class="skeleton-row"
        aria-hidden="true"
      >
        <span /><span /><span /><span />
      </div>
    </div>
    <ErrorState
      v-else-if="error"
      class="table-state"
      :code="code"
      data-testid="ov-case-error"
      message="bad case 列表加载失败，请重试；趋势与统计不受影响。"
      @retry="emit('retry')"
    />
    <EmptyState
      v-else-if="outOfRange"
      class="table-state"
      data-testid="ov-case-page-out-of-range"
      :description="`当前筛选只有 ${pages} 页，可用下方分页返回有效页。`"
      :title="`第 ${page} 页没有数据`"
    />
    <EmptyState
      v-else-if="items.length === 0"
      class="table-state"
      data-testid="ov-case-empty"
      :description="emptyDescription"
      :title="emptyTitle"
    >
      <template
        v-if="filtered"
        #action
      >
        <button
          class="empty-action"
          data-testid="ov-case-empty-clear"
          type="button"
          @click="emit('clear-filters')"
        >
          清除筛选
        </button>
      </template>
    </EmptyState>
    <div
      v-else
      class="table-wrap"
    >
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>bad case</th>
            <th>bad case 上报来源</th>
            <th>类型</th>
            <th>触发时间</th>
            <th>上报时间</th>
            <th>Session</th>
            <th>轨迹</th>
            <th>归因</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.badCaseId"
            data-testid="ov-case-row"
          >
            <td>
              <a
                v-if="traceReady(item)"
                class="idlink"
                :data-testid="`ov-case-link-${item.badCaseId}`"
                :href="caseHref(item)"
                rel="noopener"
                target="_blank"
                :title="`在新窗口打开 ${item.badCaseId} 的问题描述`"
              >
                {{ item.badCaseId }}
              </a>
              <template v-else>
                <span
                  class="id-plain"
                  :data-testid="`ov-case-id-${item.badCaseId}`"
                  :title="`${item.badCaseId} 的轨迹尚未就绪；点击「查看」打开状态说明`"
                >{{ item.badCaseId }}</span>
                <RouterLink
                  class="trace-link"
                  :data-testid="`ov-case-view-${item.badCaseId}`"
                  :to="caseHref(item)"
                  :title="`查看 ${item.badCaseId} 的轨迹状态`"
                >
                  查看
                </RouterLink>
              </template>
            </td>
            <td class="title-cell">
              {{ item.title }}
            </td>
            <td>
              <span class="chip">{{ item.objectName }}</span>
            </td>
            <td>
              <span
                class="badge"
                :class="item.badCaseType"
              >{{ item.badCaseTypeLabel }}</span>
            </td>
            <td class="mono">
              {{ formatStartedAt(item.triggerAt) }}
            </td>
            <td class="mono">
              {{ formatStartedAt(item.createdAt) }}
            </td>
            <td
              class="mono session-cell"
              :title="item.sessionId"
            >
              {{ item.sessionId.slice(0, 13) }}…
            </td>
            <td>
              <span
                class="trace-chip"
                :class="`trace-${item.syncStatus}`"
                :data-testid="`ov-trace-${item.badCaseId}`"
                :title="item.lastError ?? ''"
              >{{ traceLabels[item.syncStatus] }}</span>
            </td>
            <td class="attr">
              <b>{{ item.attributionCount }}</b> 条
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-if="!loading && !error && (items.length > 0 || outOfRange)"
      class="pager"
      data-testid="ov-pager"
    >
      <span class="info">共 {{ total }} 条 · 第 {{ currentPage }} / {{ pages }} 页</span>
      <button
        data-testid="ov-page-prev"
        type="button"
        :disabled="currentPage <= 1"
        @click="emit('update:page', currentPage - 1)"
      >
        ← 上一页
      </button>
      <button
        data-testid="ov-page-next"
        type="button"
        :disabled="currentPage >= pages"
        @click="emit('update:page', currentPage + 1)"
      >
        下一页 →
      </button>
    </div>
  </section>
</template>

<style scoped>
.list-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.list-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-start;
  padding: 13px 16px 11px;
  border-bottom: 1px solid var(--border);
}

.list-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 13.5px;
  font-weight: 650;
}

.hint {
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
}

.list-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.total {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
}

.type-chip {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  padding: 1px 7px;
  border: 1px solid color-mix(in srgb, var(--blue) 36%, var(--border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
  color: var(--text-dim);
  font-size: 10.5px;
}

.type-chip button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--text-faint);
  cursor: pointer;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
  font-size: 11.5px;
}

th,
td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

th {
  background: var(--bg-panel);
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 650;
  white-space: nowrap;
}

tbody tr:hover {
  background: color-mix(in srgb, var(--blue) 3%, transparent);
}

tbody tr:last-child td {
  border-bottom: 0;
}

.idlink {
  color: var(--blue);
  font-family: var(--mono);
  font-size: 10.5px;
  text-decoration: none;
  white-space: nowrap;
}

.idlink:hover {
  text-decoration: underline;
}

.id-plain {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
  white-space: nowrap;
}

.trace-link {
  margin-left: 6px;
  color: var(--blue);
  font-size: 10.5px;
  text-decoration: underline;
  white-space: nowrap;
}

.trace-chip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  color: var(--text-dim);
  font-size: 10px;
  white-space: nowrap;
}

.trace-chip::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-faint);
}

.trace-chip.trace-ready {
  color: var(--green);
}

.trace-chip.trace-ready::before {
  background: var(--green);
}

.trace-chip.trace-pending,
.trace-chip.trace-syncing,
.trace-chip.trace-failed,
.trace-chip.trace-unavailable {
  color: var(--orange);
}

.trace-chip.trace-pending::before,
.trace-chip.trace-syncing::before,
.trace-chip.trace-failed::before,
.trace-chip.trace-unavailable::before {
  background: var(--orange);
}

.title-cell {
  min-width: 220px;
  color: var(--text);
  font-weight: 600;
}

.chip {
  display: inline-block;
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 9.5px;
  white-space: nowrap;
}

.badge {
  display: inline-block;
  padding: 1px 7px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 9.5px;
  white-space: nowrap;
}

.badge.self {
  border-color: color-mix(in srgb, var(--blue) 32%, transparent);
  background: color-mix(in srgb, var(--blue) 10%, transparent);
  color: var(--blue);
}

.badge.discovery {
  border-color: color-mix(in srgb, var(--purple) 32%, transparent);
  background: color-mix(in srgb, var(--purple) 10%, transparent);
  color: var(--purple);
}

.mono {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10.5px;
  white-space: nowrap;
}

.session-cell {
  max-width: 132px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attr {
  color: var(--text-dim);
  font-size: 10.5px;
  white-space: nowrap;
}

.attr b {
  color: var(--text);
  font-family: var(--mono);
}

.pager {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  align-items: center;
  padding: 9px 14px;
  color: var(--text-dim);
  font-size: 11px;
}

.pager .info {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
}

.pager button {
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

.pager button:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--text);
}

.pager button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.table-loading {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
}

.skeleton-row {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) 110px 70px;
  gap: 12px;
}

.skeleton-row span {
  height: 12px;
  border-radius: 4px;
  background: var(--bg-inset);
  animation: pulse 1.5s ease-in-out infinite alternate;
}

.skeleton-row span:nth-child(2) {
  width: 84%;
}

.skeleton-row span:nth-child(4) {
  width: 64%;
}

.table-state {
  margin: 14px 16px;
}

.empty-action {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

@keyframes pulse {
  from {
    opacity: 0.45;
  }

  to {
    opacity: 1;
  }
}
</style>
