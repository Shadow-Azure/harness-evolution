<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { RouterLink } from "vue-router";
import { computed, onBeforeUnmount, ref } from "vue";

import {
  getAcquisitionStatus,
  getJob,
  triggerSync,
} from "../../api/acquisition";
import { queryKeys } from "../../api/queryKeys";
import { useCurrentUser, useLogout } from "../../composables/useAuth";
import {
  syncErrorLabel,
  syncStatusLabel,
  waitForSyncPoll
} from "../../utils/syncStatus";

const props = defineProps({
  demo: {
    type: Boolean,
    default: false,
  },
});

const { data: user } = useCurrentUser();
const { isLoading, refetch: logoutUser } = useLogout();
const queryClient = useQueryClient();
const isProcessing = ref(false);
const actionError = ref("");
let disposed = false;

const { data: acquisition } = useQuery({
  queryKey: queryKeys.acquisitionStatus,
  queryFn: getAcquisitionStatus,
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    return status === "queued" || status === "running" ? 3_000 : 15_000;
  }
});

const pendingLabel = computed(() => {
  if (!acquisition.value) {
    return "";
  }
  return `待处理 ${acquisition.value.pending}`;
});

const syncDetail = computed(() => {
  const status = acquisition.value;
  if (!status) {
    return "";
  }
  const latestError = status.errors[0]
    ? syncErrorLabel(status.errors[0].code)
    : "";
  return [
    syncStatusLabel(status.status),
    `已处理 ${status.processed}`,
    `最近导入 ${status.imported}`,
    `跳过 ${status.skipped}`,
    latestError ? `最近问题：${latestError}` : ""
  ]
    .filter(Boolean)
    .join(" · ");
});

function logout() {
  void logoutUser().catch(() => {
    // The store always clears local state and the mutation still navigates.
  });
}

async function processNow() {
  if (isProcessing.value) {
    return;
  }
  actionError.value = "";
  isProcessing.value = true;
  try {
    const triggered = await triggerSync();
    if (!triggered.jobId) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.acquisitionStatus });
      return;
    }
    while (!disposed) {
      const job = await getJob(triggered.jobId);
      if (["completed", "failed", "interrupted"].includes(job.status)) {
        break;
      }
      await waitForSyncPoll(500);
    }
    if (!disposed) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.sessions }),
        queryClient.invalidateQueries({ queryKey: queryKeys.acquisitionStatus })
      ]);
    }
  } catch (error) {
    actionError.value =
      error instanceof Error ? error.message : "立即处理失败，请稍后重试";
  } finally {
    isProcessing.value = false;
  }
}

onBeforeUnmount(() => {
  disposed = true;
});
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
      <div
        v-if="acquisition"
        class="sync-status"
        data-testid="sync-status"
        tabindex="0"
        :aria-label="`${pendingLabel}；${syncDetail}`"
      >
        <span class="sync-summary">{{ pendingLabel }}</span>
        <span class="sync-popover">{{ syncDetail }}</span>
      </div>
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
            v-if="user.role === 'admin'"
            class="sync-now"
            data-testid="sync-now"
            :disabled="isProcessing"
            type="button"
            @click="processNow"
          >
            {{ isProcessing ? "处理中…" : "立即处理" }}
          </button>
          <span
            v-if="actionError"
            class="sync-error"
            role="alert"
          >
            {{ actionError }}
          </span>
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

.sync-status {
  position: relative;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.5;
  white-space: nowrap;
  outline: none;
}

.sync-status:hover,
.sync-status:focus-visible {
  border-color: color-mix(in srgb, var(--blue) 42%, var(--border));
  color: var(--text-dim);
}

.sync-popover {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  display: none;
  width: max-content;
  max-width: 300px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  box-shadow: var(--shadow-popover);
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.5;
  white-space: normal;
}

.sync-status:hover .sync-popover,
.sync-status:focus-visible .sync-popover {
  display: block;
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

.user-popover .sync-error {
  margin: 0 0 8px;
  color: var(--red);
}

.user-popover button:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

@media (max-width: 1100px) {
  .brand-copy small {
    display: none;
  }

  .sync-status {
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
