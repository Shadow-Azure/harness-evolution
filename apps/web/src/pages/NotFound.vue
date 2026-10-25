<template>
  <section class="page">
    <p class="eyebrow">
      404
    </p>
    <h1>页面不存在</h1>
    <RouterLink to="/sessions">
      返回会话浏览器
    </RouterLink>
  </section>
</template>

<style scoped>
.page {
  padding: var(--space-xl) 0;
}

.eyebrow {
  color: var(--text-muted);
}
</style>
