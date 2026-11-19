<script setup lang="ts">
import type { AttributionSkillPackage } from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { computed, ref } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { useAttributionSkillPackages } from "../../../composables/useAttributionSkillPackages";

const props = defineProps<{
  workspaceId: string;
  canManage: boolean;
}>();

const manager = useAttributionSkillPackages(() => props.workspaceId);
const fileInput = ref<HTMLInputElement | null>(null);
const operationError = ref("");
const items = computed(() => manager.packages.data.value?.items ?? []);
const effective = computed(() => manager.packages.data.value?.effective);

function openUpload(): void {
  if (!props.canManage || manager.isMutating.value) return;
  fileInput.value?.click();
}

async function handleUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".zip")) {
    operationError.value = "请选择 ZIP 格式的 Skill 文件夹压缩包。";
    return;
  }
  operationError.value = "";
  try {
    await manager.upload(file);
    ElMessage.success("归因 Skill 已上传，可手动设为生效。");
  } catch (error) {
    operationError.value = packageErrorMessage(error, "上传失败");
  }
}

async function activate(item: AttributionSkillPackage): Promise<void> {
  if (!props.canManage || item.isActive) return;
  operationError.value = "";
  try {
    await manager.activate(item.id);
    ElMessage.success(`已启用 ${item.skillName}`);
  } catch (error) {
    operationError.value = packageErrorMessage(error, "切换失败");
  }
}

async function download(item: AttributionSkillPackage): Promise<void> {
  operationError.value = "";
  try {
    const blob = await manager.download(item.id);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${item.skillName}.zip`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    operationError.value = packageErrorMessage(error, "下载失败");
  }
}

async function remove(item: AttributionSkillPackage): Promise<void> {
  if (!props.canManage || item.builtIn) return;
  try {
    await ElMessageBox.confirm(
      item.isActive
        ? `删除当前生效的 ${item.skillName} 后将立即回退默认 Skill。`
        : `删除 ${item.skillName} 及其服务器文件？`,
      "删除归因 Skill",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  operationError.value = "";
  try {
    await manager.remove(item.id);
    ElMessage.success("归因 Skill 已删除");
  } catch (error) {
    operationError.value = packageErrorMessage(error, "删除失败");
  }
}

function packageErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "code" in error) {
    switch (String(error.code)) {
      case "ATTRIBUTION_SKILL_PACKAGE_EXISTS":
        return "当前空间已存在同名 Skill，请先删除旧包或修改 SKILL.md 的 name。";
      case "ATTRIBUTION_SKILL_PACKAGE_TOO_LARGE":
        return "压缩包超过限制，请检查 ZIP 大小、解压大小、文件数和 SKILL.md 大小。";
      case "ATTRIBUTION_SKILL_PACKAGE_INVALID":
        return "压缩包不合法：需要且只能包含一个 UTF-8 SKILL.md，并提供合法 name。";
      case "ATTRIBUTION_SKILL_PACKAGE_NOT_FOUND":
        return "该 Skill 已不存在，请刷新列表。";
      case "WORKSPACE_FORBIDDEN":
        return "当前角色没有管理归因 Skill 的权限。";
      default:
        break;
    }
  }
  return `${fallback}，请稍后重试。`;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}
</script>

<template>
  <div
    class="skill-tab"
    data-testid="attribution-skills-tab"
  >
    <div class="admin-head">
      <div>
        <h2>自定义归因 Skill</h2>
        <p class="sub">
          管理当前空间的归因提示词包。上传不会自动生效，也不会绕过生产 Run 的质量门禁。
        </p>
      </div>
      <button
        v-if="canManage"
        class="primary-button"
        data-testid="upload-attribution-skill"
        :disabled="manager.isMutating.value"
        type="button"
        @click="openUpload"
      >
        {{ manager.isMutating.value ? "处理中…" : "上传自定义归因 Skill" }}
      </button>
      <input
        ref="fileInput"
        class="hidden-input"
        data-testid="attribution-skill-file"
        type="file"
        accept=".zip,application/zip"
        @change="handleUpload"
      >
    </div>

    <p class="upload-help">
      上传 Skill 文件夹的 ZIP 包。最多 200 个文件，ZIP 不超过 10 MiB，解压后不超过 20 MiB。包内须有一个不超过 512 KiB 的 <code>SKILL.md</code>。
    </p>
    <p
      v-if="operationError"
      class="operation-error"
      role="alert"
      data-testid="skill-operation-error"
    >
      {{ operationError }}
    </p>

    <LoadingSkeleton
      v-if="manager.packages.isPending.value"
      label="正在读取归因 Skill"
      :rows="3"
    />
    <ErrorState
      v-else-if="manager.packages.error.value"
      code="ATTRIBUTION_SKILL_PACKAGES_UNAVAILABLE"
      message="归因 Skill 列表读取失败，请重试。"
      @retry="manager.packages.refetch"
    />
    <template v-else>
      <section class="panel">
        <div class="section-heading">
          <div>
            <h3>已上传归因 Skill</h3>
            <p>{{ items.length }} 个包；默认包始终可用且不可删除。</p>
          </div>
          <span
            v-if="!canManage"
            class="readonly-badge"
          >只读</span>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Skill 名</th>
                <th>上传者</th>
                <th>文件数</th>
                <th>大小</th>
                <th>生效状态</th>
                <th class="operations">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in items"
                :key="item.id"
                :data-testid="`skill-package-${item.id}`"
              >
                <td>
                  <div class="skill-name">
                    <strong>{{ item.skillName }}</strong>
                    <span v-if="item.builtIn">平台默认</span>
                  </div>
                </td>
                <td>{{ item.uploaderName }}</td>
                <td>{{ item.fileCount }}</td>
                <td>{{ formatBytes(item.sizeBytes) }}</td>
                <td>
                  <span
                    class="status"
                    :class="item.isActive ? 'active' : 'inactive'"
                  >{{ item.isActive ? "当前生效" : "未生效" }}</span>
                </td>
                <td class="operations">
                  <button
                    v-if="canManage && !item.isActive"
                    class="text-button emphasize"
                    :disabled="manager.isMutating.value"
                    type="button"
                    :data-testid="`activate-skill-${item.id}`"
                    @click="activate(item)"
                  >
                    设为生效
                  </button>
                  <button
                    class="text-button"
                    type="button"
                    :data-testid="`download-skill-${item.id}`"
                    @click="download(item)"
                  >
                    下载
                  </button>
                  <button
                    v-if="canManage && !item.builtIn"
                    class="text-button danger"
                    :disabled="manager.isMutating.value"
                    type="button"
                    :data-testid="`delete-skill-${item.id}`"
                    @click="remove(item)"
                  >
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section
        v-if="effective"
        class="panel prompt-panel"
        data-testid="effective-skill-prompt"
      >
        <div class="section-heading">
          <div>
            <h3>当前生效的归因 Skill 提示词</h3>
            <p><strong>{{ effective.skillName }}</strong> · SKILL.md 原文</p>
          </div>
          <span class="status active">当前生效</span>
        </div>
        <pre>{{ effective.prompt }}</pre>
      </section>
    </template>
  </div>
</template>

<style scoped>
.skill-tab { display: grid; gap: 16px; }
.admin-head, .section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
h2, h3, p { margin: 0; }
h2 { color: var(--text); font-size: 18px; }
h3 { color: var(--text); font-size: 15px; }
.sub, .upload-help, .section-heading p { margin-top: 6px; color: var(--text-dim); font-size: 13px; line-height: 1.6; }
.upload-help { padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-inset); }
.hidden-input { display: none; }
.primary-button { flex: 0 0 auto; min-height: 36px; padding: 0 16px; border: 1px solid var(--blue); border-radius: 8px; color: var(--text-on-accent); background: var(--blue); cursor: pointer; font-weight: 650; }
.primary-button:disabled, .text-button:disabled { cursor: not-allowed; opacity: .55; }
.operation-error { padding: 10px 12px; border: 1px solid var(--state-error-border); border-radius: 8px; color: var(--state-error-text); background: var(--state-error-surface); font-size: 13px; }
.panel { overflow: hidden; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); }
.section-heading { padding: 16px 18px; border-bottom: 1px solid var(--border); }
.readonly-badge, .status, .skill-name span { display: inline-flex; align-items: center; min-height: 22px; padding: 0 8px; border-radius: 999px; font-size: 12px; white-space: nowrap; }
.readonly-badge, .status.inactive, .skill-name span { color: var(--text-dim); background: var(--bg-inset); }
.status.active { color: var(--state-success-text); background: var(--state-success-surface); }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 10px 14px; color: var(--text-dim); background: var(--bg-inset); text-align: left; font-weight: 600; white-space: nowrap; }
td { padding: 13px 14px; border-top: 1px solid var(--border); color: var(--text-dim); }
.skill-name { display: flex; align-items: center; gap: 8px; min-width: 190px; }
.skill-name strong { color: var(--text); font-family: var(--mono); }
.operations { text-align: right; white-space: nowrap; }
.text-button { padding: 4px 7px; border: 0; color: var(--text-dim); background: transparent; cursor: pointer; }
.text-button:hover { color: var(--text); }
.text-button.emphasize { color: var(--blue); }
.text-button.danger { color: var(--red); }
.prompt-panel pre { max-height: 520px; margin: 0; padding: 18px; overflow: auto; color: var(--text-dim); background: var(--bg-inset); font-family: var(--mono); font-size: 12px; line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
code { font-family: var(--mono); }
@media (max-width: 760px) { .admin-head { flex-direction: column; } .primary-button { width: 100%; } }
</style>
