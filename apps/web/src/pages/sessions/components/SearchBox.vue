<script setup lang="ts">
defineProps({
  modelValue: {
    type: String,
    default: "",
  },
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
}>();

function submitOnEnter(event: KeyboardEvent) {
  if (event.isComposing) return;
  event.preventDefault();
  emit("submit");
}
</script>

<template>
  <div class="search">
    <div class="search-box">
      <button
        class="search-submit"
        type="button"
        aria-label="查询 Session"
        @click="emit('submit')"
      >
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
      </button>
      <input
        data-testid="search-input"
        :value="modelValue"
        aria-label="搜索 Session（完整 root Session ID）"
        autocomplete="off"
        placeholder="输入 root session ID，回车查询"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        @keydown.enter="submitOnEnter"
      >
    </div>
    <span class="search-hint">Enter 精确查询 · 清空后回车恢复最新 10 个</span>
  </div>
</template>

<style scoped>
.search {
  display: grid;
  gap: 5px;
}

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

.search-submit {
  display: flex;
  flex-shrink: 0;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.search-submit:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
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

.search-hint {
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.5;
}
</style>
