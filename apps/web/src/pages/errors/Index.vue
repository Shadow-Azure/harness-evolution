<script setup lang="ts">
import EmptyState from "../../components/ui/EmptyState.vue";

defineOptions({ name: "ErrorsPage" });
</script>

<template>
  <section class="page">
    <header>
      <p class="eyebrow">
        Errors
      </p>
      <h1>问题与归因</h1>
    </header>
    <EmptyState
      description="问题归属将在后续 milestone 接入；当前不展示模拟问题。"
      title="暂无问题"
    />
  </section>
</template>

<style scoped>
.page {
  display: grid;
  gap: 14px;
  padding: 8px 0;
}

header {
  display: grid;
  gap: var(--space-xs);
}

.eyebrow {
  margin: 0;
  color: var(--blue);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: var(--font-title);
  font-weight: 650;
}
</style>
