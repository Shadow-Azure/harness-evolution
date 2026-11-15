<script setup lang="ts">
import type {
  WorkspaceMember,
  WorkspaceMemberCreateRequest,
  WorkspaceMemberRole,
  WorkspaceRole,
} from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { computed, ref } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import {
  useAddWorkspaceMember,
  useAppointSelfAsSpaceAdmin,
  useRemoveWorkspaceMember,
  useUpdateWorkspaceMember,
  useWorkspaceMembers,
} from "../../../composables/useWorkspaces";
import MemberFormDialog from "./MemberFormDialog.vue";

const props = withDefaults(
  defineProps<{
    workspaceId: string;
    workspaceName?: string;
    currentUserId: string;
    role?: WorkspaceRole;
    isGlobalAdmin: boolean;
    canManage: boolean;
  }>(),
  {
    workspaceName: "",
    role: undefined,
  },
);

const canReadMembers = computed(() => props.role !== "viewer");
const membersQuery = useWorkspaceMembers(
  () => props.workspaceId,
  () => canReadMembers.value,
);
const addMember = useAddWorkspaceMember(() => props.workspaceId);
const updateMember = useUpdateWorkspaceMember(() => props.workspaceId);
const removeMember = useRemoveWorkspaceMember(() => props.workspaceId);
const appointSelf = useAppointSelfAsSpaceAdmin(() => props.workspaceId);

const addDialogOpen = ref(false);
const operationError = ref("");

const members = computed(() => membersQuery.data.value?.items ?? []);
const currentMembership = computed(
  () => members.value.find((member) => member.userId === props.currentUserId) ?? null,
);
const canAppointSelf = computed(
  () =>
    props.isGlobalAdmin &&
    props.canManage &&
    currentMembership.value?.role !== "space_admin",
);
const roleOptions = computed<Array<{ value: WorkspaceMemberRole; label: string }>>(
  () => [
    ...(props.isGlobalAdmin
      ? [{ value: "space_admin" as const, label: "空间管理员" }]
      : []),
    { value: "member", label: "成员" },
    { value: "viewer", label: "只读成员" },
  ],
);

function isLocked(member: WorkspaceMember): boolean {
  return !props.isGlobalAdmin && member.role === "space_admin";
}

function canRemove(member: WorkspaceMember): boolean {
  return (
    props.canManage &&
    member.userId !== props.currentUserId &&
    !isLocked(member)
  );
}

async function changeRole(
  member: WorkspaceMember,
  role: WorkspaceMemberRole,
): Promise<void> {
  if (role === member.role) return;
  operationError.value = "";
  try {
    await updateMember.updateMember(member.userId, { role });
    ElMessage.success("成员角色已更新");
  } catch (error) {
    operationError.value = memberErrorMessage(error, "更新成员角色失败");
    await membersQuery.refetch();
  }
}

async function confirmRemove(member: WorkspaceMember): Promise<void> {
  operationError.value = "";
  try {
    await ElMessageBox.confirm(
      `将 ${member.displayName} 移出「${props.workspaceName || "当前空间"}」？`,
      "移除成员",
      {
        type: "warning",
        confirmButtonText: "移除",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  try {
    await removeMember.removeMember(member.userId);
    ElMessage.success("成员已移除");
  } catch (error) {
    operationError.value = memberErrorMessage(error, "移除成员失败");
  }
}

async function submitMember(body: WorkspaceMemberCreateRequest): Promise<void> {
  operationError.value = "";
  try {
    const added = await addMember.addMember(body);
    addDialogOpen.value = false;
    ElMessage.success(`已添加 ${added.displayName}`);
  } catch (error) {
    operationError.value = memberErrorMessage(error, "添加成员失败");
  }
}

async function appointSelfAsAdmin(): Promise<void> {
  operationError.value = "";
  try {
    await appointSelf.appointSelf();
    ElMessage.success("已把自己设为该空间的空间管理员");
  } catch (error) {
    operationError.value = memberErrorMessage(error, "设置空间管理员失败");
  }
}

function memberErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "code" in error) {
    switch (String(error.code)) {
      case "MEMBER_EXISTS":
        return "该用户已在空间中。";
      case "ROLE_LOCKED":
        return "空间管理员行受保护，只能由全局管理员调整。";
      case "MEMBER_NOT_FOUND":
        return "成员不存在或已被移除。";
      case "ROLE_INVALID":
        return "不能把其他成员提升为空间管理员。";
      default:
        break;
    }
  }
  return `${fallback}，请稍后重试。`;
}
</script>

<template>
  <div data-testid="members-tab">
    <div class="admin-head">
      <div>
        <h2>成员与角色</h2>
        <p class="sub">
          空间管理员拥有本空间全部操作权限；空间管理员可以添加成员，但只能授予管理员以下的权限。
        </p>
      </div>
      <div
        v-if="canManage"
        class="actions"
      >
        <button
          v-if="canAppointSelf"
          class="btn"
          data-testid="appoint-self-admin"
          type="button"
          @click="appointSelfAsAdmin"
        >
          把自己设为空间管理员
        </button>
        <button
          class="btn primary"
          data-testid="add-workspace-member"
          type="button"
          @click="addDialogOpen = true"
        >
          ＋ 添加成员
        </button>
      </div>
    </div>

    <p
      v-if="operationError"
      class="operation-error"
      role="alert"
      data-testid="members-operation-error"
    >
      {{ operationError }}
    </p>

    <p
      v-if="!canReadMembers"
      class="readonly-card"
      data-testid="members-readonly"
    >
      只读成员不能查看成员列表；如需查看角色或申请权限，请联系空间管理员。
    </p>
    <LoadingSkeleton
      v-else-if="membersQuery.isPending.value"
      label="正在读取空间成员"
      :rows="4"
    />
    <ErrorState
      v-else-if="membersQuery.error.value"
      code="WORKSPACE_MEMBERS_UNAVAILABLE"
      message="成员列表读取失败，请重试。"
      @retry="membersQuery.refetch"
    />
    <div
      v-else
      class="table-scroll"
    >
      <table class="admin-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>空间角色</th>
            <th>加入时间</th>
            <th>标记</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="member in members"
            :key="member.userId"
            :data-testid="`member-row-${member.userId}`"
          >
            <td>
              <b class="member-name">{{ member.displayName }}</b>
              <span class="member-username">{{ member.username }}</span>
            </td>
            <td>
              <span
                v-if="isLocked(member)"
                class="locked-role"
                :title="'空间管理员不能修改其他空间管理员'"
                data-testid="member-locked-role"
              >
                空间管理员
              </span>
              <select
                v-else-if="canManage"
                class="role-select"
                :data-testid="`member-role-${member.userId}`"
                :value="member.role"
                @change="changeRole(member, ($event.target as HTMLSelectElement).value as WorkspaceMemberRole)"
              >
                <option
                  v-for="option in roleOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
              <span
                v-else
                class="locked-role"
                data-testid="member-readonly-role"
              >
                {{ member.role === "space_admin" ? "空间管理员" : member.role === "viewer" ? "只读成员" : "成员" }}
              </span>
            </td>
            <td class="mono">
              {{ member.joinedAt.slice(0, 10) }}
            </td>
            <td>
              <span
                v-if="member.userId === currentUserId"
                class="self-badge"
              >
                当前账号
              </span>
            </td>
            <td class="row-actions">
              <button
                v-if="canRemove(member)"
                class="link danger"
                type="button"
                @click="confirmRemove(member)"
              >
                移除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="note">
      {{
        isGlobalAdmin
          ? "全局管理员可以任命或撤销空间管理员。"
          : "空间管理员不能把其他成员提升为空间管理员；如需新增管理员，请联系全局管理员。"
      }}
    </p>

    <MemberFormDialog
      v-model="addDialogOpen"
      :workspace-id="workspaceId"
      :workspace-name="workspaceName"
      :can-grant-space-admin="isGlobalAdmin"
      :submitting="addMember.isPending.value"
      :server-error="operationError"
      @submit="submitMember"
    />
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

.operation-error {
  margin: 0 0 10px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--red) 35%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  color: var(--red);
  font-size: 11px;
}

.readonly-card {
  margin: 0;
  padding: 16px;
  border: 1px dashed var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.6;
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

.member-name {
  display: block;
  color: var(--text);
  font-size: 12px;
  font-weight: 650;
}

.member-username {
  display: block;
  margin-top: 1px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
}

.role-select {
  padding: 3px 7px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font: inherit;
  font-size: 11.5px;
}

.locked-role {
  padding: 1px 8px;
  border: 1px solid color-mix(in srgb, var(--purple) 30%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--purple) 8%, transparent);
  color: var(--purple);
  font-size: 10px;
  white-space: nowrap;
}

.self-badge {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 9.5px;
}

.row-actions {
  text-align: right;
  white-space: nowrap;
}

.link {
  padding: 2px 6px;
  border: 0;
  background: transparent;
  color: var(--blue);
  cursor: pointer;
  font: inherit;
}

.link.danger {
  color: var(--red);
}

.note {
  margin: 10px 0 0;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.mono {
  font-family: var(--mono);
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
}

@media (max-width: 980px) {
  .admin-head {
    display: grid;
  }

  .admin-head .actions {
    margin-left: 0;
  }
}
</style>
