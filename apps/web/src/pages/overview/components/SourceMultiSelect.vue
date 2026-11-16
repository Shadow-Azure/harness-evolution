<script setup lang="ts">
import { computed, nextTick, ref } from "vue";

const props = defineProps({
  options: {
    type: Array as () => string[],
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
  return props.options.filter((name) => name.toLowerCase().includes(search));
});

const selectedSet = computed(() => new Set(props.selected));

function isSelected(name: string): boolean {
  return selectedSet.value.has(name);
}

function toggle(name: string): void {
  emit(
    "update:selected",
    isSelected(name)
      ? props.selected.filter((item) => item !== name)
      : [...props.selected, name],
  );
}

function selectAll(): void {
  emit("update:selected", [...new Set([...props.selected, ...props.options])]);
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
    data-testid="ov-source-select"
  >
    <summary>
      {{ selected.length > 0 ? `已选 ${selected.length} 个来源` : "全部来源" }}
      <span
        class="caret"
        aria-hidden="true"
      >⌄</span>
    </summary>
    <div class="ov-multi-menu">
      <input
        v-model="keyword"
        class="search"
        data-testid="ov-source-search"
        placeholder="搜索来源"
        type="search"
      >
      <div class="options">
        <label
          v-for="name in filtered"
          :key="name"
          class="option"
        >
          <input
            type="checkbox"
            :checked="isSelected(name)"
            :data-object="name"
            :data-testid="`ov-source-option-${name}`"
            @change="toggle(name)"
          >
          <span>{{ name }}</span>
        </label>
        <p
          v-if="filtered.length === 0"
          class="no-options"
        >
          没有匹配的来源
        </p>
      </div>
      <div class="om-foot">
        <span>不选 = 全部来源</span>
        <span class="om-actions">
          <button
            data-testid="ov-source-all"
            type="button"
            @click="selectAll"
          >
            全选
          </button>
          <button
            data-testid="ov-source-clear"
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
  min-width: 138px;
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
  width: 224px;
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
