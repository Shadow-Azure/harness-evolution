<script setup lang="ts">
import { VueFlow } from "@vue-flow/core";
import "@vue-flow/core/dist/style.css";

import EmptyState from "../../components/ui/EmptyState.vue";

defineOptions({ name: "EvolutionPage" });
</script>

<template>
  <section class="placeholder">
    <h1>Evolution 骨架</h1>
    <EmptyState
      description="自进化运行将在后续 milestone 接入；Vue Flow 容器已就绪。"
      title="暂无自进化运行"
    />
    <div
      class="canvas"
      style="height: 320px; width: 100%"
    >
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

.canvas {
  margin-top: var(--space-md);
  height: 320px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface-overlay);
}
</style>
