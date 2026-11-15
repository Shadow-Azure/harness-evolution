<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { queryKeys } from "../../api/queryKeys";
import { useAuthStore } from "../../stores/auth";
import {
  workspaceMark,
  workspaceQuotaPercent,
  workspaceRoleLabel,
} from "../../utils/workspaceDisplay";
import {
  DEFAULT_WORKSPACE_PATH,
  rememberWorkspace,
  switchableWorkspaceChild,
  workspacePath,
} from "../../router/workspace";

defineOptions({ name: "WorkspacePicker" });

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const queryClient = useQueryClient();
const root = ref<HTMLDetailsElement | null>(null);

const currentId = computed(() =>
  typeof route.params.wid === "string" ? route.params.wid : "",
);
const current = computed(() =>
  currentId.value ? auth.workspaceById(currentId.value) : null,
);
const visible = computed(() => auth.workspaces);
const currentRole = computed(() => current.value?.role);

/**
 * Build the same child route under another workspace while preserving query.
 * @param workspaceId Destination workspace identifier.
 * @returns App-relative destination path.
 */
function targetPath(workspaceId: string): string {
  if (!currentId.value) {
    return workspacePath(workspaceId, DEFAULT_WORKSPACE_PATH);
  }
  const prefix = `/workspaces/${encodeURIComponent(currentId.value)}`;
  const child = route.path.startsWith(prefix)
    ? route.path.slice(prefix.length)
    : "";
  return workspacePath(
    workspaceId,
    switchableWorkspaceChild(child || `/${DEFAULT_WORKSPACE_PATH}`),
  );
}

/**
 * Switch workspace, invalidate the previous workspace cache tree, and navigate.
 * @param workspaceId Destination workspace identifier.
 * @returns No value.
 */
async function switchWorkspace(workspaceId: string): Promise<void> {
  if (root.value) root.value.open = false;
  if (workspaceId === currentId.value) return;
  if (currentId.value) {
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workspace(currentId.value),
    });
  }
  rememberWorkspace(workspaceId);
  const query = { ...route.query };
  delete query.reason;
  await router.push({
    path: targetPath(workspaceId),
    query,
  });
}
</script>

<template>
  <details
    v-if="current && currentRole"
    ref="root"
    class="workspace-picker"
    data-testid="workspace-picker"
  >
    <summary :aria-label="`切换工作空间：${current.name}`">
      <span class="ws-mark">{{ workspaceMark(current) }}</span>
      <span class="ws-name">{{ current.name }}</span>
      <span class="ws-role">{{ workspaceRoleLabel(currentRole) }}</span>
      <span class="ws-caret">⌄</span>
    </summary>
    <div
      class="ws-pop"
      data-testid="workspace-picker-menu"
    >
      <div class="ws-head">
        我的工作空间 · {{ visible.length }}
      </div>
      <button
        v-for="workspace in visible"
        :key="workspace.id"
        class="ws-option"
        :class="{ active: workspace.id === currentId }"
        :data-testid="`workspace-option-${workspace.id}`"
        type="button"
        @click="switchWorkspace(workspace.id)"
      >
        <span class="ws-mark">{{ workspaceMark(workspace) }}</span>
        <span class="wo-main">
          <b>{{ workspace.name }}</b>
          <span>
            {{ workspace.used }} / {{ workspace.quota }} bad case ·
            {{ workspace.memberCount }} 名成员
          </span>
          <span class="wo-quota">
            <span
              class="wo-quota-bar"
              :class="{ hot: workspaceQuotaPercent(workspace.used, workspace.quota) > 80 }"
              :style="{ width: `${workspaceQuotaPercent(workspace.used, workspace.quota)}%` }"
            />
          </span>
        </span>
        <span class="wo-role">{{ workspaceRoleLabel(workspace.role) }}</span>
      </button>
      <div class="ws-foot">
        空间数据与权限相互隔离
      </div>
    </div>
  </details>
</template>

<style scoped>
.workspace-picker {
  position: relative;
  min-width: 0;
}

.workspace-picker summary {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  color: var(--text-dim);
  cursor: pointer;
  font-size: 11px;
  list-style: none;
  white-space: nowrap;
}

.workspace-picker summary::-webkit-details-marker {
  display: none;
}

.workspace-picker summary:hover,
.workspace-picker[open] summary {
  border-color: color-mix(in srgb, var(--blue) 42%, var(--border));
  color: var(--text);
}

.ws-mark {
  display: inline-grid;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--blue) 22%, transparent);
  border-radius: 5px;
  background: color-mix(in srgb, var(--blue) 12%, transparent);
  color: var(--blue);
  font-family: var(--mono);
  font-size: 8.5px;
  font-weight: 700;
}

.ws-name {
  max-width: 132px;
  overflow: hidden;
  color: var(--text);
  font-weight: 600;
  text-overflow: ellipsis;
}

.ws-role {
  color: var(--text-faint);
  font-size: 9.5px;
}

.ws-caret {
  color: var(--text-faint);
  font-size: 9px;
}

.ws-pop {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 360;
  width: 322px;
  padding: 7px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-panel);
  box-shadow: var(--shadow-popover);
}

.ws-head {
  padding: 6px 8px 7px;
  color: var(--text-faint);
  font-size: 10.5px;
}

.ws-option {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.ws-option:hover {
  background: color-mix(in srgb, var(--blue) 6%, var(--bg-card));
}

.ws-option.active {
  border-color: color-mix(in srgb, var(--blue) 35%, transparent);
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
}

.wo-main {
  flex: 1;
  min-width: 0;
}

.wo-main b {
  display: block;
  overflow: hidden;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wo-main span {
  display: block;
  margin-top: 1px;
  color: var(--text-faint);
  font-size: 10px;
}

.wo-quota {
  height: 4px;
  margin-top: 4px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--density-track);
}

.wo-quota-bar {
  display: block;
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--blue) 50%, var(--bg-card)),
    var(--blue)
  );
}

.wo-quota-bar.hot {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--orange) 55%, var(--bg-card)),
    var(--orange)
  );
}

.wo-role {
  flex-shrink: 0;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 9.5px;
}

.ws-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 5px;
  padding: 7px 8px 3px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10.5px;
}

@media (max-width: 1100px) {
  .ws-role {
    display: none;
  }

  .ws-name {
    max-width: 96px;
  }
}

@media (max-width: 640px) {
  .workspace-picker summary {
    gap: 3px;
    padding: 0 4px;
  }

  .ws-name,
  .ws-caret {
    display: none;
  }
}
</style>
