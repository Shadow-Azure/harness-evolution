<script setup lang="ts">
import type {
  EvolutionTarget,
  EvolutionTargetWrite,
} from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { computed, ref } from "vue";

import {
  useEvolutionTargets,
  useEvolutionTargetVersions,
} from "../../../composables/useEvolutionTargets";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import TargetTable from "./components/TargetTable.vue";
import TargetFormDialog from "./components/TargetFormDialog.vue";

defineOptions({ name: "TargetConfigPage" });

const auth = useAuthStore();
const {
  createTarget,
  data,
  deleteTarget,
  error,
  isPending,
  refetch,
  updateTarget,
} = useEvolutionTargets();

const targets = computed(() => data.value?.items ?? []);
const canWrite = computed(() => auth.user?.role === "admin");
const dialogOpen = ref(false);
const editingTarget = ref<EvolutionTarget | null>(null);
const formError = ref("");
const operationError = ref("");
const submitting = ref(false);
const editingTargetId = computed(() => editingTarget.value?.id ?? null);
const versionsQuery = useEvolutionTargetVersions(editingTargetId);
const versions = computed(() => versionsQuery.data.value?.versions ?? []);

function openCreate(): void {
  if (!canWrite.value) return;
  operationError.value = "";
  editingTarget.value = null;
  formError.value = "";
  dialogOpen.value = true;
}

function openEdit(target: EvolutionTarget): void {
  if (!canWrite.value) return;
  operationError.value = "";
  editingTarget.value = target;
  formError.value = "";
  dialogOpen.value = true;
}

function targetWrite(target: EvolutionTarget): EvolutionTargetWrite {
  return {
    objectType: target.objectType,
    objectName: target.objectName,
    repoUrl: target.repoUrl,
    subDir: target.subDir,
    defaultRef: target.defaultRef,
    enabled: target.enabled,
  };
}

async function removeTarget(target: EvolutionTarget): Promise<void> {
  operationError.value = "";
  try {
    await ElMessageBox.confirm(
      `删除 ${target.objectName} 的配置？有进行中 run 时不可删除。`,
      "删除进化对象",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        distinguishCancelAndClose: true,
      },
    );
  } catch {
    return;
  }
  try {
    await deleteTarget(target.id);
    ElMessage.success("进化对象已删除");
  } catch (errorValue) {
    operationError.value =
      errorValue instanceof ApiError && errorValue.code === "TARGET_IN_USE"
        ? "该对象有进行中 run，不能删除；请等待运行结束后重试。"
        : "删除进化对象失败，请稍后重试。";
  }
}

async function toggleTarget(target: EvolutionTarget): Promise<void> {
  operationError.value = "";
  try {
    await updateTarget(target.id, targetWrite(target));
    ElMessage.success(target.enabled ? "进化对象已启用" : "进化对象已停用");
  } catch {
    operationError.value = "更新进化对象状态失败，请稍后重试。";
  }
}

function targetErrorMessage(errorValue: unknown): string {
  if (errorValue instanceof ApiError) {
    if (errorValue.code === "REPO_INVALID") {
      return "仓库或 ref 无效，请检查地址、子目录与基线";
    }
    if (errorValue.code === "TARGET_EXISTS") {
      return "同类型的对象名称已经配置";
    }
    return errorValue.message || "保存配置失败，请稍后重试";
  }
  return errorValue instanceof Error
    ? errorValue.message
    : "保存配置失败，请稍后重试";
}

async function submitTarget(body: EvolutionTargetWrite): Promise<void> {
  formError.value = "";
  submitting.value = true;
  try {
    if (editingTarget.value) {
      await updateTarget(editingTarget.value.id, body);
    } else {
      await createTarget(body);
    }
    dialogOpen.value = false;
    editingTarget.value = null;
  } catch (errorValue) {
    formError.value = targetErrorMessage(errorValue);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section
    class="target-config-page"
    data-testid="target-config-page"
  >
    <header class="page-heading">
      <div>
        <p class="eyebrow">
          EVOLUTION
        </p>
        <h1>进化对象配置</h1>
        <p class="lede">
          配置可被自进化修改的 skill 与 agent；仓库、引用和路径由后端校验。
        </p>
      </div>
    </header>

    <p
      v-if="operationError"
      class="operation-error"
      role="alert"
    >
      {{ operationError }}
    </p>

    <TargetTable
      :can-write="canWrite"
      :error="error"
      :loading="isPending"
      :targets="targets"
      @create="openCreate"
      @delete="removeTarget"
      @edit="openEdit"
      @retry="refetch"
      @toggle="toggleTarget"
    />

    <TargetFormDialog
      v-model="dialogOpen"
      :server-error="formError"
      :submitting="submitting"
      :target="editingTarget"
      :versions="versions"
      :versions-loading="versionsQuery.isPending.value"
      @submit="submitTarget"
    />
  </section>
</template>

<style scoped>
.target-config-page {
  display: grid;
  min-width: 0;
  gap: 16px;
  padding: 8px 0 24px;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--purple);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

h1 {
  margin: 0;
  color: var(--text);
  font-size: var(--font-title);
  font-weight: 650;
}

.operation-error {
  margin: 0;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--red) 35%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  color: var(--red);
  font-size: 11.5px;
}

.lede {
  max-width: 680px;
  margin: 7px 0 0;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 640px) {
  .target-config-page {
    padding-top: 2px;
  }
}
</style>
