<script setup lang="ts">
import EmptyState from "../../components/ui/EmptyState.vue";

defineOptions({ name: "SessionsPage" });
</script>

<template>
  <section class="placeholder">
    <h1>Session 浏览器</h1>
    <EmptyState
      description="Session 数据将在后续 milestone 接入。"
      title="暂无会话"
    />
  </section>
</template>

<style scoped>
.placeholder {
  padding: var(--space-xl) 0;
}

h1 {
  margin: 0 0 var(--space-md);
  font-size: var(--font-title);
}
</style>
