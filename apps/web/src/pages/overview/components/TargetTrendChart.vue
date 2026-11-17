<script setup lang="ts">
import type {
  OverviewGrain,
  TargetState,
  TargetTrendBucket,
} from "@harness/contracts";
import { computed, ref } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { barLayout, niceTicks, stackSegments } from "../chartGeometry";
import { bucketWindow } from "../overviewUrl";

const CHART_WIDTH = 720;
const CHART_HEIGHT = 220;
const LABEL_STEP_TARGET = 13;

const STATES: TargetState[] = ["attributed", "nonTarget", "unanalyzed"];

const STATE_LABELS: Record<TargetState, string> = {
  attributed: "是该对象问题",
  nonTarget: "非该对象问题",
  unanalyzed: "未分析",
};

const props = defineProps({
  buckets: {
    type: Array as () => TargetTrendBucket[],
    default: () => [],
  },
  grain: {
    type: String as () => OverviewGrain,
    required: true,
  },
  selectedStates: {
    type: Array as () => TargetState[],
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
    default: "OVERVIEW_TARGET_TREND_UNAVAILABLE",
  },
});

const emit = defineEmits<{
  retry: [];
  "select-bucket": [value: { bucket: string; from: string; to: string }];
  "toggle-state": [value: TargetState];
  "clear-filters": [];
}>();

const hovered = ref<number | null>(null);

const chosen = computed<TargetState[]>(() =>
  props.selectedStates.length > 0 ? props.selectedStates : STATES,
);

function bucketTotal(bucket: TargetTrendBucket): number {
  return chosen.value.reduce((sum, state) => sum + bucket[state], 0);
}

const counts = computed<Record<TargetState, number>>(() => {
  const total: Record<TargetState, number> = {
    attributed: 0,
    nonTarget: 0,
    unanalyzed: 0,
  };
  for (const bucket of props.buckets) {
    for (const state of STATES) total[state] += bucket[state];
  }
  return total;
});

const total = computed(() =>
  props.buckets.reduce((sum, bucket) => sum + bucketTotal(bucket), 0),
);
const hasData = computed(() => props.buckets.length > 0 && total.value > 0);
const layout = computed(() => barLayout(props.buckets.length, CHART_WIDTH));
const ticks = computed(() => {
  const highest = Math.max(0, ...props.buckets.map((bucket) => bucketTotal(bucket)));
  return niceTicks(highest, 4);
});
const axisMax = computed(() => ticks.value.at(-1) ?? 1);

type Bar = {
  bucket: TargetTrendBucket;
  index: number;
  x: number;
  y: number;
  heights: number[];
  totalHeight: number;
  window: { from: string; to: string } | null;
  total: number;
};

const bars = computed<Bar[]>(() =>
  props.buckets.map((bucket, index) => {
    const values = chosen.value.map((state) => bucket[state]);
    const geometry = stackSegments(values, 0, CHART_HEIGHT, axisMax.value);
    return {
      bucket,
      index,
      x:
        index * layout.value.slot +
        (layout.value.slot - layout.value.barWidth) / 2,
      y: geometry.y,
      heights: geometry.heights,
      totalHeight: geometry.totalHeight,
      window: bucketWindow(bucket.bucket, props.grain),
      total: values.reduce((sum, value) => sum + value, 0),
    };
  }),
);

const tickRows = computed(() =>
  ticks.value.map((tick) => ({
    value: tick,
    top:
      ((CHART_HEIGHT - (tick / axisMax.value) * CHART_HEIGHT) / CHART_HEIGHT) *
      100,
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
const hoveredShares = computed(() => {
  if (!hoveredBar.value || hoveredBar.value.total <= 0) return [];
  return chosen.value.map((state, index) => ({
    state,
    value: hoveredBar.value?.bucket[state] ?? 0,
    percent: Math.round(
      ((hoveredBar.value?.heights[index] ?? 0) /
        (hoveredBar.value?.totalHeight || 1)) *
        100,
    ),
  }));
});

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
      data-testid="ov-target-chart-loading"
      label="正在加载对象趋势"
      :rows="4"
    />
    <ErrorState
      v-else-if="error"
      :code="code"
      data-testid="ov-target-chart-error"
      message="对象趋势加载失败，请重试；列表与对象卡不受影响。"
      @retry="emit('retry')"
    />
    <div
      v-else-if="!hasData"
      class="ov-empty"
      data-testid="ov-target-chart-empty"
    >
      <b>当前条件下没有潜在 bad case</b>
      <span>调整时间、进化对象或查看信息后重试。</span>
      <button
        data-testid="ov-target-chart-empty-clear"
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
        aria-label="进化对象潜在 bad case 趋势"
        data-testid="ov-target-chart"
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
          v-for="bar in bars"
          :key="bar.bucket.bucket"
          class="bucket"
        >
          <rect
            class="hit"
            :x="bar.index * layout.slot"
            y="0"
            :width="layout.slot"
            :height="CHART_HEIGHT"
            tabindex="0"
            role="button"
            :aria-label="`${bar.bucket.label}：${chosen
              .map((state) => `${STATE_LABELS[state]} ${bar.bucket[state]}`)
              .join('，')}`"
            :data-bucket="bar.bucket.bucket"
            :data-testid="`ov-target-bucket-${bar.index}`"
            @mouseenter="hovered = bar.index"
            @mouseleave="hovered = null"
            @focus="hovered = bar.index"
            @blur="hovered = null"
            @click="select(bar)"
            @keydown.enter.prevent="select(bar)"
            @keydown.space.prevent="select(bar)"
          />
          <rect
            v-for="(state, index) in chosen"
            v-show="bar.bucket[state] > 0"
            :key="state"
            class="segment"
            :class="state"
            :x="bar.x"
            :y="bar.y + bar.heights.slice(index + 1).reduce((sum, value) => sum + value, 0)"
            :width="layout.barWidth"
            :height="bar.heights[index] ?? 0"
            aria-hidden="true"
            :data-testid="`ov-target-segment-${state}`"
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
        data-testid="ov-target-tooltip"
        :style="{ left: `${tooltipLeft}%` }"
      >
        <b>{{ hoveredBar.bucket.label }}</b>
        <span
          v-for="share in hoveredShares"
          :key="share.state"
        >
          {{ STATE_LABELS[share.state] }} {{ share.value }}（{{ share.percent }}%）
        </span>
        <span>合计 {{ hoveredBar.total }}</span>
      </div>
    </div>
    <div
      class="metrics"
      data-testid="ov-target-metrics"
    >
      <span class="metrics-label">趋势图显示</span>
      <div class="metric-chips">
        <button
          v-for="state in STATES"
          :key="state"
          class="metric-chip"
          :class="{ on: chosen.includes(state) }"
          :data-testid="`ov-target-metric-${state}`"
          type="button"
          :title="`切换趋势图与分布里的「${STATE_LABELS[state]}」`"
          @click="emit('toggle-state', state)"
        >
          <i
            class="dot"
            :class="state"
          />{{ STATE_LABELS[state] }}<b>{{ counts[state] }}</b>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-block {
  min-width: 0;
}

.ov-empty {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  border: 1px dashed var(--border);
  border-radius: 9px;
  color: var(--text-faint);
  font-size: 11px;
  text-align: center;
}

.ov-empty b {
  color: var(--text-dim);
  font-size: 12.5px;
}

.ov-empty button {
  margin-top: 6px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

.plot-wrap {
  position: relative;
  height: 220px;
  padding-bottom: 18px;
}

.yaxis {
  position: absolute;
  top: 0;
  bottom: 18px;
  left: 0;
  width: 30px;
}

.yaxis span {
  position: absolute;
  right: 0;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
  transform: translateY(-50%);
}

.plot {
  display: block;
  width: calc(100% - 34px);
  height: 100%;
  margin-left: 34px;
}

.grid line {
  stroke: var(--border);
  stroke-width: 0.5;
}

.hit {
  fill: transparent;
  cursor: pointer;
  outline: none;
}

.hit:focus-visible {
  stroke: var(--blue);
  stroke-width: 1;
}

.segment.attributed {
  fill: var(--green);
}

.segment.nonTarget {
  fill: var(--orange);
}

.segment.unanalyzed {
  fill: var(--border-strong);
}

.labels {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 34px;
  height: 16px;
}

.labels span {
  position: absolute;
  bottom: 0;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9px;
  white-space: nowrap;
  transform: translateX(-50%);
}

.tooltip {
  position: absolute;
  top: 4px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 150px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  box-shadow: var(--shadow-popover);
  color: var(--text-dim);
  font-size: 10px;
  pointer-events: none;
  transform: translateX(-50%);
}

.tooltip b {
  color: var(--text);
  font-size: 10.5px;
}

.metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px dashed var(--border);
}

.metrics-label {
  color: var(--text-faint);
  font-size: 10px;
}

.metric-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.metric-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 11px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s, color 0.12s;
}

.metric-chip b {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--bg-panel);
  color: var(--text);
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 600;
  line-height: 16px;
}

.metric-chip:hover {
  border-color: var(--blue);
  color: var(--text);
}

.metric-chip.on {
  border-color: color-mix(in srgb, var(--blue) 38%, var(--border));
  background: color-mix(in srgb, var(--blue) 7%, var(--bg-card));
  color: var(--text);
}

.metric-chip:not(.on) {
  opacity: 0.55;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot.attributed {
  background: var(--green);
}

.dot.nonTarget {
  background: var(--orange);
}

.dot.unanalyzed {
  background: var(--border-strong);
}

@media (max-width: 640px) {
  .plot-wrap {
    height: 180px;
  }
}
</style>
