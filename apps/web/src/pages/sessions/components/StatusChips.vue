<script setup lang="ts">
import type { SessionStatusFilter } from "../../../api/sessions";

defineProps({
  modelValue: {
    type: String,
    default: "all",
  },
});

const emit = defineEmits<{
  "update:modelValue": [value: SessionStatusFilter];
}>();

const options: Array<{ value: SessionStatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "ok", label: "完成" },
  { value: "problem", label: "有失败" },
];
</script>

<template>
  <div
    class="status-chips"
    role="group"
    aria-label="Session 状态"
  >
    <button
      v-for="option in options"
      :key="option.value"
      class="chip"
      :class="{ active: modelValue === option.value }"
      type="button"
      :aria-pressed="modelValue === option.value"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.status-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
}

.chip.active {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 14%, transparent);
  color: var(--text);
}
</style>
