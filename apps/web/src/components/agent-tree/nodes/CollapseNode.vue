<script setup lang="ts">
import { Handle, Position } from "@vue-flow/core";

defineProps<{
  data: {
    label: string;
  };
}>();
</script>

<template>
  <button
    class="rf-agent collapse"
    type="button"
  >
    {{ data.label }}
    <Handle
      id="in"
      type="target"
      :position="Position.Left"
      class="hidden-handle"
    />
  </button>
</template>

<style scoped>
.rf-agent {
  width: 220px;
  padding: 8px 10px;
  border: 1px dashed var(--text-faint);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.hidden-handle {
  width: 8px;
  height: 8px;
  border: 0;
  background: transparent;
  opacity: 0;
}
</style>
