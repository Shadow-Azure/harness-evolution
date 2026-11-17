<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import type {
  BadCaseMarker,
  Lane,
  LaneBar,
  LaneModel,
  LaneSpawnGroup,
  LaneViewport,
} from "../types";
import {
  LANE_BAR_H,
  LANE_MAIN_BAR_TOP,
  LANE_TOP,
} from "../types";
import {
  centerOn,
  fitViewport,
  pan,
  resetViewport,
  zoomAt,
} from "./viewport";

defineOptions({ name: "LaneDag" });

const props = withDefaults(
  defineProps<{
    model: LaneModel;
    selectedCaseId?: string | null;
    height?: string;
  }>(),
  {
    selectedCaseId: null,
    height: "clamp(360px, 48vh, 520px)",
  },
);

const emit = defineEmits<{
  "select-case": [badCaseId: string];
  locate: [badCaseId: string];
}>();

const viewportEl = ref<HTMLElement | null>(null);
const view = ref<LaneViewport>(resetViewport());
const panning = ref(false);
const userAdjusted = ref(false);
let drag:
  | { pointerId: number; startX: number; startY: number; originX: number; originY: number }
  | null = null;
let fitTimer: ReturnType<typeof setTimeout> | undefined;
let resizeObserver: ResizeObserver | undefined;

const selectedMarker = computed<BadCaseMarker | null>(() => {
  if (!props.selectedCaseId) {
    return null;
  }
  return (
    props.model.caseMarkers.find(
      (marker) => marker.badCaseId === props.selectedCaseId,
    ) ?? null
  );
});

const selectedBarId = computed(() => selectedMarker.value?.barId ?? null);

function viewportSize() {
  const element = viewportEl.value;
  return {
    width: element?.clientWidth ?? 0,
    height: element?.clientHeight ?? 0,
  };
}

function scheduleFit(delay = 40) {
  if (fitTimer !== undefined) {
    clearTimeout(fitTimer);
  }
  fitTimer = setTimeout(() => {
    fitTimer = undefined;
    fit();
    if (props.selectedCaseId) {
      locateBadCase(props.selectedCaseId);
    }
  }, delay);
}

/**
 * Fit the full lane canvas into the small viewport and center it.
 *
 * @returns Nothing.
 */
function fit() {
  const { width, height } = viewportSize();
  if (!width || !height) {
    return;
  }
  view.value = fitViewport(props.model.width, props.model.height, width, height);
  userAdjusted.value = false;
}

/**
 * Reset the canvas to 1:1 at the origin.
 *
 * @returns Nothing.
 */
function reset() {
  view.value = resetViewport();
  userAdjusted.value = true;
}

/**
 * Zoom around the viewport center.
 *
 * @param factor Multiplicative zoom factor.
 * @returns Nothing.
 */
function zoomBy(factor: number) {
  const { width, height } = viewportSize();
  view.value = zoomAt(view.value, factor, width / 2, height / 2);
  userAdjusted.value = true;
}

function onWheel(event: WheelEvent) {
  event.preventDefault();
  const element = viewportEl.value;
  if (!element) {
    return;
  }
  const rect = element.getBoundingClientRect();
  view.value = zoomAt(
    view.value,
    event.deltaY < 0 ? 1.12 : 0.89,
    event.clientX - rect.left,
    event.clientY - rect.top,
  );
  userAdjusted.value = true;
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0 || !viewportEl.value) {
    return;
  }
  viewportEl.value.setPointerCapture(event.pointerId);
  drag = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: view.value.x,
    originY: view.value.y,
  };
  panning.value = true;
}

function onPointerMove(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) {
    return;
  }
  view.value = pan(
    { ...view.value, x: drag.originX, y: drag.originY },
    event.clientX - drag.startX,
    event.clientY - drag.startY,
  );
  userAdjusted.value = true;
}

function onPointerUp() {
  const element = viewportEl.value;
  if (drag && element?.hasPointerCapture(drag.pointerId)) {
    element.releasePointerCapture(drag.pointerId);
  }
  drag = null;
  panning.value = false;
}

function barTitle(bar: LaneBar): string {
  return bar.title || bar.label;
}

function laneBarTop(lane: Lane): number {
  return lane.barTop;
}

function laneLabelTop(lane: Lane): number {
  return lane.top;
}

function spawnY(group: LaneSpawnGroup): number {
  return group.parentTop + group.parentBarTop + LANE_BAR_H - LANE_TOP;
}

function memberBarY(group: LaneSpawnGroup, laneId: string): number {
  const member = group.members.find((item) => item.laneId === laneId);
  return (member?.top ?? group.parentTop) + (member?.barTop ?? 4) - LANE_TOP;
}

function spawnPath(group: LaneSpawnGroup, laneId: string): string {
  const member = group.members.find((item) => item.laneId === laneId);
  if (!member) {
    return "";
  }
  const barY = memberBarY(group, laneId);
  if (group.adjacentOnly) {
    return `M ${member.trigger * 10} ${spawnY(group)} L ${member.start * 10} ${barY}`;
  }
  return `M ${group.trunk * 10} ${barY - 5} L ${member.start * 10} ${barY - 5} L ${member.start * 10} ${barY}`;
}

function trunkPath(group: LaneSpawnGroup): string {
  const y1 = spawnY(group);
  const y2 = group.lastY2 - LANE_TOP - 5;
  const trunkX = group.trunk * 10;
  return `M ${group.mergeX * 10} ${y1} L ${trunkX} ${y1} L ${trunkX} ${y2}`;
}

function markerTitle(marker: BadCaseMarker): string {
  return [
    `BC${marker.index + 1} ${marker.title}`,
    `触发点 L${marker.line}`,
    marker.gapNote ?? "",
    marker.selected ? "当前选中" : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * Center the viewport on one bad-case marker.
 *
 * @param badCaseId Selected bad case identifier.
 * @returns Nothing.
 */
function locateBadCase(badCaseId: string) {
  const marker = props.model.caseMarkers.find(
    (candidate) => candidate.badCaseId === badCaseId,
  );
  if (!marker) {
    return;
  }
  const { width, height } = viewportSize();
  if (!width || !height) {
    return;
  }
  const contentX = (marker.x / 100) * props.model.width;
  const contentY = LANE_TOP + LANE_MAIN_BAR_TOP;
  view.value = centerOn(view.value, contentX, contentY, width, height, 0.6);
  userAdjusted.value = true;
}

/**
 * Center the viewport on one lane row.
 *
 * @param agentId Agent identifier of the target lane.
 * @returns Nothing.
 */
function locateLane(agentId: string) {
  const lane = props.model.lanes.find((candidate) => candidate.id === agentId);
  if (!lane) {
    return;
  }
  const { width, height } = viewportSize();
  if (!width || !height) {
    return;
  }
  view.value = centerOn(
    view.value,
    (lane.start / 100) * props.model.width,
    lane.top + laneBarTop(lane) + LANE_BAR_H / 2,
    width,
    height,
    0.6,
  );
  userAdjusted.value = true;
}

function selectMarker(marker: BadCaseMarker) {
  emit("select-case", marker.badCaseId);
  emit("locate", marker.badCaseId);
  locateBadCase(marker.badCaseId);
}

function onResize() {
  if (!userAdjusted.value) {
    scheduleFit(0);
  }
}

watch(
  () => [props.model.width, props.model.height, props.model.lanes.length],
  () => {
    scheduleFit();
  },
  { flush: "post" },
);

onMounted(() => {
  if (typeof ResizeObserver !== "undefined" && viewportEl.value) {
    resizeObserver = new ResizeObserver(onResize);
    resizeObserver.observe(viewportEl.value);
  }
  void nextTick().then(() => scheduleFit(0));
});

onBeforeUnmount(() => {
  if (fitTimer !== undefined) {
    clearTimeout(fitTimer);
  }
  resizeObserver?.disconnect();
});

defineExpose({ fit, reset, zoomIn: () => zoomBy(1.2), zoomOut: () => zoomBy(0.83), locateBadCase, locateLane });
</script>

<template>
  <section
    class="ld-view"
    :style="{ height }"
    data-testid="lane-dag"
    aria-label="执行序 lane DAG"
  >
    <div class="ld-toolbar">
      <span class="ld-badge">执行序 DAG</span>
      <span
        v-if="selectedMarker"
        class="ld-hit"
        data-testid="lane-selected-case"
      >高亮 BC · {{ selectedMarker.title }} · L{{ selectedMarker.line }}</span>
      <div
        class="ld-legend"
        aria-label="执行流图例"
      >
        <span><i class="swatch swatch-main" />main</span>
        <span><i class="swatch swatch-sub" />subagent</span>
        <span><i class="swatch swatch-sub2" />nested</span>
        <span><i class="swatch swatch-skill" />skill</span>
        <span><i class="swatch swatch-gap" />×N 无触发</span>
        <span><i class="swatch swatch-band" />并发分支带</span>
        <span><i class="swatch swatch-case" />BC 触发</span>
        <span><i class="legend-line" />spawn</span>
      </div>
    </div>

    <div
      v-if="model.lanes.length"
      ref="viewportEl"
      :class="['ld-viewport', { 'is-panning': panning }]"
      data-testid="lane-viewport"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dblclick="fit"
      @wheel.prevent="onWheel"
    >
      <div
        class="ld-canvas"
        :style="{
          width: `${model.width}px`,
          height: `${model.height}px`,
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
        }"
      >
        <div
          class="ld-board"
          :style="{ height: `${model.height}px` }"
        >
          <div
            class="ld-axis"
            aria-hidden="true"
          >
            <span style="left: 0%">0</span>
            <span style="left: 25%">25</span>
            <span style="left: 50%">50</span>
            <span style="left: 75%">75</span>
            <span style="left: 100%">100</span>
          </div>
          <div
            class="ld-grid"
            aria-hidden="true"
          >
            <i style="left: 0%" />
            <i style="left: 25%" />
            <i style="left: 50%" />
            <i style="left: 75%" />
            <i style="left: 100%" />
          </div>

          <div
            class="ld-cases"
            aria-label="bad case 触发点"
          >
            <template
              v-for="marker in model.caseMarkers"
              :key="`case-${marker.badCaseId}`"
            >
              <button
                type="button"
                :class="['ld-case', { 'is-selected': marker.badCaseId === selectedCaseId }]"
                :style="{ left: `${marker.x}%`, top: `${marker.row * 16}px` }"
                :title="markerTitle(marker)"
                :aria-pressed="marker.badCaseId === selectedCaseId"
                :data-bad-case-id="marker.badCaseId"
                @click="selectMarker(marker)"
              >
                BC{{ marker.index + 1 }}
              </button>
              <i
                :class="['ld-case-lead', { 'is-selected': marker.badCaseId === selectedCaseId }]"
                :style="{
                  left: `${marker.x}%`,
                  top: `${marker.leadTop}px`,
                  height: `${marker.leadH}px`,
                }"
                aria-hidden="true"
              />
            </template>
          </div>

          <svg
            class="ld-edges"
            :viewBox="`0 0 1000 ${Math.max(1, model.height - LANE_TOP)}`"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <defs>
              <marker
                id="ld-spawn"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path
                  d="M0 0 L8 4 L0 8 z"
                  class="ld-spawn-arrow"
                />
              </marker>
            </defs>
            <g
              v-for="group in model.spawnGroups"
              :key="`spawn-${group.key}`"
            >
              <path
                v-if="!group.adjacentOnly"
                class="ld-edge-trunk"
                :d="trunkPath(group)"
              />
              <path
                v-for="(member, index) in group.members"
                :key="`spawn-edge-${member.laneId}-${index}`"
                class="ld-edge"
                :d="spawnPath(group, member.laneId)"
                marker-end="url(#ld-spawn)"
              />
            </g>
            <circle
              v-for="group in model.spawnGroups"
              :key="`spawn-anchor-${group.key}`"
              class="ld-spawn-anchor"
              :cx="group.mergeX * 10"
              :cy="spawnY(group)"
              :r="group.members.length > 1 ? 3.2 : 2.6"
            />
          </svg>

          <div
            class="ld-spawnmarks"
            aria-hidden="true"
          >
            <span
              v-for="group in model.spawnGroups.filter((item) => item.members.length > 1)"
              :key="`spawn-chip-${group.key}`"
              class="ld-spawn-chip"
              :style="{
                left: `${group.mergeX}%`,
                top: `${group.parentTop + group.parentBarTop + LANE_BAR_H + 2}px`,
              }"
            >spawn ×{{ group.members.length }}</span>
          </div>

          <div
            v-for="lane in model.lanes"
            :key="`lane-${lane.id}`"
            class="ld-lane"
            :style="{ top: `${laneLabelTop(lane)}px` }"
            :data-lane-path="lane.path"
          >
            <div :class="['ld-label', lane.depth ? `ld-indent-${Math.min(2, lane.depth)}` : '']">
              <span
                v-if="lane.depth"
                class="ld-tree"
              >└─</span>
              <span :class="['ld-dot', lane.depth === 0 ? 'is-main' : lane.depth === 1 ? 'is-sub' : 'is-sub2']" />
              <span class="ld-idx">{{ lane.path }}</span>
              <span
                class="ld-name"
                :title="lane.full"
              >{{ lane.label }}</span>
              <span
                v-if="lane.depth === 0"
                class="ld-rail-note"
              >触发标签</span>
              <span class="ld-depth">d{{ lane.depth }}</span>
            </div>
            <div :class="['ld-track', lane.depth === 0 ? 'ld-track-main' : '']">
              <div
                v-if="lane.depth === 0"
                class="ld-rail"
                aria-hidden="true"
              >
                <template
                  v-for="label in lane.railLabels"
                  :key="`rail-${label.id}`"
                >
                  <div
                    :class="['ld-rail-chip', label.kind]"
                    :style="{ left: `${label.left}%`, top: `${label.row * 13}px` }"
                    :title="label.title"
                  >
                    {{ label.text }}
                  </div>
                  <i
                    class="ld-rail-lead"
                    :style="{
                      left: `${label.x}%`,
                      top: `${label.row * 13 + 11}px`,
                      height: `${Math.max(2, LANE_MAIN_BAR_TOP - 2 - (label.row * 13 + 11))}px`,
                    }"
                  />
                </template>
              </div>
              <div class="ld-bars">
                <div
                  v-for="bar in lane.bars"
                  :key="`bar-${lane.id}-${bar.id}`"
                  :class="[
                    'ld-bar',
                    `is-${bar.kind}`,
                    {
                      'is-event': lane.depth === 0 && bar.rail,
                      'is-tight': bar.kind === 'gap' && bar.end - bar.start < 2,
                      'is-case-src': lane.depth === 0 && !bar.kind.includes('gap') && bar.id === selectedBarId,
                    },
                  ]"
                  :style="{
                    left: `${bar.start}%`,
                    width: `${Math.max(0, bar.end - bar.start)}%`,
                    top: `${laneBarTop(lane)}px`,
                  }"
                  :title="barTitle(bar)"
                >
                  <span
                    v-if="!(lane.depth === 0 && bar.rail) && !(bar.kind === 'gap' && bar.end - bar.start < 1.2)"
                    class="lb"
                  >{{ bar.label }}</span>
                </div>
                <span
                  v-for="bar in lane.bars.filter((item) => item.cont)"
                  :key="`cont-${lane.id}-${bar.id}`"
                  class="ld-cont-mark"
                  :style="{
                    left: `${Math.min(99.4, bar.end)}%`,
                    top: `${laneBarTop(lane) + 4}px`,
                  }"
                  :title="bar.contReason || '区间延续'"
                >›</span>
              </div>
            </div>
          </div>

          <div
            v-for="(band, index) in model.concurrencyBands"
            :key="`band-${index}`"
            class="ld-bands"
            aria-hidden="true"
          >
            <div
              class="ld-band"
              :style="{
                left: `${band.left}%`,
                width: `${band.right - band.left}%`,
                top: `${band.top}px`,
                height: `${band.bottom - band.top}px`,
              }"
              :title="`并发分支 / 嵌套 subagent · ${band.left.toFixed(1)}–${band.right.toFixed(1)}%（子 lane min start – max end，不是从 0% 开始）`"
            />
          </div>

          <div
            class="ld-ticks"
            aria-hidden="true"
          >
            <i
              v-for="marker in model.caseMarkers"
              :key="`tick-${marker.badCaseId}`"
              :class="['ld-case-tick', { 'is-selected': marker.badCaseId === selectedCaseId }]"
              :style="{
                left: `${marker.x}%`,
                top: `${LANE_TOP + LANE_MAIN_BAR_TOP - 2 - (marker.badCaseId === selectedCaseId ? 1 : 0)}px`,
              }"
            />
          </div>
        </div>
      </div>

      <div
        class="ld-zoom"
        role="group"
        aria-label="执行序 DAG 缩放与平移"
        @pointerdown.stop
      >
        <button
          type="button"
          aria-label="放大"
          title="放大"
          @click="zoomBy(1.2)"
        >
          ＋
        </button>
        <button
          type="button"
          aria-label="缩小"
          title="缩小"
          @click="zoomBy(0.83)"
        >
          －
        </button>
        <button
          type="button"
          class="wide"
          aria-label="适应窗口"
          title="适应窗口"
          @click="fit"
        >
          适应
        </button>
        <button
          type="button"
          class="wide"
          aria-label="恢复 1:1"
          title="恢复 1:1"
          @click="reset"
        >
          1:1
        </button>
      </div>
    </div>
    <div
      v-else
      class="ld-empty"
      role="status"
    >
      执行流数据不完整，暂时无法绘制。
    </div>
    <div class="ld-foot">
      <b>逻辑序（无时间戳）：</b>bar 长度 = 日志行区间（main 按行位置；sub 按同 session 行数线性缩放），不是真实耗时；
      同一 lane 内 bar 不重叠，跨 lane 重叠表示并发；橙色带 = 子 agent 区间 min(start)–max(end)。
      所有 lane 均已展开，不再按数量折叠；滚轮缩放、拖拽平移，右下角可「适应」或「1:1」。
    </div>
  </section>
</template>

<style scoped>
.ld-view {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-panel);
}

.ld-toolbar {
  display: flex;
  flex-wrap: wrap;
  flex-shrink: 0;
  gap: 9px;
  align-items: center;
  padding: 7px 12px 5px;
  border-bottom: 1px solid var(--border);
}

.ld-badge {
  padding: 2px 8px;
  border: 1px solid color-mix(in srgb, var(--purple) 35%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--purple) 9%, var(--bg-card));
  color: var(--purple);
  font-size: 9.5px;
  font-weight: 750;
  letter-spacing: 0.04em;
}

.ld-sub {
  color: var(--text-faint);
  font-size: 10px;
}

.ld-hit {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 8px;
  border: 1px solid color-mix(in srgb, var(--red) 45%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
  color: color-mix(in srgb, var(--red) 75%, var(--text));
  font-size: 9.5px;
  font-weight: 750;
}

.ld-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  align-items: center;
  margin-left: auto;
  color: var(--text-faint);
  font-size: 9.5px;
}

.ld-legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.swatch {
  display: inline-block;
  width: 15px;
  height: 8px;
  border-radius: 2px;
}

.swatch-main {
  background: linear-gradient(135deg, var(--blue), color-mix(in srgb, var(--blue) 55%, var(--bg-card)));
}

.swatch-sub {
  background: linear-gradient(135deg, var(--purple), color-mix(in srgb, var(--purple) 55%, var(--bg-card)));
}

.swatch-sub2 {
  background: linear-gradient(135deg, var(--orange), color-mix(in srgb, var(--orange) 55%, var(--bg-card)));
}

.swatch-skill {
  background: linear-gradient(135deg, var(--green), color-mix(in srgb, var(--green) 55%, var(--bg-card)));
}

.swatch-gap {
  border: 1px dashed var(--border-strong);
  background: var(--bg-inset);
}

.swatch-band {
  border-right: 2px dashed var(--orange);
  border-left: 2px dashed var(--orange);
  background: color-mix(in srgb, var(--orange) 12%, var(--bg-card));
}

.swatch-case {
  border: 1px solid var(--red);
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
}

.legend-line {
  display: inline-block;
  width: 15px;
  border-top: 2px dashed var(--purple);
}

.ld-viewport {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-panel);
  cursor: grab;
  touch-action: none;
}

.ld-viewport.is-panning {
  cursor: grabbing;
}

.ld-canvas {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}

.ld-board {
  position: relative;
  min-width: 100%;
}

.ld-axis {
  position: absolute;
  top: 0;
  right: 0;
  left: 218px;
  height: 18px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 8.5px;
}

.ld-axis span {
  position: absolute;
  transform: translateX(-50%);
}

.ld-axis span:first-child {
  transform: none;
}

.ld-axis span:last-child {
  transform: translateX(-100%);
}

.ld-grid {
  position: absolute;
  top: 18px;
  right: 0;
  bottom: 0;
  left: 218px;
  pointer-events: none;
}

.ld-grid i {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px dashed var(--border);
}

.ld-cases {
  position: absolute;
  top: 18px;
  right: 0;
  left: 218px;
  height: 28px;
  pointer-events: none;
}

.ld-case {
  position: absolute;
  top: 0;
  z-index: 5;
  padding: 0 4px;
  border: 1px solid var(--red);
  border-radius: 999px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  color: color-mix(in srgb, var(--red) 80%, var(--text));
  font-size: 7.5px;
  font-weight: 800;
  line-height: 11px;
  white-space: nowrap;
  cursor: pointer;
  pointer-events: auto;
  transform: translateX(-50%);
}

.ld-case.is-selected {
  border-color: var(--red);
  background: var(--red);
  color: var(--bg-card);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--red) 20%, transparent);
}

.ld-case::after {
  position: absolute;
  top: 100%;
  left: 50%;
  width: 1px;
  height: 2px;
  background: var(--red);
  content: "";
}

.ld-case-lead {
  position: absolute;
  z-index: 4;
  width: 1px;
  background: color-mix(in srgb, var(--red) 55%, transparent);
}

.ld-case-lead.is-selected {
  width: 2px;
  background: var(--red);
}

.ld-edges {
  position: absolute;
  top: 46px;
  right: 0;
  bottom: 0;
  left: 218px;
  z-index: 1;
  width: calc(100% - 218px);
  height: calc(100% - 46px);
  overflow: visible;
  pointer-events: none;
}

.ld-edge {
  fill: none;
  stroke: var(--purple);
  stroke-dasharray: 5 4;
  stroke-width: 1.4;
}

.ld-edge-trunk {
  fill: none;
  stroke: var(--purple);
  stroke-dasharray: 4 3;
  stroke-width: 1.3;
  opacity: 0.8;
}

.ld-spawn-arrow {
  fill: var(--purple);
}

.ld-spawn-anchor {
  fill: var(--purple);
  stroke: var(--bg-card);
  stroke-width: 1;
}

.ld-spawnmarks {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 218px;
  z-index: 5;
  pointer-events: none;
}

.ld-spawn-chip {
  position: absolute;
  height: 12px;
  padding: 0 5px;
  border: 1px dashed var(--purple);
  border-radius: 999px;
  background: color-mix(in srgb, var(--purple) 9%, var(--bg-card));
  color: var(--purple);
  font-size: 8px;
  font-weight: 800;
  line-height: 12px;
  white-space: nowrap;
  transform: translateX(3px);
}

.ld-lane {
  position: absolute;
  right: 0;
  left: 0;
  display: grid;
  grid-template-columns: 210px 1fr;
  gap: 8px;
  align-items: center;
}

.ld-label {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
  color: var(--text-dim);
  font-size: 10.5px;
}

.ld-indent-1 {
  padding-left: 14px;
}

.ld-indent-2 {
  padding-left: 30px;
}

.ld-tree {
  flex-shrink: 0;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}

.ld-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-faint);
}

.ld-dot.is-main {
  background: var(--blue);
}

.ld-dot.is-sub {
  background: var(--purple);
}

.ld-dot.is-sub2 {
  background: var(--orange);
}

.ld-idx {
  flex-shrink: 0;
  padding: 0 4px;
  border: 1px solid color-mix(in srgb, var(--purple) 30%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--purple) 9%, var(--bg-card));
  color: var(--purple);
  font-family: var(--mono);
  font-size: 8.5px;
  font-weight: 750;
}

.ld-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ld-rail-note {
  flex-shrink: 0;
  color: var(--text-faint);
  font-size: 8px;
  font-weight: 750;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.ld-depth {
  flex-shrink: 0;
  margin-left: auto;
  padding: 0 4px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-inset);
  color: var(--text-faint);
  font-size: 8px;
  font-weight: 750;
}

.ld-track {
  position: relative;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--blue) 3%, var(--bg-card)),
    color-mix(in srgb, var(--blue) 6%, var(--bg-card))
  );
}

.ld-track-main {
  height: 56px;
}

.ld-rail {
  position: absolute;
  top: 2px;
  right: 0;
  left: 0;
  z-index: 7;
  height: 30px;
  pointer-events: none;
}

.ld-rail-chip {
  position: absolute;
  height: 11px;
  padding: 0 4px;
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  background: var(--bg-card);
  box-shadow: 0 1px 2px color-mix(in srgb, var(--text) 10%, transparent);
  color: var(--text-dim);
  font-size: 8.5px;
  font-weight: 750;
  line-height: 11px;
  white-space: nowrap;
  pointer-events: auto;
}

.ld-rail-chip.is-main {
  border-color: color-mix(in srgb, var(--blue) 30%, transparent);
  background: color-mix(in srgb, var(--blue) 6%, var(--bg-card));
  color: var(--blue);
}

.ld-rail-chip.is-skill {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  background: color-mix(in srgb, var(--green) 6%, var(--bg-card));
  color: var(--green);
}

.ld-rail-lead {
  position: absolute;
  z-index: 6;
  width: 1px;
  background: color-mix(in srgb, var(--text) 45%, transparent);
}

.ld-bars {
  position: absolute;
  top: 0;
  right: 2px;
  bottom: 0;
  left: 2px;
}

.ld-bar {
  position: absolute;
  top: 4px;
  z-index: 2;
  display: flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  overflow: hidden;
  border-radius: 6px;
  background: linear-gradient(135deg, var(--blue), color-mix(in srgb, var(--blue) 55%, var(--bg-card)));
  box-shadow: 0 3px 8px color-mix(in srgb, var(--text) 12%, transparent);
  color: var(--bg-card);
  font-size: 9px;
  font-weight: 750;
  white-space: nowrap;
}

.ld-bar > .lb {
  position: relative;
  z-index: 1;
  display: block;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ld-bar.is-sub {
  background: linear-gradient(135deg, var(--purple), color-mix(in srgb, var(--purple) 55%, var(--bg-card)));
}

.ld-bar.is-sub2 {
  background: linear-gradient(135deg, var(--orange), color-mix(in srgb, var(--orange) 55%, var(--bg-card)));
}

.ld-bar.is-skill {
  background: linear-gradient(135deg, var(--green), color-mix(in srgb, var(--green) 55%, var(--bg-card)));
}

.ld-bar.is-gap {
  border: 1px dashed var(--border-strong);
  background: color-mix(in srgb, var(--text-faint) 12%, var(--bg-card));
  box-shadow: none;
  color: var(--text-dim);
  font-size: 8px;
  font-weight: 700;
}

.ld-bar.is-gap.is-tight {
  padding: 0;
}

.ld-bar.is-event {
  padding: 0;
}

.ld-bar.is-unknown {
  border: 1px dashed var(--purple);
  background: repeating-linear-gradient(
    135deg,
    color-mix(in srgb, var(--purple) 8%, var(--bg-card)) 0 6px,
    color-mix(in srgb, var(--purple) 3%, var(--bg-card)) 6px 12px
  );
  box-shadow: none;
  color: var(--purple);
}

.ld-bar.is-case-src {
  outline: 2px solid var(--red);
  outline-offset: 1px;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--red) 14%, transparent);
}

.ld-cont-mark {
  position: absolute;
  top: 4px;
  z-index: 4;
  width: 12px;
  height: 12px;
  border: 1px solid var(--purple);
  border-radius: 50%;
  background: var(--bg-card);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--text) 18%, transparent);
  color: var(--purple);
  font-size: 10px;
  font-weight: 900;
  line-height: 10px;
  text-align: center;
  transform: translateX(-50%);
}

.ld-bands {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 218px;
  z-index: 1;
  pointer-events: none;
}

.ld-band {
  position: absolute;
  border: 1px dashed var(--orange);
  border-right: 2px dashed var(--orange);
  border-left: 2px dashed var(--orange);
  border-radius: 5px;
  background: color-mix(in srgb, var(--orange) 8%, transparent);
}

.ld-ticks {
  position: absolute;
  top: 0;
  right: 0;
  left: 218px;
  height: 100%;
  pointer-events: none;
}

.ld-case-tick {
  position: absolute;
  width: 1px;
  height: 3px;
  background: var(--red);
}

.ld-case-tick.is-selected {
  width: 2px;
  height: 4px;
}

.ld-zoom {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 9;
  display: flex;
  gap: 4px;
  align-items: center;
}

.ld-zoom button {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: color-mix(in srgb, var(--bg-card) 94%, transparent);
  box-shadow: 0 2px 6px color-mix(in srgb, var(--text) 8%, transparent);
  color: var(--text-dim);
  font: 700 12px/1 inherit;
  cursor: pointer;
}

.ld-zoom button:hover {
  border-color: color-mix(in srgb, var(--blue) 40%, var(--border-strong));
  color: var(--blue);
}

.ld-zoom button.wide {
  width: auto;
  padding: 0 7px;
  font-size: 9.5px;
}

.ld-empty {
  display: grid;
  flex: 1;
  place-items: center;
  padding: 24px;
  color: var(--text-faint);
  font-size: 12px;
  text-align: center;
}

.ld-foot {
  flex-shrink: 0;
  padding: 5px 12px 7px;
  border-top: 1px dashed var(--border);
  color: var(--text-faint);
  font-size: 9px;
}

.ld-foot b {
  color: var(--text-dim);
}
</style>
