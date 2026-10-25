<script setup lang="ts">
import type { SessionSort } from "../../../api/sessions";

defineProps({
  modelValue: {
    type: String,
    default: "latest",
  },
});

const emit = defineEmits<{
  "update:modelValue": [value: SessionSort];
}>();

const options: Array<{ value: SessionSort; label: string }> = [
  { value: "latest", label: "最新" },
  { value: "userTurns", label: "用户轮次" },
  { value: "messages", label: "消息数" },
  { value: "agents", label: "子 Agent 数" },
];
</script>

<template>
  <select
    data-testid="session-sort"
    class="sort-select"
    aria-label="Session 排序"
    :value="modelValue"
    @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value as SessionSort)"
  >
    <option
      v-for="option in options"
      :key="option.value"
      :value="option.value"
    >
      {{ option.label }}
    </option>
  </select>
</template>

<style scoped>
.sort-select {
  padding: 3px 24px 3px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font: inherit;
  font-size: 11.5px;
}
</style>
