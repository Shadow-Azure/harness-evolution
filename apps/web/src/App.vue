<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { RouterView, useRoute } from "vue-router";

import TopNav from "./components/layout/TopNav.vue";
import ErrorState from "./components/ui/ErrorState.vue";
import LoadingSkeleton from "./components/ui/LoadingSkeleton.vue";
import { fetchHealth } from "./api/health";
import { ApiError } from "./api/http";
import { queryKeys } from "./api/queryKeys";

const route = useRoute();
const isAuthLayout = computed(() => route.meta.authLayout === true);

const { data, error, isPending, refetch } = useQuery({
  enabled: computed(() => !isAuthLayout.value),
  queryFn: fetchHealth,
  queryKey: queryKeys.health
});

const isConflict = computed(
  () => error.value instanceof ApiError && error.value.status === 409,
);

const healthFailure = computed(() => {
  if (isPending.value || isConflict.value) {
    return false;
  }
  return Boolean(
    error.value ||
      !data.value ||
      !data.value.ok ||
      !data.value.db.ok,
  );
});

const healthErrorCode = computed(() => {
  if (error.value instanceof ApiError) {
    return error.value.code;
  }
  return "HEALTH_UNAVAILABLE";
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

function retryHealth() {
  void refetch().catch(() => {
    // The shared error state remains visible with the latest failure.
  });
}
</script>

<template>
  <div class="shell">
    <TopNav
      v-if="!isAuthLayout"
      :demo="data?.phase === 'demo'"
    />
    <main :class="{ 'auth-main': isAuthLayout }">
      <template v-if="isAuthLayout">
        <RouterView />
      </template>
      <template v-else>
        <p
          v-if="data && !isConflict"
          class="status-pill"
          :class="statusTone"
          aria-live="polite"
        >
          <span class="status-dot" />
          {{ status }}<template v-if="data?.db?.ok">
            · {{ databaseLabel }}
          </template>
        </p>
        <section
          v-if="isPending"
          data-testid="health-loading"
        >
          <LoadingSkeleton
            label="正在连接 API"
            :rows="2"
          />
        </section>
        <ErrorState
          v-else-if="healthFailure"
          :code="healthErrorCode"
          message="API 或数据库当前不可用，请稍后重试。"
          @retry="retryHealth"
        />
        <RouterView v-else />
      </template>
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

main.auth-main {
  width: 100%;
  padding-top: 0;
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
