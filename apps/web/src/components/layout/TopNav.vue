<script setup lang="ts">
import { RouterLink } from "vue-router";

import { useCurrentUser, useLogout } from "../../composables/useAuth";

const { data: user } = useCurrentUser();
const { isLoading, refetch: logoutUser } = useLogout();

function logout() {
  void logoutUser().catch(() => {
    // The store always clears local state and the mutation still navigates.
  });
}
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
    <details
      v-if="user"
      class="user-menu"
    >
      <summary>{{ user.displayName }}</summary>
      <div class="user-popover">
        <span>{{ user.username }}</span>
        <button
          data-testid="logout"
          :disabled="isLoading"
          type="button"
          @click="logout"
        >
          {{ isLoading ? "退出中…" : "退出登录" }}
        </button>
      </div>
    </details>
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

.user-menu {
  position: relative;
  margin-left: var(--space-md);
}

.user-menu summary {
  color: var(--text-secondary);
  cursor: pointer;
  list-style: none;
}

.user-menu summary::-webkit-details-marker {
  display: none;
}

.user-popover {
  position: absolute;
  top: calc(100% + var(--space-xs));
  right: 0;
  min-width: 160px;
  padding: var(--space-sm);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  box-shadow: var(--shadow-card);
}

.user-popover span {
  display: block;
  margin-bottom: var(--space-xs);
  color: var(--text-muted);
  font-size: 12px;
}

.user-popover button {
  width: 100%;
  padding: 7px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface-overlay);
  color: var(--text-muted);
  cursor: pointer;
}

.user-area button:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
}
</style>
