<script setup lang="ts">
import ChangePasswordCard from "./ChangePasswordCard.vue";

defineOptions({ name: "ChangePasswordPage" });
</script>

<template>
  <section class="auth-page">
    <ChangePasswordCard />
  </section>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--space-lg);
  background: var(--page-gradient);
}
</style>
