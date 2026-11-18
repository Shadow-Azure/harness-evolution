<script setup lang="ts">
import type {
  OverviewGrain,
  OverviewSourceRow,
  OverviewTrendBucket,
} from "@harness/contracts";
import { computed, ref } from "vue";

import type { OverviewFilters } from "../../../api/overview";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import SourceMatrix from "./SourceMatrix.vue";

const TOP_COUNT = 6;

const props = defineProps({
  sources: {
    type: Array as () => OverviewSourceRow[],
    default: () => [],
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
    default: "OVERVIEW_SOURCES_UNAVAILABLE",
  },
  workspaceId: {
    type: String,
    default: "",
  },
  buckets: {
    type: Array as () => OverviewTrendBucket[],
    default: () => [],
  },
  grain: {
    type: String as () => OverviewGrain,
    default: "week",
  },
  filters: {
    type: Object as () => OverviewFilters,
    default: () => ({ objects: [] }),
  },
});

const emit = defineEmits<{ retry: [] }>();

const expanded = ref(false);

const visible = computed(() =>
  expanded.value ? props.sources : props.sources.slice(0, TOP_COUNT),
);
const rest = computed(() =>
  expanded.value ? [] : props.sources.slice(TOP_COUNT),
);
const restTotals = computed(() =>
  rest.value.reduce(
    (sum, row) => ({
      total: sum.total + row.total,
      self: sum.self + row.self,
      discovery: sum.discovery + row.discovery,
    }),
    { total: 0, self: 0, discovery: 0 },
  ),
);
const maxTotal = computed(() =>
  Math.max(
    1,
    ...props.sources.map((row) => row.total),
    restTotals.value.total,
  ),
);

function width(value: number): string {
  return `${(value / maxTotal.value) * 100}%`;
}
</script>

<template>
  <div
    class="source-bars"
    data-testid="ov-source-bars"
  >
    <LoadingSkeleton
      v-if="loading"
      data-testid="ov-source-bars-loading"
      label="正在加载来源分布"
      :rows="3"
    />
    <ErrorState
      v-else-if="error"
      :code="code"
      data-testid="ov-source-bars-error"
      message="来源分布加载失败，请重试；趋势与列表不受影响。"
      @retry="emit('retry')"
    />
    <p
      v-else-if="sources.length === 0"
      class="source-empty"
      data-testid="ov-source-bars-empty"
    >
      暂无 bad case 上报来源数据
    </p>
    <template v-else>
      <div
        v-for="row in visible"
        :key="row.object"
        class="source-row"
        data-testid="ov-source-bar"
        :title="`${row.object} · 自身存在问题 ${row.self} · 发现前置步骤问题 ${row.discovery}`"
      >
        <span
          class="name"
          :title="row.object"
        >{{ row.object }}</span>
        <span class="bar">
          <span
            class="fill self"
            :style="{ width: width(row.self) }"
          />
          <span
            class="fill discovery"
            :style="{ width: width(row.discovery) }"
          />
        </span>
        <span class="num"><b>{{ row.total }}</b> · 自身 {{ row.self }} / 前置 {{ row.discovery }}</span>
      </div>
      <div
        v-if="rest.length > 0"
        class="source-row rest"
        data-testid="ov-source-rest"
        :title="`其余 ${rest.length} 个来源 · 自身 ${restTotals.self} · 前置 ${restTotals.discovery}`"
      >
        <span class="name">其余 {{ rest.length }} 个来源</span>
        <span class="bar">
          <span
            class="fill self"
            :style="{ width: width(restTotals.self) }"
          />
          <span
            class="fill discovery"
            :style="{ width: width(restTotals.discovery) }"
          />
        </span>
        <span class="num"><b>{{ restTotals.total }}</b> · 自身 {{ restTotals.self }} / 前置 {{ restTotals.discovery }}</span>
      </div>
      <button
        v-if="sources.length > TOP_COUNT"
        class="toggle"
        data-testid="ov-source-expand"
        type="button"
        @click="expanded = !expanded"
      >
        {{ expanded ? "收起为 top 6" : `展开全部 ${sources.length} 个来源` }}
      </button>
      <SourceMatrix
        v-if="workspaceId"
        :buckets="buckets"
        :filters="filters"
        :grain="grain"
        :sources="sources"
        :workspace-id="workspaceId"
      />
    </template>
  </div>
</template>

<style scoped>
.source-bars {
  display: grid;
  min-width: 0;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.source-row {
  display: grid;
  min-width: 0;
  grid-template-columns: 118px minmax(0, 1fr) 148px;
  gap: 10px;
  align-items: center;
  font-size: 11.5px;
}

.name {
  overflow: hidden;
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar {
  display: flex;
  height: 7px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--bg-inset);
}

.fill {
  height: 100%;
}

.fill.self {
  background: var(--blue);
  opacity: 0.82;
}

.fill.discovery {
  background: var(--purple);
  opacity: 0.82;
}

.num {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
  text-align: right;
  white-space: nowrap;
}

.num b {
  color: var(--text-dim);
  font-weight: 600;
}

.source-row.rest .name {
  color: var(--text-faint);
}

.source-empty {
  margin: 0;
  padding: 14px 0 6px;
  color: var(--text-faint);
  font-size: 11.5px;
}

.toggle {
  justify-self: start;
  padding: 2px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  cursor: pointer;
}

.toggle:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

@media (max-width: 640px) {
  .source-row {
    grid-template-columns: minmax(0, 1fr) 120px;
    row-gap: 3px;
  }

  .name {
    grid-column: 1;
  }

  .bar {
    grid-column: 1 / -1;
    grid-row: 2;
  }

  .num {
    grid-column: 2;
    grid-row: 1;
  }
}
</style>
