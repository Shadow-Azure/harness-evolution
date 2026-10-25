<script setup lang="ts">
defineProps({
  label: {
    type: String,
    default: "正在加载",
  },
  rows: {
    type: Number,
    default: 3,
  },
});
</script>

<template>
  <div
    class="loading-state"
    role="status"
    aria-live="polite"
    :aria-label="label"
  >
    <span class="visually-hidden">{{ label }}</span>
    <span
      v-for="index in rows"
      :key="index"
      class="skeleton-line"
      aria-hidden="true"
    />
  </div>
</template>

<style scoped>
.loading-state {
  display: grid;
  gap: 10px;
  width: min(100%, 720px);
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.skeleton-line {
  display: block;
  height: 14px;
  border-radius: 4px;
  background: var(--bg-inset);
  animation: pulse 1.5s ease-in-out infinite alternate;
}

.skeleton-line:nth-child(2n) {
  width: 72%;
}

.skeleton-line:nth-child(3n) {
  width: 88%;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

@keyframes pulse {
  from {
    opacity: 0.45;
  }

  to {
    opacity: 1;
  }
}
</style>
