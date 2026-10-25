<script setup lang="ts">
import ErrorState from "../components/ui/ErrorState.vue";
</script>

<template>
  <section class="page">
    <ErrorState
      code="404"
      message="页面不存在或已删除"
      :retryable="false"
      title="页面不可用"
    />
    <RouterLink to="/sessions">
      返回 Session 浏览器
    </RouterLink>
  </section>
</template>

<style scoped>
.page {
  display: grid;
  gap: 14px;
  padding: 8px 0;
}

a {
  width: max-content;
  color: var(--blue);
  font-size: 12.5px;
}
</style>
