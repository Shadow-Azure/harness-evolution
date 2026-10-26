<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <RouterLink
    class="target-config-entry"
    to="/evolution/targets"
    aria-label="配置进化对象"
    title="配置进化对象"
  >
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
    >
      <path
        d="M12 8.5A3.5 3.5 0 1 0 12 15.5A3.5 3.5 0 0 0 12 8.5Z"
      />
      <path
        d="M19 13.5v-3l-2-.6a7 7 0 0 0-.8-1.8l1-1.8L15 4.1l-1.7 1a7 7 0 0 0-1.8-.8L11 2.5H8l-.6 1.8a7 7 0 0 0-1.8.8l-1.8-1-2.2 2.2 1 1.8a7 7 0 0 0-.8 1.8l-1.8.6v3l1.8.6a7 7 0 0 0 .8 1.8l-1 1.8 2.2 2.2 1.8-1a7 7 0 0 0 1.8.8l.6 1.8h3l.6-1.8a7 7 0 0 0 1.8-.8l1.8 1 2.2-2.2-1-1.8a7 7 0 0 0 .8-1.8l1.8-.6Z"
      />
    </svg>
  </RouterLink>
</template>

<style scoped>
.target-config-entry {
  display: inline-grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  text-decoration: none;
}

.target-config-entry:hover,
.target-config-entry:focus-visible {
  border-color: var(--blue);
  color: var(--blue);
}

.target-config-entry svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.6;
}
</style>
