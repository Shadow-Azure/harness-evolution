<script setup lang="ts">
import { RouterLink } from "vue-router";

import { useCurrentUser, useLogout } from "../../composables/useAuth";

const props = defineProps({
  demo: {
    type: Boolean,
    default: false,
  },
});

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
      aria-label="Harness Evolution"
      class="brand"
      to="/sessions"
    >
      <span
        class="brand-mark"
        aria-hidden="true"
      />
      <span class="brand-copy">
        <strong>Harness Evolution</strong>
        <small>轨迹诊断与自进化</small>
      </span>
    </RouterLink>

    <nav
      class="primary-nav"
      aria-label="Primary"
    >
      <RouterLink
        id="tn-sessions"
        class="tn-item"
        to="/sessions"
      >
        Sessions
      </RouterLink>
      <RouterLink
        id="tn-errors"
        class="tn-item"
        to="/errors"
      >
        Errors
      </RouterLink>
      <RouterLink
        id="tn-evo"
        class="tn-item"
        to="/evolution"
      >
        Evolution
      </RouterLink>
    </nav>

    <div class="actions">
      <span
        v-if="props.demo"
        class="demo-badge"
        data-testid="demo-badge"
      >
        演示数据
      </span>
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
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 350;
  display: flex;
  align-items: stretch;
  height: var(--shell-header-height);
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-right: 26px;
  color: var(--text);
  text-decoration: none;
  white-space: nowrap;
}

.brand-mark {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border-radius: 7px;
  background: var(--brand-gradient);
  box-shadow: var(--shadow-mark);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.brand-copy strong {
  color: var(--text);
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.brand-copy small {
  color: var(--text-faint);
  font-size: 10px;
}

.primary-nav {
  display: flex;
  align-items: stretch;
}

.tn-item {
  display: flex;
  align-items: center;
  margin-bottom: -1px;
  padding: 0 18px;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
}

.tn-item:hover {
  color: var(--text);
}

.tn-item.router-link-active {
  color: var(--text);
  border-bottom-color: var(--blue);
}

.tn-item#tn-evo.router-link-active {
  border-bottom-color: var(--purple);
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-left: auto;
}

.demo-badge {
  padding: 1px 8px;
  border: 1px solid color-mix(in srgb, var(--orange) 45%, transparent);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--orange) 12%, transparent);
  color: var(--orange);
  font-size: 11px;
  white-space: nowrap;
}

.user-menu {
  position: relative;
}

.user-menu summary {
  max-width: 144px;
  overflow: hidden;
  color: var(--text-dim);
  cursor: pointer;
  list-style: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-menu summary::-webkit-details-marker {
  display: none;
}

.user-popover {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  min-width: 160px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  box-shadow: var(--shadow-popover);
}

.user-popover span {
  display: block;
  margin-bottom: 8px;
  color: var(--text-faint);
  font-size: 11px;
}

.user-popover button {
  width: 100%;
  padding: 5px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
}

.user-popover button:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

@media (max-width: 1100px) {
  .brand-copy small {
    display: none;
  }
}

@media (max-width: 640px) {
  .topbar {
    padding-inline: 12px;
  }

  .brand {
    gap: 0;
    margin-right: 10px;
  }

  .brand-copy {
    display: none;
  }

  .tn-item {
    padding-inline: 7px;
    font-size: 12.5px;
  }

  .actions {
    gap: 5px;
  }

  .demo-badge {
    padding: 1px 5px;
    font-size: 10px;
  }

  .user-menu summary {
    max-width: 48px;
  }
}
</style>
