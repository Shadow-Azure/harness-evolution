<script setup lang="ts">
import EmptyState from "../../components/ui/EmptyState.vue";

defineOptions({ name: "SessionsPage" });
</script>

<template>
  <section class="placeholder">
    <p class="eyebrow">
      SESSIONS
    </p>
    <h1>Session 浏览器</h1>
    <EmptyState
      description="Session 数据将在后续 milestone 接入。"
      title="暂无会话"
    />
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
  color: var(--blue);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

h1 {
  margin: 0;
  font-size: var(--font-title);
  font-weight: 650;
}
</style>
