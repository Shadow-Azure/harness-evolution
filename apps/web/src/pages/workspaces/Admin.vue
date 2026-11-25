<script setup lang="ts">
import type {
  Workspace,
  WorkspaceCreateRequest,
  WorkspaceRole,
  WorkspaceUpdateRequest,
} from "@harness/contracts";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import {
  useAllUsers,
  useCreateWorkspace,
  useUpdateWorkspace,
  useWorkspaceList,
} from "../../composables/useWorkspaces";
import { useWorkspaceId } from "../../composables/useWorkspaceId";
import { useAuthStore } from "../../stores/auth";
import {
  canManageWorkspace,
  workspaceRoleLabel,
} from "../../utils/workspaceDisplay";
import AuthTab from "./components/AuthTab.vue";
import AttributionSkillsTab from "./components/AttributionSkillsTab.vue";
import BadCaseLabelsTab from "./components/BadCaseLabelsTab.vue";
import IngestTab from "./components/IngestTab.vue";
import MembersTab from "./components/MembersTab.vue";
import SpacesTab from "./components/SpacesTab.vue";
import WorkspaceFormDialog from "./components/WorkspaceFormDialog.vue";

defineOptions({ name: "WorkspaceAdminPage" });

type AdminTab =
  | "spaces"
  | "members"
  | "ingest"
  | "bad-case-labels"
  | "attribution-skills"
  | "auth";

const TABS: ReadonlyArray<{ key: AdminTab; label: string }> = [
  { key: "spaces", label: "空间与额度" },
  { key: "members", label: "成员与角色" },
  { key: "ingest", label: "上报接入" },
  { key: "bad-case-labels", label: "Badcase 类型" },
  { key: "attribution-skills", label: "归因 Skill" },
  { key: "auth", label: "鉴权接入" },
];

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const workspaceId = useWorkspaceId();
const workspaceList = useWorkspaceList();

const dialogOpen = ref(false);
const editingWorkspace = ref<Workspace | null>(null);
const formError = ref("");

const currentSessionWorkspace = computed(() =>
  workspaceId.value ? auth.workspaceById(workspaceId.value) : null,
);
const currentRole = computed<WorkspaceRole | undefined>(
  () => currentSessionWorkspace.value?.role,
);
const isGlobalAdmin = computed(() => auth.user?.role === "admin");
const canManage = computed(() => canManageWorkspace(currentRole.value));
const currentWorkspace = computed<Workspace | null>(() => {
  const items = workspaceList.data.value?.items ?? [];
  return items.find((item) => item.id === workspaceId.value) ?? null;
});
const usersQuery = useAllUsers(isGlobalAdmin);
const users = computed(() => usersQuery.data.value?.items ?? []);

const activeTab = computed<AdminTab>(() => {
  const requested = route.query.tab;
  return TABS.some((tab) => tab.key === requested)
    ? (requested as AdminTab)
    : "spaces";
});

const pageTitle = computed(() =>
  isGlobalAdmin.value ? "工作空间管理" : "空间管理",
);
const pageSub = computed(() => {
  if (isGlobalAdmin.value) {
    return "管理所有空间、成员、额度与上报凭据；唯一全局管理员账号由部署配置播种。";
  }
  if (canManage.value) {
    return "管理当前空间的成员、额度与上报接入；空间数据与权限相互隔离。";
  }
  return "当前角色为只读，写入口已隐藏；如需调整额度、成员或凭据，请联系空间管理员。";
});
const navHint = computed(() =>
  isGlobalAdmin.value
    ? "全局管理员可创建空间、任命空间管理员。"
    : canManage.value
      ? "空间管理员只管理当前空间，不能创建空间。"
      : "只读成员可以查看当前空间与成员列表。",
);

const createWorkspace = useCreateWorkspace();
const updateWorkspace = useUpdateWorkspace(workspaceId);

/**
 * Switch the visible management tab and mirror it in the URL.
 * @param tab Tab identifier from the navigation.
 * @returns No value.
 */
function selectTab(tab: AdminTab): void {
  if (tab === activeTab.value) return;
  void router.replace({
    path: route.path,
    query: { ...route.query, tab },
  });
}

/**
 * Open the creation dialog (global administrator only).
 * @returns No value.
 */
function openCreate(): void {
  if (!isGlobalAdmin.value) return;
  editingWorkspace.value = null;
  formError.value = "";
  dialogOpen.value = true;
}

/**
 * Open the quota dialog for one workspace.
 * @param workspace Workspace being edited.
 * @returns No value.
 */
function openQuota(workspace: Workspace): void {
  if (!canManage.value) return;
  editingWorkspace.value = workspace;
  formError.value = "";
  dialogOpen.value = true;
}

/**
 * Navigate to the members tab of another visible workspace.
 * @param targetWorkspaceId Workspace identifier from the global table.
 * @returns No value.
 */
async function openMembers(targetWorkspaceId: string): Promise<void> {
  if (targetWorkspaceId === workspaceId.value) {
    selectTab("members");
    return;
  }
  await router.push({
    path: `/workspaces/${encodeURIComponent(targetWorkspaceId)}/admin`,
    query: { tab: "members" },
  });
}

/**
 * Persist the create or quota form and keep the dialog open on failure.
 * @param body Validated workspace payload.
 * @returns No value.
 */
async function submitWorkspace(
  body: WorkspaceCreateRequest | WorkspaceUpdateRequest,
): Promise<void> {
  formError.value = "";
  try {
    if (editingWorkspace.value) {
      await updateWorkspace.updateWorkspace(body as WorkspaceUpdateRequest);
    } else {
      await createWorkspace.createWorkspace(body as WorkspaceCreateRequest);
    }
    dialogOpen.value = false;
    editingWorkspace.value = null;
  } catch (error) {
    formError.value = workspaceErrorMessage(error);
  }
}

/**
 * Map workspace mutation failures onto actionable Chinese copy.
 * @param error Unknown mutation failure.
 * @returns User-facing message.
 */
function workspaceErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "code" in error) {
    const code = String(error.code);
    if (code === "WORKSPACE_EXISTS") return "空间名称已经存在，请换一个名称。";
    if (code === "QUOTA_INVALID") {
      return "额度必须为非负整数，且不能低于当前已上报数量。";
    }
    if (code === "ROLE_INVALID") {
      return "初始空间管理员必须至少选择一个已存在账号。";
    }
  }
  return "保存空间失败，请稍后重试。";
}
</script>

<template>
  <section
    class="evolution-page-frame admin-page"
    data-testid="workspace-admin-page"
  >
    <header class="page-head">
      <div>
        <p class="eyebrow">
          工作空间
        </p>
        <h1>{{ pageTitle }}</h1>
        <p class="page-sub">
          {{ pageSub }}
        </p>
      </div>
      <div class="page-badges">
        <span
          v-if="currentSessionWorkspace"
          class="head-badge"
          data-testid="admin-workspace-badge"
        >
          {{ currentSessionWorkspace.name }}
        </span>
        <span
          v-if="currentRole"
          class="head-badge role"
          data-testid="admin-role-badge"
        >
          {{ workspaceRoleLabel(currentRole) }}
        </span>
        <span
          v-if="!canManage"
          class="head-badge readonly"
          data-testid="admin-readonly-badge"
        >
          只读
        </span>
      </div>
    </header>

    <LoadingSkeleton
      v-if="workspaceList.isPending.value"
      label="正在读取工作空间"
      :rows="4"
    />
    <ErrorState
      v-else-if="workspaceList.error.value"
      code="WORKSPACE_LIST_UNAVAILABLE"
      message="工作空间读取失败，请重试。"
      @retry="workspaceList.refetch"
    />
    <div
      v-else
      class="admin-grid"
    >
      <aside class="admin-nav">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          :class="{ active: activeTab === tab.key }"
          :data-testid="`admin-tab-${tab.key}`"
          type="button"
          @click="selectTab(tab.key)"
        >
          {{ tab.label }}
        </button>
        <div class="an-sep" />
        <p class="an-hint">
          {{ navHint }}
        </p>
      </aside>

      <section
        class="admin-content"
        data-testid="admin-content"
      >
        <SpacesTab
          v-if="activeTab === 'spaces'"
          :workspaces="workspaceList.data.value?.items ?? []"
          :current="currentWorkspace"
          :role="currentRole"
          :can-manage="canManage"
          :is-global-admin="isGlobalAdmin"
          @create="openCreate"
          @edit-quota="openQuota"
          @open-members="openMembers"
        />
        <MembersTab
          v-else-if="activeTab === 'members'"
          :workspace-id="workspaceId"
          :workspace-name="currentSessionWorkspace?.name ?? ''"
          :current-user-id="auth.user?.id ?? ''"
          :role="currentRole"
          :is-global-admin="isGlobalAdmin"
          :can-manage="canManage"
        />
        <IngestTab
          v-else-if="activeTab === 'ingest'"
          :workspace-id="workspaceId"
          :workspace="currentWorkspace"
          :can-manage="canManage"
        />
        <BadCaseLabelsTab
          v-else-if="activeTab === 'bad-case-labels'"
          :workspace-id="workspaceId"
          :can-manage="canManage"
        />
        <AttributionSkillsTab
          v-else-if="activeTab === 'attribution-skills'"
          :workspace-id="workspaceId"
          :can-manage="canManage"
        />
        <AuthTab v-else />
      </section>
    </div>

    <WorkspaceFormDialog
      v-model="dialogOpen"
      :workspace="editingWorkspace"
      :users="users"
      :current-user-id="auth.user?.id ?? ''"
      :submitting="
        editingWorkspace
          ? updateWorkspace.isPending.value
          : createWorkspace.isPending.value
      "
      :server-error="formError"
      @submit="submitWorkspace"
    />
  </section>
</template>

<style scoped>
.admin-page {
  display: grid;
  gap: 16px;
  align-content: start;
  height: 100%;
  padding-bottom: 48px;
  overflow-y: auto;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--blue);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.page-head h1 {
  margin: 0;
  color: var(--text);
  font-size: 22px;
  font-weight: 700;
}

.page-sub {
  max-width: 760px;
  margin: 6px 0 0;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
}

.page-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.head-badge {
  padding: 2px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  white-space: nowrap;
}

.head-badge.role {
  border-color: color-mix(in srgb, var(--purple) 30%, transparent);
  background: color-mix(in srgb, var(--purple) 8%, transparent);
  color: var(--purple);
}

.head-badge.readonly {
  border-color: color-mix(in srgb, var(--orange) 38%, transparent);
  background: color-mix(in srgb, var(--orange) 9%, transparent);
  color: var(--orange);
  font-weight: 600;
}

.admin-grid {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.admin-nav {
  padding: 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.admin-nav button {
  display: block;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  text-align: left;
}

.admin-nav button:hover {
  background: var(--bg-panel);
  color: var(--text);
}

.admin-nav button.active {
  background: color-mix(in srgb, var(--blue) 9%, var(--bg-card));
  color: var(--blue);
  font-weight: 600;
}

.an-sep {
  margin: 7px 10px;
  border-top: 1px solid var(--border);
}

.an-hint {
  margin: 0;
  padding: 4px 10px 7px;
  color: var(--text-faint);
  font-size: 9.5px;
  line-height: 1.5;
}

.admin-content {
  min-width: 0;
  min-height: 340px;
  padding: 15px 17px 19px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

@media (max-width: 980px) {
  .admin-grid {
    grid-template-columns: 1fr;
  }

  .admin-nav {
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }

  .admin-nav button {
    width: auto;
    white-space: nowrap;
  }

  .an-sep,
  .an-hint {
    display: none;
  }
}
</style>
