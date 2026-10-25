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
  gap: var(--space-md);
  padding: var(--space-xl) 0;
}

header {
  display: grid;
  gap: var(--space-xs);
}

.eyebrow {
  margin: 0;
  color: var(--brand-accent);
  font-size: 12px;
  font-weight: var(--weight-bold);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: var(--font-title);
}
</style>
