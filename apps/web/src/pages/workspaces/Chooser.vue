<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "../../stores/auth";
import {
  DEFAULT_WORKSPACE_PATH,
  readLastWorkspaceId,
  rememberWorkspace,
  workspacePath,
} from "../../router/workspace";
import {
  canManageWorkspace,
  workspaceMark,
  workspaceQuotaPercent,
  workspaceRoleLabel,
} from "../../utils/workspaceDisplay";

defineOptions({ name: "WorkspaceChooserPage" });

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const workspaces = computed(() => auth.workspaces);
const lastWorkspaceId = computed(() => readLastWorkspaceId());
const notice = computed(() => {
  if (route.query.reason === "forbidden") {
    return "你没有该空间的访问权限，请选择其他空间。";
  }
  if (route.query.reason === "select") {
    return "无法从旧链接确定工作空间，请手动选择。";
  }
  return "";
});

/**
 * Enter one workspace at its remembered child route.
 * @param workspaceId Selected workspace identifier.
 * @returns No value.
 */
async function enterWorkspace(workspaceId: string): Promise<void> {
  rememberWorkspace(workspaceId);
  await router.push(workspacePath(workspaceId, DEFAULT_WORKSPACE_PATH));
}
</script>

<template>
  <section
    class="workspace-chooser"
    data-testid="workspace-chooser"
  >
    <header class="chooser-head">
      <p class="eyebrow">
        工作空间
      </p>
      <h1>选择一个工作空间</h1>
      <p class="note">
        每个空间独立保存 bad case、Session 与自进化配置；进入后可在顶栏随时切换。
      </p>
    </header>

    <p
      v-if="notice"
      class="chooser-notice"
      role="status"
      data-testid="workspace-chooser-notice"
    >
      {{ notice }}
    </p>

    <p
      v-if="auth.sessionTruncated"
      class="chooser-notice"
      role="status"
      data-testid="workspace-chooser-truncated"
    >
      可见空间过多，列表只显示前 200 个；请联系管理员确认成员关系。
    </p>

    <p
      v-if="workspaces.length === 0"
      class="chooser-empty"
      data-testid="workspace-chooser-empty"
    >
      当前账号还没有加入任何工作空间。请联系管理员将你加入空间。
    </p>

    <div
      v-else
      class="workspace-grid"
    >
      <button
        v-for="workspace in workspaces"
        :key="workspace.id"
        class="workspace-card"
        :class="{ remembered: workspace.id === lastWorkspaceId }"
        :data-testid="`workspace-card-${workspace.id}`"
        type="button"
        @click="enterWorkspace(workspace.id)"
      >
        <div class="card-head">
          <span class="ws-mark">{{ workspaceMark(workspace) }}</span>
          <span class="card-title">
            <strong>{{ workspace.name }}</strong>
            <span class="card-id">{{ workspace.id }}</span>
          </span>
          <span class="role-badge">{{ workspaceRoleLabel(workspace.role) }}</span>
        </div>
        <p class="card-meta">
          {{ workspace.memberCount }} 名成员 ·
          {{ workspace.spaceAdminCount }} 名空间管理员
        </p>
        <div class="quota">
          <div class="quota-line">
            <span>bad case 额度</span>
            <span class="mono">
              {{ workspace.used }} / {{ workspace.quota }}
            </span>
          </div>
          <div class="quota-bar">
            <span
              :class="{ hot: workspaceQuotaPercent(workspace.used, workspace.quota) > 80 }"
              :style="{ width: `${workspaceQuotaPercent(workspace.used, workspace.quota)}%` }"
            />
          </div>
        </div>
        <span class="card-action">
          {{ canManageWorkspace(workspace.role) ? "进入并管理空间 →" : "进入空间 →" }}
        </span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.workspace-chooser {
  width: min(1080px, calc(100% - 48px));
  margin: 0 auto;
  padding: 46px 0 64px;
}

.chooser-head {
  max-width: 640px;
  margin-bottom: 22px;
}

.eyebrow {
  margin: 0 0 6px;
  color: var(--blue);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.chooser-head h1 {
  margin: 0;
  color: var(--text);
  font-size: 24px;
  font-weight: 700;
}

.note {
  margin: 8px 0 0;
  color: var(--text-dim);
  font-size: 13px;
  line-height: 1.6;
}

.chooser-notice {
  margin: 0 0 14px;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--orange) 35%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  color: var(--text-dim);
  font-size: 12px;
}

.chooser-empty {
  padding: 28px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 13px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.workspace-card {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease,
    transform 0.15s ease;
}

.workspace-card:hover,
.workspace-card:focus-visible {
  border-color: color-mix(in srgb, var(--blue) 45%, var(--border));
  box-shadow: var(--shadow-card);
  outline: none;
  transform: translateY(-1px);
}

.workspace-card.remembered {
  border-color: color-mix(in srgb, var(--blue) 35%, var(--border));
}

.card-head {
  display: flex;
  align-items: center;
  gap: 9px;
}

.ws-mark {
  display: inline-grid;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--blue) 22%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--blue) 12%, transparent);
  color: var(--blue);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
}

.card-title {
  display: grid;
  flex: 1;
  min-width: 0;
}

.card-title strong {
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-id {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}

.role-badge {
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 10px;
  white-space: nowrap;
}

.card-meta {
  margin: 0;
  color: var(--text-faint);
  font-size: 11.5px;
}

.quota {
  display: grid;
  gap: 4px;
}

.quota-line {
  display: flex;
  justify-content: space-between;
  color: var(--text-dim);
  font-size: 11px;
}

.quota-bar {
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--density-track);
}

.quota-bar span {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--blue) 50%, var(--bg-card)),
    var(--blue)
  );
}

.quota-bar span.hot {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--orange) 55%, var(--bg-card)),
    var(--orange)
  );
}

.card-action {
  color: var(--blue);
  font-size: 12px;
  font-weight: 600;
}

.mono {
  font-family: var(--mono);
}

@media (max-width: 640px) {
  .workspace-chooser {
    width: calc(100% - 24px);
    padding-top: 24px;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }
}
</style>
