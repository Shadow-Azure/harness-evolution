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
const isWorkspace = computed(() => route.meta.workspace === true);

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
    <main
      :class="{
        'auth-main': isAuthLayout,
        'workspace-main': isWorkspace && !isAuthLayout,
      }"
    >
      <template v-if="isAuthLayout">
        <RouterView />
      </template>
      <template v-else>
        <section
          v-if="isPending"
          class="shell-state"
          data-testid="health-loading"
        >
          <LoadingSkeleton
            label="正在连接 API"
            :rows="2"
          />
        </section>
        <ErrorState
          v-else-if="healthFailure"
          class="shell-state"
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
  background: var(--bg);
  color: var(--text-primary);
}

main {
  width: min(1280px, calc(100% - 48px));
  margin: 0 auto;
  padding: 20px 0 64px;
}

main.auth-main {
  width: 100%;
  padding-top: 0;
}

main.workspace-main {
  width: 100%;
  height: calc(100vh - var(--shell-header-height));
  padding: 0;
  overflow: hidden;
}

.shell-state {
  margin-bottom: 14px;
}

@media (max-width: 640px) {
  main {
    width: calc(100% - 24px);
    padding-top: 12px;
  }

  main.workspace-main {
    width: 100%;
    height: auto;
    padding: 0;
    overflow: visible;
  }
}
</style>
