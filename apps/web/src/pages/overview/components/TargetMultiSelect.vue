<script setup lang="ts">
import type { TargetObjectType } from "@harness/contracts";
import { computed, nextTick, ref } from "vue";

/** One selectable evolution target option. */
type TargetOption = {
  id: string;
  name: string;
  objectType: TargetObjectType;
};

const props = defineProps({
  options: {
    type: Array as () => TargetOption[],
    default: () => [],
  },
  selected: {
    type: Array as () => string[],
    default: () => [],
  },
});

const emit = defineEmits<{
  "update:selected": [value: string[]];
}>();

const root = ref<HTMLDetailsElement | null>(null);
const keyword = ref("");

const filtered = computed(() => {
  const search = keyword.value.trim().toLowerCase();
  if (!search) return props.options;
  return props.options.filter(
    (option) =>
      option.name.toLowerCase().includes(search) ||
      option.objectType.includes(search),
  );
});

const selectedSet = computed(() => new Set(props.selected));

function toggle(id: string): void {
  emit(
    "update:selected",
    selectedSet.value.has(id)
      ? props.selected.filter((item) => item !== id)
      : [...props.selected, id],
  );
}

function selectAll(): void {
  emit("update:selected", [
    ...new Set([...props.selected, ...props.options.map((option) => option.id)]),
  ]);
}

function clear(): void {
  emit("update:selected", []);
}

/**
 * Open the popover and focus its search box.
 * @returns No value.
 */
function focus(): void {
  if (root.value) {
    root.value.open = true;
  }
  void nextTick(() => {
    root.value?.querySelector<HTMLInputElement>("input[type='search']")?.focus();
  });
}

defineExpose({ focus });
</script>

<template>
  <details
    ref="root"
    class="ov-multi"
    data-testid="ov-target-select"
  >
    <summary>
      {{ selected.length > 0 ? `已选 ${selected.length} 个进化对象` : "全部进化对象" }}
      <span
        class="caret"
        aria-hidden="true"
      >⌄</span>
    </summary>
    <div class="ov-multi-menu">
      <input
        v-model="keyword"
        class="search"
        data-testid="ov-target-search"
        placeholder="搜索进化对象"
        type="search"
      >
      <div class="options">
        <label
          v-for="option in filtered"
          :key="option.id"
          class="option"
        >
          <input
            type="checkbox"
            :checked="selectedSet.has(option.id)"
            :data-target="option.id"
            :data-testid="`ov-target-option-${option.id}`"
            @change="toggle(option.id)"
          >
          <span class="kind">{{ option.objectType }}</span>
          <span>{{ option.name }}</span>
        </label>
        <p
          v-if="filtered.length === 0"
          class="no-options"
        >
          没有匹配的进化对象
        </p>
      </div>
      <div class="om-foot">
        <span>不选 = 全部对象</span>
        <span class="om-actions">
          <button
            data-testid="ov-target-select-all"
            type="button"
            @click="selectAll"
          >
            全选
          </button>
          <button
            data-testid="ov-target-select-clear"
            type="button"
            @click="clear"
          >
            清空
          </button>
        </span>
      </div>
    </div>
  </details>
</template>

<style scoped>
.ov-multi {
  position: relative;
}

summary {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 152px;
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11.5px;
  list-style: none;
  cursor: pointer;
}

summary::-webkit-details-marker {
  display: none;
}

summary:hover,
.ov-multi[open] summary {
  border-color: var(--blue);
  color: var(--text);
}

.caret {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 9px;
}

.ov-multi-menu {
  position: absolute;
  top: calc(100% + 5px);
  left: 0;
  z-index: 40;
  width: 258px;
  padding: 5px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  box-shadow: var(--shadow-popover);
}

.search {
  width: 100%;
  height: 26px;
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-inset);
  color: var(--text);
  font-size: 11px;
}

.options {
  display: grid;
  max-height: 220px;
  margin-top: 4px;
  overflow-y: auto;
}

.option {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 7px;
  border-radius: 5px;
  color: var(--text-dim);
  font-size: 11.5px;
  cursor: pointer;
}

.option:hover {
  background: var(--bg-panel);
}

.option input {
  accent-color: var(--blue);
}

.kind {
  padding: 0 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9px;
}

.no-options {
  margin: 6px 7px;
  color: var(--text-faint);
  font-size: 11px;
}

.om-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  padding: 5px 6px 1px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10.5px;
}

.om-actions {
  display: flex;
  gap: 8px;
}

.om-actions button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--blue);
  font: inherit;
  cursor: pointer;
}
</style>
