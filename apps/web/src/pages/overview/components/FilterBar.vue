<script setup lang="ts">
import type { OverviewGrain, OverviewRange, OverviewWindow } from "@harness/contracts";
import { computed, ref } from "vue";

import type { OverviewRangeChoice, OverviewUrlState } from "../overviewUrl";
import SourceMultiSelect from "./SourceMultiSelect.vue";

const props = defineProps({
  state: {
    type: Object as () => OverviewUrlState,
    required: true,
  },
  options: {
    type: Array as () => string[],
    default: () => [],
  },
  window: {
    type: Object as () => OverviewWindow | null,
    default: null,
  },
  grainEffective: {
    type: String as () => OverviewGrain | null,
    default: null,
  },
  objectsLoading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{
  "update:range": [value: OverviewRangeChoice];
  "update:window": [value: { from: string; to: string }];
  "update:grain": [value: OverviewGrain];
  "update:objects": [value: string[]];
  clear: [];
}>();

const sourceSelect = ref<InstanceType<typeof SourceMultiSelect> | null>(null);

const ranges: Array<{ value: OverviewRange; label: string }> = [
  { value: 7, label: "近 7 天" },
  { value: 30, label: "近 30 天" },
  { value: 90, label: "近 90 天" },
];

const grains: Array<{ value: OverviewGrain; label: string }> = [
  { value: "day", label: "日" },
  { value: "week", label: "周" },
  { value: "month", label: "月" },
];

const grainLabels: Record<OverviewGrain, string> = {
  day: "日",
  week: "周",
  month: "月",
};

const windowLabel = computed(() =>
  props.window ? `${props.window.from} ~ ${props.window.to}` : "",
);
const downgradedGrain = computed(() =>
  props.grainEffective && props.grainEffective !== props.state.grain
    ? props.grainEffective
    : null,
);

function removeObject(name: string): void {
  emit(
    "update:objects",
    props.state.objects.filter((item) => item !== name),
  );
}

function customChanged(field: "from" | "to", event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  const next = {
    from: field === "from" ? value : props.state.from,
    to: field === "to" ? value : props.state.to,
  };
  if (next.from && next.to && next.from <= next.to) {
    emit("update:window", next);
  }
}

/**
 * Focus the source multiselect from a stat-strip shortcut.
 * @returns No value.
 */
function focusSources(): void {
  sourceSelect.value?.focus();
}

defineExpose({ focusSources });
</script>

<template>
  <div
    class="ov-filterbar"
    data-testid="ov-filterbar"
  >
    <div class="group">
      <span class="label">时间</span>
      <div
        class="seg"
        role="group"
        aria-label="时间范围"
      >
        <button
          v-for="range in ranges"
          :key="range.value"
          :class="{ active: state.range === range.value }"
          :data-testid="`ov-range-${range.value}`"
          type="button"
          @click="emit('update:range', range.value)"
        >
          {{ range.label }}
        </button>
        <button
          :class="{ active: state.range === 'custom' }"
          data-testid="ov-range-custom"
          type="button"
          @click="emit('update:range', 'custom')"
        >
          自定义
        </button>
      </div>
      <div
        v-if="state.range === 'custom'"
        class="custom-range"
      >
        <input
          class="inp"
          data-testid="ov-from"
          type="date"
          :value="state.from"
          aria-label="开始日期"
          @change="customChanged('from', $event)"
        >
        <span class="label">~</span>
        <input
          class="inp"
          data-testid="ov-to"
          type="date"
          :value="state.to"
          aria-label="结束日期"
          @change="customChanged('to', $event)"
        >
      </div>
      <span
        v-else-if="windowLabel"
        class="range"
        data-testid="ov-window-label"
      >{{ windowLabel }}</span>
    </div>

    <span class="sep" />

    <div class="group">
      <span class="label">粒度</span>
      <div
        class="seg"
        role="group"
        aria-label="趋势粒度"
      >
        <button
          v-for="grain in grains"
          :key="grain.value"
          :class="{ active: state.grain === grain.value }"
          :data-testid="`ov-grain-${grain.value}`"
          type="button"
          @click="emit('update:grain', grain.value)"
        >
          {{ grain.label }}
        </button>
      </div>
      <span
        v-if="downgradedGrain"
        class="downgraded"
        data-testid="ov-grain-downgraded"
      >已按{{ grainLabels[downgradedGrain] }}展示</span>
    </div>

    <span class="sep" />

    <div class="group">
      <span class="label">bad case 上报来源</span>
      <SourceMultiSelect
        ref="sourceSelect"
        :options="options"
        :selected="state.objects"
        @update:selected="emit('update:objects', $event)"
      />
      <span
        v-if="objectsLoading"
        class="loading-note"
        data-testid="ov-sources-loading"
      >来源加载中…</span>
    </div>

    <template v-if="state.objects.length > 0">
      <span class="spacer" />
      <div
        class="selected"
        data-testid="ov-object-chips"
      >
        <span
          v-for="name in state.objects"
          :key="name"
          class="chip"
          :data-testid="`ov-chip-${name}`"
        >
          {{ name }}
          <button
            type="button"
            :title="`移除 ${name}`"
            :aria-label="`移除 ${name}`"
            @click="removeObject(name)"
          >
            ×
          </button>
        </span>
      </div>
    </template>

    <span class="spacer" />
    <button
      class="clear"
      data-testid="ov-clear"
      type="button"
      @click="emit('clear')"
    >
      清除筛选
    </button>
  </div>
</template>

<style scoped>
.ov-filterbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-bottom: 12px;
  padding: 9px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  min-height: 28px;
}

.label {
  color: var(--text-faint);
  font-size: 10.5px;
  white-space: nowrap;
}

.seg {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
}

.seg button {
  padding: 4px 10px;
  border: 0;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 11.5px;
  cursor: pointer;
}

.seg button:first-child {
  border-left: 0;
}

.seg button.active {
  background: var(--bg-card);
  color: var(--text);
  font-weight: 600;
}

.seg button:hover {
  color: var(--text);
}

.range {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10.5px;
  white-space: nowrap;
}

.custom-range {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.inp {
  height: 26px;
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text);
  font-size: 11px;
}

.sep {
  width: 1px;
  height: 17px;
  background: var(--border);
}

.downgraded {
  padding: 1px 7px;
  border: 1px solid color-mix(in srgb, var(--orange) 34%, var(--border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--orange) 8%, var(--bg-card));
  color: var(--orange);
  font-size: 10px;
  white-space: nowrap;
}

.loading-note {
  color: var(--text-faint);
  font-size: 10px;
}

.spacer {
  flex: 1;
  min-width: 4px;
}

.selected {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
}

.chip button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}

.chip button:hover {
  color: var(--red);
}

.clear {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

.clear:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

@media (max-width: 640px) {
  .ov-filterbar {
    padding: 8px 10px;
  }

  .sep {
    display: none;
  }
}
</style>
