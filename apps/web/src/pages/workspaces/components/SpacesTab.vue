<script setup lang="ts">
import type { Workspace, WorkspaceRole } from "@harness/contracts";
import { computed } from "vue";
import { RouterLink } from "vue-router";

import { workspacePath } from "../../../router/workspace";
import {
  workspaceQuotaPercent,
  workspaceRoleLabel,
} from "../../../utils/workspaceDisplay";

const props = withDefaults(
  defineProps<{
    workspaces: Workspace[];
    current?: Workspace | null;
    role?: WorkspaceRole;
    canManage: boolean;
    isGlobalAdmin: boolean;
  }>(),
  {
    current: null,
    role: undefined,
  },
);

const emit = defineEmits<{
  create: [];
  "edit-quota": [workspace: Workspace];
  "open-members": [workspaceId: string];
}>();

const currentUsed = computed(() => props.current?.used ?? 0);
const currentQuota = computed(() => props.current?.quota ?? 0);
const currentPercent = computed(() =>
  workspaceQuotaPercent(currentUsed.value, currentQuota.value),
);
const isHot = computed(() => currentPercent.value > 80);
const currentAdmins = computed(() =>
  (props.current?.spaceAdmins ?? []).map((admin) => admin.displayName),
);

/**
 * Percentage used by the compact quota bar.
 * @param used Stored bad cases.
 * @param quota Configured bad case quota.
 * @returns Integer percentage between 0 and 100.
 */
function percent(used: number, quota: number): number {
  return workspaceQuotaPercent(used, quota);
}
</script>

<template>
  <div data-testid="spaces-tab">
    <div class="admin-head">
      <div>
        <h2>{{ isGlobalAdmin ? "全部工作空间" : "当前空间与额度" }}</h2>
        <p class="sub">
          {{
            isGlobalAdmin
              ? "创建时设置 bad case 数量上限；创建后仍可调整。管理员可以把任意用户（包括自己）加入空间并任命为空间管理员。"
              : canManage
                ? "空间管理员可以在本空间内调整额度、成员与上报凭据，但不能创建新空间。"
                : "只读成员可以查看当前空间的额度与管理员；写入口由服务端权限决定。"
          }}
        </p>
      </div>
      <div
        v-if="isGlobalAdmin"
        class="actions"
      >
        <button
          class="btn primary"
          data-testid="create-workspace"
          type="button"
          @click="emit('create')"
        >
          ＋ 创建工作空间
        </button>
      </div>
    </div>

    <template v-if="isGlobalAdmin">
      <div class="table-scroll">
        <table class="admin-table">
          <thead>
            <tr>
              <th>工作空间</th>
              <th>额度使用</th>
              <th>空间管理员</th>
              <th>成员</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="workspace in workspaces"
              :key="workspace.id"
              :data-testid="`workspace-row-${workspace.id}`"
            >
              <td class="ws-name-cell">
                <b>{{ workspace.name }}</b>
                <span>{{ workspace.id }} · 创建于 {{ workspace.createdAt.slice(0, 10) }}</span>
              </td>
              <td class="ws-quota-cell">
                <div class="ws-quota-top">
                  <span>{{ workspace.used }} / {{ workspace.quota }}</span>
                  <span>{{ percent(workspace.used, workspace.quota) }}%</span>
                </div>
                <div
                  class="ws-quota-bar"
                  :class="{ hot: percent(workspace.used, workspace.quota) > 80 }"
                >
                  <span :style="{ width: `${percent(workspace.used, workspace.quota)}%` }" />
                </div>
              </td>
              <td>
                <div class="ws-admin-chips">
                  <span
                    v-for="admin in workspace.spaceAdmins"
                    :key="admin.id"
                    class="chip admin"
                  >
                    {{ admin.displayName }}
                  </span>
                  <span
                    v-if="workspace.spaceAdmins.length === 0"
                    class="muted"
                  >
                    未配置
                  </span>
                </div>
              </td>
              <td><span class="mono">{{ workspace.memberCount }}</span> 人</td>
              <td class="row-actions">
                <RouterLink
                  class="btn small"
                  :to="workspacePath(workspace.id, 'sessions')"
                >
                  进入
                </RouterLink>
                <button
                  class="btn small"
                  type="button"
                  @click="emit('open-members', workspace.id)"
                >
                  成员
                </button>
                <button
                  class="btn small"
                  type="button"
                  @click="emit('edit-quota', workspace)"
                >
                  额度
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">
        全局管理员仅有一个账号，不开放注册；普通用户由管理员创建或通过预留的鉴权接入进入系统。
      </p>
    </template>

    <template v-else>
      <div
        v-if="current"
        class="quota-editor"
      >
        <div class="quota-cell">
          <div class="qc-k">
            bad case 额度
          </div>
          <div class="qc-v">
            {{ currentUsed }} <span>/ {{ currentQuota }}</span>
          </div>
          <div
            class="ws-quota-bar"
            :class="{ hot: isHot }"
          >
            <span :style="{ width: `${currentPercent}%` }" />
          </div>
          <div class="qc-s">
            {{ currentPercent }}% 已使用 · 剩余 {{ Math.max(0, currentQuota - currentUsed) }}
          </div>
          <div
            v-if="canManage"
            class="quota-actions"
          >
            <button
              class="btn"
              data-testid="edit-current-quota"
              type="button"
              @click="emit('edit-quota', current)"
            >
              调整额度
            </button>
            <button
              class="btn"
              data-testid="manage-current-members"
              type="button"
              @click="emit('open-members', current.id)"
            >
              管理成员
            </button>
          </div>
          <p
            v-else
            class="readonly-note"
            data-testid="spaces-readonly-note"
          >
            当前角色为 {{ workspaceRoleLabel(role ?? "viewer") }}，不能调整额度。
          </p>
        </div>
        <div class="quota-cell">
          <div class="qc-k">
            空间管理员
          </div>
          <div class="qc-v small">
            {{ currentAdmins.join("、") || "—" }}
          </div>
          <div class="qc-s">
            一个空间可以有多个管理员；空间管理员的权限只在本空间内生效。
          </div>
        </div>
      </div>
      <p
        v-else
        class="note"
      >
        当前空间信息不可用，请刷新后重试。
      </p>
    </template>
  </div>
</template>

<style scoped>
.admin-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.admin-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

.admin-head .sub {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}

.admin-head .actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
  margin-left: auto;
}

.btn {
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
  text-decoration: none;
  white-space: nowrap;
}

.btn:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: white;
  font-weight: 600;
}

.btn.primary:hover {
  background: var(--blue-deep);
  color: white;
}

.btn.small {
  padding: 3px 8px;
  font-size: 11px;
}

.table-scroll {
  min-width: 0;
  overflow-x: auto;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.admin-table th,
.admin-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

.admin-table th {
  background: var(--bg-panel);
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 650;
  white-space: nowrap;
}

.admin-table tr:last-child td {
  border-bottom: none;
}

.ws-name-cell b {
  display: block;
  color: var(--text);
  font-size: 12px;
  font-weight: 650;
}

.ws-name-cell span {
  display: block;
  margin-top: 1px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
}

.ws-quota-cell {
  min-width: 150px;
}

.ws-quota-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 9.5px;
}

.ws-quota-bar {
  height: 6px;
  margin-top: 4px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--density-track);
}

.ws-quota-bar span {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--blue) 50%, var(--bg-card)),
    var(--blue)
  );
}

.ws-quota-bar.hot span {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--orange) 55%, var(--bg-card)),
    var(--orange)
  );
}

.ws-admin-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.chip {
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 9.5px;
  white-space: nowrap;
}

.chip.admin {
  border-color: color-mix(in srgb, var(--purple) 30%, transparent);
  background: color-mix(in srgb, var(--purple) 8%, transparent);
  color: var(--purple);
}

.row-actions {
  white-space: nowrap;
}

.row-actions .btn + .btn {
  margin-left: 4px;
}

.quota-editor {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 4px;
}

.quota-cell {
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
}

.qc-k {
  color: var(--text-faint);
  font-size: 10px;
}

.qc-v {
  margin-top: 3px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 16px;
  font-weight: 650;
}

.qc-v span {
  color: var(--text-faint);
  font-family: inherit;
  font-size: 11px;
  font-weight: 400;
}

.qc-v.small {
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
}

.qc-s {
  margin-top: 3px;
  color: var(--text-faint);
  font-size: 10px;
  line-height: 1.5;
}

.quota-actions {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}

.note {
  margin: 10px 0 0;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.readonly-note {
  margin: 10px 0 0;
  color: var(--orange);
  font-size: 10.5px;
}

.muted {
  color: var(--text-faint);
}

.mono {
  font-family: var(--mono);
}

@media (max-width: 980px) {
  .quota-editor {
    grid-template-columns: 1fr;
  }
}
</style>
