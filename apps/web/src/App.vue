<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { RouterView } from "vue-router";

import TopNav from "./components/layout/TopNav.vue";
import { fetchHealth } from "./api/health";
import { queryKeys } from "./api/queryKeys";

const { data, error, isPending } = useQuery({
  queryFn: fetchHealth,
  queryKey: queryKeys.health
});

const status = computed(() => {
  if (isPending.value) {
    return "连接中…";
  }
  if (error.value || !data.value) {
    return "API 未连接";
  }
  return data.value.db.ok ? "API 已连接" : "数据库异常";
});

const databaseLabel = computed(() => {
  if (!data.value) {
    return "数据库";
  }
  return data.value.db.dialect === "mysql" ? "MySQL" : "SQLite";
});

const statusTone = computed(() => {
  if (!data.value) {
    return isPending.value ? "pending" : "error";
  }
  return data.value.db.ok ? "ok" : "error";
});
</script>

<template>
  <div class="shell">
    <TopNav />
    <main>
      <p
        class="status-pill"
        :class="statusTone"
        aria-live="polite"
      >
        <span class="status-dot" />
        {{ status }}<template v-if="data?.db?.ok">
          · {{ databaseLabel }}
        </template>
      </p>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  background: var(--page-gradient);
  color: var(--text-primary);
}

main {
  width: min(1080px, calc(100% - var(--space-xl)));
  margin: 0 auto;
  padding-top: var(--space-lg);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 var(--space-md);
  padding: 6px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface-overlay);
  color: var(--text-muted);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: var(--radius-circle);
  background: var(--state-neutral);
}

.status-pill.ok {
  color: var(--state-success-text);
  border-color: var(--state-success-border);
  background: var(--state-success-surface);
}

.status-pill.ok .status-dot {
  background: var(--state-success);
}

.status-pill.error {
  color: var(--state-error-text);
  border-color: var(--state-error-border);
  background: var(--state-error-surface);
}

.status-pill.error .status-dot {
  background: var(--state-error);
}
</style>
