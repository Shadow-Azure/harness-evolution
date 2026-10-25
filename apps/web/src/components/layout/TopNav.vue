<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <header class="topbar">
    <RouterLink
      class="brand"
      to="/sessions"
    >
      <span class="brand-mark">HL</span>
      <span class="brand-copy">
        <strong>Harness Lens</strong>
        <small>Vue shell</small>
      </span>
    </RouterLink>
    <nav aria-label="Primary">
      <RouterLink to="/sessions">
        Sessions
      </RouterLink>
      <RouterLink to="/evolution">
        Evolution
      </RouterLink>
    </nav>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--shell-header-height);
  padding: 0 var(--space-lg);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-raised);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--text-primary);
  text-decoration: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-md);
  background: var(--brand-gradient);
  color: var(--surface-base);
  font-weight: var(--weight-bold);
}

.brand-copy {
  display: grid;
  gap: 2px;
}

.brand-copy small {
  color: var(--text-muted);
}

nav {
  display: flex;
  gap: var(--space-xs);
}

nav a {
  padding: 7px 11px;
  border-radius: var(--radius-pill);
  color: var(--text-muted);
  text-decoration: none;
}

nav a.router-link-active {
  color: var(--text-primary);
  background: var(--surface-selected);
}
</style>
