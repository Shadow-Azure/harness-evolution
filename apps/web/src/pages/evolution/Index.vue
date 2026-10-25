<script setup lang="ts">
import { VueFlow } from "@vue-flow/core";
import "@vue-flow/core/dist/style.css";

import EmptyState from "../../components/ui/EmptyState.vue";

defineOptions({ name: "EvolutionPage" });
</script>

<template>
  <section class="placeholder">
    <p class="eyebrow">
      EVOLUTION
    </p>
    <h1>自进化</h1>
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
  display: grid;
  gap: 14px;
  padding: 8px 0;
}

.eyebrow {
  margin: 0;
  color: var(--purple);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

h1 {
  margin: 0;
  font-size: var(--font-title);
  font-weight: 650;
}

.canvas {
  height: 320px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-panel);
  box-shadow: var(--shadow-card);
}
</style>
