<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { RouterLink, useRoute } from "vue-router";
import { computed, onBeforeUnmount, ref } from "vue";

import {
  getAcquisitionStatus,
  getJob,
  triggerSync,
} from "../../api/acquisition";
import { queryKeys } from "../../api/queryKeys";
import { useCurrentUser, useLogout } from "../../composables/useAuth";
import {
  badCaseSyncErrorLabel,
  badCaseSyncStatusLabel,
  catalogSyncErrorLabel,
  catalogSyncStatusLabel,
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
const route = useRoute();
const isProcessing = ref(false);
const actionError = ref("");
let disposed = false;

const activeSection = computed(() => {
  if (route.path.startsWith("/sessions")) return "sessions";
  if (route.path.startsWith("/evolution")) return "evo";
  return "";
});

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

const badCaseSync = computed(() => acquisition.value?.badCaseSync);
const catalogSync = computed(() => acquisition.value?.badCaseCatalogSync);
const analysis = computed(() => acquisition.value?.badCaseAnalysis);

const badCaseSyncDetail = computed(() => {
  const status = badCaseSync.value;
  if (!status) {
    return "";
  }
  if (status.status === "unavailable") {
    return "未配置轨迹查询服务";
  }
  return `总 ${status.total} · 已同步 ${status.synced} · 未同步 ${status.unsynced}`;
});

const badCaseProblemSub = computed(() => {
  const status = badCaseSync.value;
  if (!status || status.status === "unavailable") {
    return "";
  }
  if (status.status === "idle") {
    return `${badCaseSyncStatusLabel(status.status)} · 同步中 ${status.syncing} · 失败 ${status.failed}`;
  }
  if (status.status === "failed") {
    return `同步中 ${status.syncing} · 失败 ${status.failed} · ${badCaseSyncErrorLabel(status.lastError)}`;
  }
  return badCaseSyncStatusLabel(status.status);
});

const badCaseSyncAria = computed(() => {
  const status = badCaseSync.value;
  if (!status) {
    return "";
  }
  if (status.status === "unavailable") {
    return "问题轨迹未配置";
  }
  return `问题轨迹 总 ${status.total} 已同步 ${status.synced} 未同步 ${status.unsynced}`;
});

const catalogDetail = computed(() => {
  const status = catalogSync.value;
  if (!status) {
    return "";
  }
  if (status.status === "unavailable") {
    return "未配置坏例查询服务";
  }
  return `总 ${status.synced + status.unsynced} · 已同步 ${status.synced} · 未同步 ${status.unsynced}`;
});

const catalogSub = computed(() => {
  const status = catalogSync.value;
  if (!status || status.status === "unavailable") {
    return "";
  }
  if (status.status === "failed") {
    return `${catalogSyncStatusLabel(status.status)} · ${catalogSyncErrorLabel(status.lastError)}`;
  }
  if (status.status === "idle") {
    return `${catalogSyncStatusLabel(status.status)} · 游标 #${status.lastBadCaseId}`;
  }
  return catalogSyncStatusLabel(status.status);
});

const catalogSyncAria = computed(() => {
  const status = catalogSync.value;
  if (!status) {
    return "";
  }
  if (status.status === "unavailable") {
    return "问题数量 未配置坏例查询服务";
  }
  return `问题数量 总 ${status.synced + status.unsynced} 已同步 ${status.synced} 未同步 ${status.unsynced}`;
});

const normalizationDetail = computed(() => {
  const status = acquisition.value;
  if (!status) {
    return "";
  }
  return `待处理 ${status.pending} · 已处理 ${status.processed} · 已导入 ${status.imported}`;
});

const normalizationSub = computed(() => {
  const status = acquisition.value;
  if (!status) {
    return "";
  }
  const latestError = status.errors[0]
    ? syncErrorLabel(status.errors[0].code)
    : "";
  return [
    syncStatusLabel(status.status),
    `跳过 ${status.skipped}`,
    latestError ? `最近问题：${latestError}` : ""
  ]
    .filter(Boolean)
    .join(" · ");
});

const analysisDetail = computed(() => {
  const progress = analysis.value;
  if (!progress) {
    return "";
  }
  return `已分析 ${progress.analyzed} · 待分析 ${progress.pending}`;
});

const analysisSub = computed(() => {
  const progress = analysis.value;
  if (!progress) {
    return "";
  }
  return `问题 ${progress.issue} · 非问题 ${progress.nonIssue}`;
});

const analysisAria = computed(() => {
  const progress = analysis.value;
  if (!progress) {
    return "";
  }
  return `归因分析 已分析 ${progress.analyzed} 待分析 ${progress.pending}`;
});

const syncAria = computed(() =>
  [
    pendingLabel.value,
    syncDetail.value,
    badCaseSyncAria.value,
    catalogSyncAria.value,
    analysisAria.value
  ]
    .filter(Boolean)
    .join("；")
);

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
  let terminalStatus = "";
  try {
    const triggered = await triggerSync();
    if (!triggered.jobId) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.acquisitionStatus });
      return;
    }
    while (!disposed) {
      const job = await getJob(triggered.jobId);
      if (["completed", "failed", "interrupted"].includes(job.status)) {
        terminalStatus = job.status;
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
    if (!disposed && terminalStatus === "failed") {
      actionError.value = "同步失败，请稍后重试";
    } else if (!disposed && terminalStatus === "interrupted") {
      actionError.value = "同步已中断，请稍后重试";
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
        :class="{ active: activeSection === 'sessions' }"
        to="/sessions"
      >
        Session 错误查看<span class="tn-sub">会话轨迹与归因</span>
      </RouterLink>
      <RouterLink
        id="tn-evo"
        class="tn-item"
        :class="{ active: activeSection === 'evo' }"
        to="/evolution"
      >
        自进化<span class="tn-sub">报告驱动的迭代优化</span>
      </RouterLink>
    </nav>

    <span class="tn-note">问题与报告 ID 已串联 · 点击 ID 跨页溯源</span>

    <div class="actions">
      <div
        v-if="acquisition"
        class="sync-status"
        data-testid="sync-status"
        tabindex="0"
        :aria-label="syncAria"
      >
        <span class="sync-summary">{{ pendingLabel }}</span>
        <span
          v-if="badCaseSync && badCaseSync.status !== 'unavailable'"
          class="sync-problem-badge"
          data-testid="sync-problem-badge"
        >
          问题轨迹 {{ badCaseSync.synced }}/{{ badCaseSync.total }}
        </span>
        <span class="sync-popover">
          <span class="sync-popover-head">数据同步</span>
          <span
            v-if="catalogSync"
            class="sync-section"
            data-testid="sync-catalog"
          >
            <span class="sync-row">
              <span class="sync-key">问题数量</span>
              <span class="sync-val">{{ catalogDetail }}</span>
            </span>
            <span
              v-if="catalogSub"
              class="sync-problem-sub"
            >
              {{ catalogSub }}
            </span>
          </span>
          <span
            v-if="badCaseSync"
            class="sync-section"
            data-testid="sync-problem"
          >
            <span class="sync-row">
              <span class="sync-key">问题轨迹</span>
              <span class="sync-val">{{ badCaseSyncDetail }}</span>
            </span>
            <span
              v-if="badCaseProblemSub"
              class="sync-problem-sub"
            >
              {{ badCaseProblemSub }}
            </span>
          </span>
          <span
            class="sync-section"
            data-testid="sync-normalization"
          >
            <span class="sync-row">
              <span class="sync-key">会话归一化</span>
              <span class="sync-val">{{ normalizationDetail }}</span>
            </span>
            <span
              v-if="normalizationSub"
              class="sync-problem-sub"
            >
              {{ normalizationSub }}
            </span>
          </span>
          <span
            v-if="analysis"
            class="sync-section"
            data-testid="sync-analysis"
          >
            <span class="sync-row">
              <span class="sync-key">归因分析</span>
              <span class="sync-val">{{ analysisDetail }}</span>
            </span>
            <span class="sync-problem-sub">
              {{ analysisSub }}
            </span>
          </span>
        </span>
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

.tn-sub {
  margin-left: 8px;
  color: var(--text-faint);
  font-size: 10.5px;
  font-weight: 400;
}

.tn-note {
  align-self: center;
  margin-left: auto;
  color: var(--text-faint);
  font-size: 11px;
  white-space: nowrap;
}

.tn-item:hover {
  color: var(--text);
}

.tn-item.active {
  color: var(--text);
  border-bottom-color: var(--blue);
}

.tn-item#tn-evo.active {
  border-bottom-color: var(--purple);
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-left: 12px;
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

.sync-problem-badge {
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--blue) 8%, transparent);
  color: var(--blue);
  font-family: var(--mono);
  font-size: 9.5px;
}

.sync-detail {
  display: block;
}

.sync-popover-head {
  display: block;
  margin-bottom: 4px;
  color: var(--text);
  font-weight: 700;
}

.sync-section {
  display: block;
}

.sync-section + .sync-section {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.sync-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.sync-key {
  color: var(--text-faint);
  white-space: nowrap;
}

.sync-val {
  color: var(--text-dim);
  text-align: right;
}

.sync-normalization-title {
  display: block;
  color: var(--text-faint);
  font-size: 10.5px;
}

.sync-problem {
  display: block;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.sync-problem-title {
  display: block;
  color: var(--text);
  font-weight: 600;
}

.sync-problem-sub {
  display: block;
  color: var(--text-faint);
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

  .tn-sub,
  .tn-note {
    display: none;
  }

  .actions {
    margin-left: auto;
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
