<script setup lang="ts">
import { VueFlow } from "@vue-flow/core";
import "@vue-flow/core/dist/style.css";

defineOptions({ name: "EvolutionPage" });
</script>

<template>
  <section class="placeholder">
    <h1>Evolution 骨架</h1>
    <p>Vue Flow 已通过动态 vendor chunk 挂载。</p>
    <div class="canvas">
      <VueFlow
        :edges="[]"
        :nodes="[]"
      />
    </div>
  </section>
</template>

<style scoped>
.placeholder {
  padding: var(--space-xl) 0;
}

h1 {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-title);
}

p {
  margin: 0 0 var(--space-md);
  color: var(--text-muted);
}

.canvas {
  height: 320px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface-overlay);
}
</style>
