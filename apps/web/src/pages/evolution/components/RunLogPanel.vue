<script setup lang="ts">
import type {
  EvolutionRunEventLevel,
  EvolutionRunStep,
  EvolutionStepKey,
} from "@harness/contracts";
import { computed, nextTick, ref, watch } from "vue";

import EmptyState from "../../../components/ui/EmptyState.vue";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { useEvolutionRunEventLog } from "../../../composables/useEvolutionRunEventLog";
import EventList from "./EventList.vue";

const props = defineProps<{
  runId: string;
  steps: EvolutionRunStep[];
}>();

const emit = defineEmits<{
  "select-step": [key: EvolutionStepKey];
  "focus-cluster": [clusterId: string];
}>();

type FilterValue = EvolutionRunEventLevel | undefined;

const filter = ref<FilterValue>();
const autoScroll = ref(true);
const scroller = ref<HTMLElement | null>(null);
const visible = ref(true);
const {
  items,
  hasMore,
  isPending,
  error,
  appendError,
  refresh,
  loadMore,
} = useEvolutionRunEventLog(
  computed(() => props.runId),
  computed(() => filter.value),
  visible,
);

const filterOptions: Array<{ label: string; value: FilterValue }> = [
  { label: "全部", value: undefined },
  { label: "错误", value: "error" },
  { label: "警告", value: "warn" },
];

const isEmpty = computed(
  () => !isPending.value && !error.value && items.value.length === 0,
);

function chooseFilter(value: FilterValue): void {
  filter.value = value;
}

function onScroll(): void {
  const element = scroller.value;
  if (!element || !autoScroll.value) return;
  const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
  if (distance > 32) autoScroll.value = false;
}

watch(
  () => items.value.length,
  async (next, previous) => {
    if (!autoScroll.value || next <= previous) return;
    await nextTick();
    const element = scroller.value;
    if (element) element.scrollTop = element.scrollHeight;
  },
);

async function refreshLog(): Promise<void> {
  autoScroll.value = true;
  await refresh();
}
</script>

<template>
  <section
    class="card panel log-panel"
    data-testid="run-log-panel"
  >
    <header class="log-toolbar">
      <div
        class="filters"
        role="group"
        aria-label="日志级别过滤"
      >
        <button
          v-for="option in filterOptions"
          :key="option.label"
          type="button"
          :class="{ active: filter === option.value }"
          :aria-pressed="filter === option.value"
          @click="chooseFilter(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
      <label class="toggle">
        <input
          v-model="autoScroll"
          type="checkbox"
        >
        自动滚动
      </label>
      <button
        type="button"
        class="refresh"
        :disabled="isPending"
        @click="refreshLog"
      >
        刷新
      </button>
      <span class="spacer" />
      <span class="count mono">{{ items.length }} 条</span>
    </header>

    <div
      ref="scroller"
      class="event-scroll"
      data-testid="event-scroll"
      @scroll.passive="onScroll"
    >
      <LoadingSkeleton
        v-if="isPending && items.length === 0"
        label="正在读取执行日志"
        :rows="3"
      />
      <ErrorState
        v-else-if="error && items.length === 0"
        code="EVOLUTION_RUN_EVENTS_UNAVAILABLE"
        message="执行日志读取失败，请重试"
        @retry="refreshLog"
      />
      <EmptyState
        v-else-if="isEmpty"
        title="还没有执行日志"
        description="运行产生阶段变化或异常后，事件会持久出现在这里。"
      />
      <EventList
        v-else
        :events="items"
        :steps="steps"
        @select-step="emit('select-step', $event)"
        @focus-cluster="emit('focus-cluster', $event)"
      />
    </div>

    <footer class="log-footer">
      <div
        v-if="appendError"
        class="append-error"
        data-testid="append-error"
      >
        <span>后续日志加载失败</span>
        <button
          type="button"
          data-testid="retry-load-more"
          :disabled="isPending"
          @click="loadMore"
        >
          重试
        </button>
      </div>
      <div
        v-else-if="error && items.length"
        class="append-error"
      >
        <span>日志刷新失败，已保留现有记录</span>
        <button
          type="button"
          :disabled="isPending"
          @click="refreshLog"
        >
          重试
        </button>
      </div>
      <button
        v-if="hasMore"
        type="button"
        :disabled="isPending"
        data-testid="load-more-events"
        @click="loadMore"
      >
        {{ isPending ? "加载中…" : "加载更多" }}
      </button>
      <span
        v-else-if="items.length"
        class="end-copy"
      >已加载全部记录</span>
      <span
        v-if="!autoScroll"
        class="paused-copy"
      >你已上滚，自动滚动已暂停</span>
    </footer>
  </section>
</template>

<style scoped>
.card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.panel {
  padding: 14px;
}

.log-toolbar,
.log-footer {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.log-toolbar {
  margin-bottom: 10px;
}

.filters {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 7px;
}

.filters button,
.refresh,
.log-footer button {
  padding: 5px 10px;
  border: 0;
  background: var(--bg-inset);
  color: var(--text-dim);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.filters button + button {
  border-left: 1px solid var(--border);
}

.filters button.active {
  background: color-mix(in srgb, var(--blue) 12%, var(--bg-card));
  color: var(--blue);
}

.toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-dim);
  font-size: 11px;
}

.refresh {
  border: 1px solid var(--border);
  border-radius: 6px;
}

.refresh:disabled,
.log-footer button:disabled {
  cursor: wait;
  opacity: 0.6;
}

.spacer {
  flex: 1;
}

.count,
.end-copy,
.paused-copy {
  color: var(--text-faint);
  font-size: 10.5px;
}

.event-scroll {
  max-height: min(58vh, 640px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.log-footer {
  min-height: 30px;
  padding-top: 9px;
}

.log-footer button {
  border: 1px solid var(--border);
  border-radius: 6px;
}

.paused-copy {
  margin-left: auto;
  color: var(--orange);
}

.append-error {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  color: var(--red);
  font-size: 11px;
}

.append-error span {
  flex: 1;
}

@media (max-width: 720px) {
  .log-panel {
    padding: 11px;
  }

  .event-scroll {
    max-height: none;
  }
}
</style>
