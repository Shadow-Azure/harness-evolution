<script setup lang="ts">
import type {
  OverviewGrain,
  OverviewSourceRow,
  OverviewTrendBucket,
} from "@harness/contracts";
import { useQuery } from "@tanstack/vue-query";
import { computed, ref } from "vue";

import { ApiError } from "../../../api/http";
import { getOverviewSources, type OverviewFilters } from "../../../api/overview";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { bucketWindow } from "../overviewUrl";

const MAX_MATRIX_BUCKETS = 31;
const MATRIX_CONCURRENCY = 4;

const props = defineProps<{
  workspaceId: string;
  sources: OverviewSourceRow[];
  buckets: OverviewTrendBucket[];
  grain: OverviewGrain;
  filters: OverviewFilters;
}>();

type MatrixCell = {
  self: number;
  discovery: number;
};

type MatrixRow = {
  object: string;
  total: number;
  self: number;
  discovery: number;
  cells: Record<string, MatrixCell>;
};

type MatrixData = {
  buckets: Pick<OverviewTrendBucket, "bucket" | "label">[];
  rows: MatrixRow[];
};

const open = ref(false);
const manageable = computed(
  () => props.sources.length > 0 && props.buckets.length > 0,
);
const dense = computed(() => props.buckets.length > MAX_MATRIX_BUCKETS);
const enabled = computed(() => open.value && manageable.value && !dense.value);

/**
 * Run one bounded number of bucket reads in parallel.
 * @param items Bucket identifiers to read.
 * @param worker Bucket reader.
 * @returns One result per bucket in input order.
 */
async function mapConcurrent<T>(
  items: string[],
  worker: (bucket: string) => Promise<T>,
): Promise<T[]> {
  const results = new Array<T>(items.length);
  let next = 0;
  const runners = Array.from(
    { length: Math.min(MATRIX_CONCURRENCY, items.length) },
    async () => {
      while (next < items.length) {
        const index = next;
        next += 1;
        results[index] = await worker(items[index] as string);
      }
    },
  );
  await Promise.all(runners);
  return results;
}

/**
 * Read every bucket's source distribution and merge it into one matrix.
 *
 * The overview sources endpoint reports aggregate counts for a date window,
 * not an object × bucket field, so the matrix issues one bounded aggregate
 * query per bucket instead of stitching the eight-row page. The buckets are
 * disjoint, so the joined result is exact for the active filters.
 * @param workspaceId Route workspace identifier.
 * @param buckets Continuous buckets from the trend response.
 * @param grain Effective trend grain.
 * @param filters Active window and object selection.
 * @returns Bucket labels plus zero-completed rows.
 */
async function loadMatrix(
  workspaceId: string,
  buckets: OverviewTrendBucket[],
  grain: OverviewGrain,
  filters: OverviewFilters,
): Promise<MatrixData> {
  const rows = new Map<string, MatrixRow>();
  for (const source of props.sources) {
    rows.set(source.object, {
      object: source.object,
      total: 0,
      self: 0,
      discovery: 0,
      cells: {},
    });
  }
  const bucketResults = await mapConcurrent(
    buckets.map((bucket) => bucket.bucket),
    async (bucket) => {
      const window = bucketWindow(bucket, grain);
      if (!window) return [];
      const response = await getOverviewSources(workspaceId, {
        ...filters,
        from: window.from,
        to: window.to,
      });
      return response.items;
    },
  );
  for (const [index, items] of bucketResults.entries()) {
    const bucket = buckets[index];
    if (!bucket) continue;
    for (const item of items) {
      const row = rows.get(item.object) ?? {
        object: item.object,
        total: 0,
        self: 0,
        discovery: 0,
        cells: {},
      };
      rows.set(item.object, row);
      row.cells[bucket.bucket] = {
        self: item.self,
        discovery: item.discovery,
      };
      row.total += item.total;
      row.self += item.self;
      row.discovery += item.discovery;
    }
  }
  const order = new Map(
    props.sources.map((source, index) => [source.object, index]),
  );
  const ordered = [...rows.values()].sort(
    (left, right) =>
      (order.get(left.object) ?? Number.MAX_SAFE_INTEGER) -
        (order.get(right.object) ?? Number.MAX_SAFE_INTEGER) ||
      right.total - left.total ||
      left.object.localeCompare(right.object),
  );
  return {
    buckets: props.buckets.map((bucket) => ({
      bucket: bucket.bucket,
      label: bucket.label,
    })),
    rows: ordered,
  };
}

const matrix = useQuery({
  queryKey: computed(
    () =>
      [
        "ws",
        props.workspaceId,
        "overview",
        "sourceMatrix",
        { ...props.filters, grain: props.grain },
        props.buckets.map((bucket) => bucket.bucket),
        props.sources.map((source) => `${source.object}:${source.total}`),
      ] as const,
  ),
  queryFn: () =>
    loadMatrix(
      props.workspaceId,
      props.buckets,
      props.grain,
      props.filters,
    ),
  enabled,
});

function cell(row: MatrixRow, bucket: string): MatrixCell {
  return row.cells[bucket] ?? { self: 0, discovery: 0 };
}

const matrixData = computed(() => matrix.data.value ?? null);
const hasData = computed(
  () => (matrixData.value?.rows ?? []).some((row) => row.total > 0),
);
const errorCode = computed(() =>
  matrix.error.value instanceof ApiError && matrix.error.value.code
    ? matrix.error.value.code
    : "OVERVIEW_SOURCES_UNAVAILABLE",
);
</script>

<template>
  <section
    v-if="manageable"
    class="source-matrix"
    data-testid="ov-source-matrix"
  >
    <button
      class="matrix-toggle"
      type="button"
      :aria-expanded="open"
      data-testid="ov-matrix-toggle"
      @click="open = !open"
    >
      <span class="caret">{{ open ? "▾" : "▸" }}</span>
      按 bad case 上报来源 × 时间查看问题类型明细
    </button>
    <div
      v-if="open"
      class="matrix-body"
      data-testid="ov-matrix-body"
    >
      <p
        v-if="dense"
        class="matrix-hint"
        data-testid="ov-matrix-dense"
      >
        当前粒度下时间桶超过 {{ MAX_MATRIX_BUCKETS }} 个，切换为周或月粒度后可查看来源 × 时间明细。
      </p>
      <LoadingSkeleton
        v-else-if="matrix.isPending.value"
        data-testid="ov-matrix-loading"
        label="正在加载来源 × 时间明细"
        :rows="3"
      />
      <ErrorState
        v-else-if="matrix.error.value"
        :code="errorCode"
        data-testid="ov-matrix-error"
        message="来源 × 时间明细加载失败，请重试；来源分布与趋势不受影响。"
        @retry="matrix.refetch()"
      />
      <p
        v-else-if="!hasData"
        class="matrix-empty"
        data-testid="ov-matrix-empty"
      >
        当前筛选下没有可展示的来源 × 时间明细。
      </p>
      <div
        v-else-if="matrixData"
        class="matrix-scroll"
        data-testid="ov-matrix-scroll"
      >
        <table>
          <thead>
            <tr>
              <th scope="col">
                bad case 上报来源
              </th>
              <th
                v-for="bucket in matrixData.buckets"
                :key="bucket.bucket"
                scope="col"
                :title="bucket.bucket"
              >
                {{ bucket.label }}
              </th>
              <th scope="col">
                合计
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in matrixData.rows"
              :key="row.object"
              :data-object="row.object"
              data-testid="ov-matrix-row"
            >
              <th
                scope="row"
                :title="row.object"
              >
                {{ row.object }}
              </th>
              <td
                v-for="bucket in matrixData.buckets"
                :key="bucket.bucket"
                :data-bucket="bucket.bucket"
              >
                <span class="s">自身 {{ cell(row, bucket.bucket).self }}</span>
                /
                <span class="d">前置 {{ cell(row, bucket.bucket).discovery }}</span>
              </td>
              <td class="total">
                <b>{{ row.self }}</b> / <b>{{ row.discovery }}</b>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<style scoped>
.source-matrix {
  min-width: 0;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.matrix-toggle {
  padding: 0;
  border: 0;
  background: none;
  color: var(--text-dim);
  font-size: 10.5px;
  text-align: left;
  cursor: pointer;
}

.matrix-toggle:hover {
  color: var(--text);
}

.caret {
  display: inline-block;
  width: 12px;
  color: var(--text-faint);
}

.matrix-body {
  min-width: 0;
  margin-top: 9px;
}

.matrix-hint,
.matrix-empty {
  margin: 0;
  padding: 8px 0;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.matrix-scroll {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
  white-space: nowrap;
}

th,
td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}

thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-inset);
  color: var(--text-faint);
  font-weight: 600;
}

tbody th {
  position: sticky;
  left: 0;
  z-index: 1;
  max-width: 150px;
  overflow: hidden;
  background: var(--bg-card);
  color: var(--text-dim);
  font-family: var(--mono);
  font-weight: 500;
  text-align: left;
  text-overflow: ellipsis;
}

thead th:first-child {
  left: 0;
  z-index: 2;
  text-align: left;
}

tbody tr:last-child th,
tbody tr:last-child td {
  border-bottom: 0;
}

td {
  color: var(--text-faint);
  font-family: var(--mono);
}

td .s {
  color: var(--blue);
}

td .d {
  color: var(--purple);
}

td.total {
  color: var(--text-dim);
}

td.total b {
  color: var(--text);
  font-weight: 650;
}
</style>
