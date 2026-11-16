<script setup lang="ts">
import type { OverviewGrain, OverviewTrendBucket } from "@harness/contracts";
import { computed, ref } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import {
  barLayout,
  niceTicks,
  percent,
  stackY,
  type StackGeometry,
} from "../chartGeometry";
import { bucketWindow } from "../overviewUrl";

const CHART_WIDTH = 720;
const CHART_HEIGHT = 220;
const LABEL_STEP_TARGET = 14;

const props = defineProps({
  buckets: {
    type: Array as () => OverviewTrendBucket[],
    default: () => [],
  },
  grain: {
    type: String as () => OverviewGrain,
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
    default: "OVERVIEW_TREND_UNAVAILABLE",
  },
});

const emit = defineEmits<{
  retry: [];
  "select-bucket": [value: { bucket: string; from: string; to: string }];
  "clear-filters": [];
}>();

const hovered = ref<number | null>(null);

const total = computed(() =>
  props.buckets.reduce((sum, bucket) => sum + bucket.total, 0),
);
const hasData = computed(() => props.buckets.length > 0 && total.value > 0);
const layout = computed(() => barLayout(props.buckets.length, CHART_WIDTH));
const ticks = computed(() => {
  const highest = Math.max(0, ...props.buckets.map((bucket) => bucket.total));
  return niceTicks(highest, 4);
});
const axisMax = computed(() => ticks.value.at(-1) ?? 1);

type Bar = {
  bucket: OverviewTrendBucket;
  geometry: StackGeometry;
  x: number;
  window: { from: string; to: string } | null;
  selfPercent: number;
  discoveryPercent: number;
};

const bars = computed<Bar[]>(() =>
  props.buckets.map((bucket, index) => {
    const share = percent(bucket.self, bucket.discovery);
    return {
      bucket,
      geometry: stackY(
        bucket.self,
        bucket.discovery,
        0,
        CHART_HEIGHT,
        axisMax.value,
      ),
      x:
        index * layout.value.slot +
        (layout.value.slot - layout.value.barWidth) / 2,
      window: bucketWindow(bucket.bucket, props.grain),
      selfPercent: share.self,
      discoveryPercent: share.discovery,
    };
  }),
);

const tickRows = computed(() =>
  ticks.value.map((tick) => ({
    value: tick,
    top: ((CHART_HEIGHT - (tick / axisMax.value) * CHART_HEIGHT) / CHART_HEIGHT) * 100,
  })),
);

const labelEvery = computed(() =>
  Math.max(1, Math.ceil(props.buckets.length / LABEL_STEP_TARGET)),
);

const labels = computed(() =>
  props.buckets.map((bucket, index) => ({
    key: `${bucket.bucket}-${index}`,
    text: bucket.label,
    visible:
      index % labelEvery.value === 0 || index === props.buckets.length - 1,
    left: ((index + 0.5) / props.buckets.length) * 100,
  })),
);

const hoveredBar = computed(() =>
  hovered.value === null ? null : bars.value[hovered.value] ?? null,
);

const tooltipLeft = computed(() =>
  hovered.value === null
    ? 0
    : ((hovered.value + 0.5) / Math.max(1, props.buckets.length)) * 100,
);

function select(bar: Bar): void {
  if (!bar.window) return;
  emit("select-bucket", {
    bucket: bar.bucket.bucket,
    from: bar.window.from,
    to: bar.window.to,
  });
}
</script>

<template>
  <div class="chart-block">
    <LoadingSkeleton
      v-if="loading"
      data-testid="ov-chart-loading"
      label="正在加载趋势"
      :rows="4"
    />
    <ErrorState
      v-else-if="error"
      :code="code"
      data-testid="ov-chart-error"
      message="趋势加载失败，请重试；列表不受影响。"
      @retry="emit('retry')"
    />
    <div
      v-else-if="!hasData"
      class="ov-empty"
      data-testid="ov-chart-empty"
    >
      <b>当前条件下没有 bad case</b>
      <span>调整时间范围或 bad case 上报来源后重试。</span>
      <button
        data-testid="ov-chart-empty-clear"
        type="button"
        @click="emit('clear-filters')"
      >
        清除筛选
      </button>
    </div>
    <div
      v-else
      class="plot-wrap"
      :class="{ dense: layout.dense }"
    >
      <div
        class="yaxis"
        aria-hidden="true"
      >
        <span
          v-for="tick in tickRows"
          :key="tick.value"
          :style="{ top: `${tick.top}%` }"
        >{{ tick.value }}</span>
      </div>
      <svg
        class="plot"
        :viewBox="`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`"
        preserveAspectRatio="none"
        role="img"
        aria-label="bad case 趋势"
        data-testid="ov-chart"
      >
        <g class="grid">
          <line
            v-for="tick in tickRows"
            :key="tick.value"
            x1="0"
            :x2="CHART_WIDTH"
            :y1="(tick.top / 100) * CHART_HEIGHT"
            :y2="(tick.top / 100) * CHART_HEIGHT"
          />
        </g>
        <g
          v-for="(bar, index) in bars"
          :key="bar.bucket.bucket"
          class="bucket"
        >
          <rect
            class="hit"
            :x="index * layout.slot"
            y="0"
            :width="layout.slot"
            :height="CHART_HEIGHT"
            tabindex="0"
            role="button"
            :aria-label="`${bar.bucket.label}：自身存在问题 ${bar.bucket.self}，发现前置步骤问题 ${bar.bucket.discovery}`"
            :data-bucket="bar.bucket.bucket"
            :data-testid="`ov-bucket-${index}`"
            @mouseenter="hovered = index"
            @mouseleave="hovered = null"
            @focus="hovered = index"
            @blur="hovered = null"
            @click="select(bar)"
            @keydown.enter.prevent="select(bar)"
            @keydown.space.prevent="select(bar)"
          />
          <rect
            v-if="bar.bucket.self > 0"
            class="segment self"
            :x="bar.x"
            :y="bar.geometry.y + bar.geometry.discoveryHeight"
            :width="layout.barWidth"
            :height="bar.geometry.selfHeight"
            aria-hidden="true"
          />
          <rect
            v-if="bar.bucket.discovery > 0"
            class="segment discovery"
            :x="bar.x"
            :y="bar.geometry.y"
            :width="layout.barWidth"
            :height="bar.geometry.discoveryHeight"
            aria-hidden="true"
          />
        </g>
      </svg>
      <div
        class="labels"
        aria-hidden="true"
      >
        <span
          v-for="label in labels"
          :key="label.key"
          :style="{ left: `${label.left}%` }"
        >{{ label.visible ? label.text : "" }}</span>
      </div>
      <div
        v-if="hoveredBar"
        class="tooltip"
        data-testid="ov-tooltip"
        :style="{ left: `${tooltipLeft}%` }"
      >
        <b>{{ hoveredBar.bucket.label }}</b>
        <span>自身存在问题 {{ hoveredBar.bucket.self }}（{{ Math.round(hoveredBar.selfPercent) }}%）</span>
        <span>发现前置步骤问题 {{ hoveredBar.bucket.discovery }}（{{ Math.round(hoveredBar.discoveryPercent) }}%）</span>
        <span>合计 {{ hoveredBar.bucket.total }}</span>
      </div>
      <p
        v-if="layout.dense"
        class="dense-hint"
        data-testid="ov-chart-dense-hint"
      >
        {{ buckets.length }} 个时间桶，标签已稀疏展示
      </p>
    </div>
  </div>
</template>

<style scoped>
.chart-block {
  min-height: 214px;
}

.ov-empty {
  display: grid;
  justify-items: center;
  gap: 5px;
  padding: 34px 16px;
  color: var(--text-faint);
  font-size: 12px;
  text-align: center;
}

.ov-empty b {
  color: var(--text-dim);
  font-size: 13px;
}

.ov-empty button {
  margin-top: 6px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

.plot-wrap {
  position: relative;
  padding: 0 0 24px 36px;
}

.plot {
  display: block;
  width: 100%;
  height: 244px;
  overflow: visible;
}

.grid line {
  stroke: var(--border);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.segment.self {
  fill: var(--blue);
  opacity: 0.82;
}

.segment.discovery {
  fill: var(--purple);
  opacity: 0.82;
}

.bucket:hover .segment,
.bucket:focus-within .segment {
  opacity: 1;
}

.hit {
  fill: transparent;
  cursor: pointer;
  outline: none;
}

.hit:focus-visible {
  stroke: var(--blue);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.yaxis {
  position: absolute;
  top: 0;
  bottom: 24px;
  left: 0;
  width: 32px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-faint);
}

.yaxis span {
  position: absolute;
  right: 6px;
  transform: translateY(-50%);
}

.labels {
  position: absolute;
  right: 0;
  bottom: 2px;
  left: 36px;
  height: 18px;
}

.labels span {
  position: absolute;
  transform: translateX(-50%);
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
  white-space: nowrap;
}

.dense .labels span {
  font-size: 9px;
}

.tooltip {
  position: absolute;
  top: 4px;
  z-index: 6;
  display: grid;
  gap: 1px;
  min-width: 186px;
  padding: 5px 8px;
  border-radius: 6px;
  background: var(--text);
  color: var(--bg-card);
  font-size: 10px;
  line-height: 1.55;
  transform: translateX(-50%);
  box-shadow: var(--shadow-popover);
  pointer-events: none;
}

.tooltip b {
  color: var(--bg-card);
  font-family: var(--mono);
  font-size: 10.5px;
}

.dense-hint {
  position: absolute;
  right: 0;
  bottom: -2px;
  margin: 0;
  color: var(--text-faint);
  font-size: 9.5px;
}
</style>
