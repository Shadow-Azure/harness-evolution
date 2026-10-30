<script setup lang="ts">
defineProps({
  modelValue: {
    type: String,
    default: "",
  },
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();
</script>

<template>
  <label class="search-box">
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
    >
      <circle
        cx="11"
        cy="11"
        r="6.5"
      />
      <path d="m16 16 4 4" />
    </svg>
    <input
      data-testid="search-input"
      :value="modelValue"
      aria-label="搜索 Session（标题、仓库或根会话 ID）"
      autocomplete="off"
      placeholder="搜索标题、仓库或根会话 ID"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    >
  </label>
</template>

<style scoped>
.search-box {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
}

.search-box:focus-within {
  border-color: var(--blue);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--blue) 12%, transparent);
}

svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: var(--text-faint);
  stroke-width: 1.8;
}

input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 12px;
}

input::placeholder {
  color: var(--text-faint);
}
</style>
