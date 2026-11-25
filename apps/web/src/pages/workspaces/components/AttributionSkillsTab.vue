<script setup lang="ts">
import type { AttributionSkillPackage } from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { useQuery } from "@tanstack/vue-query";
import { getSkillResource } from "../../../api/attributionSkillPackages";
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
const selectedId = ref("");
const selected = computed(() => items.value.find(item => item.id === selectedId.value) ?? items.value[0]);
const detail = useQuery({
  queryKey: computed(() => ["skill-resource", props.workspaceId, selected.value?.id]),
  queryFn: () => getSkillResource(props.workspaceId, selected.value!.id),
  enabled: computed(() => Boolean(selected.value)),
});

const directoryTree = computed(() => {
  const lines: string[] = [];
  let previous: string[] = [];
  for (const path of detail.data.value?.files ?? []) {
    const parts = path.split("/");
    let depth = 0;
    while (depth < parts.length && previous[depth] === parts[depth]) depth++;
    for (; depth < parts.length; depth++) {
      lines.push("  ".repeat(depth) + parts[depth] + (depth < parts.length - 1 ? "/" : ""));
    }
    previous = parts;
  }
  return lines.join("\n");
});

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
    selectedId.value = (await manager.upload(file)).id;
    ElMessage.success("归因 Skill 已上传，可在进化对象中选择。");
  } catch (error) {
    operationError.value = packageErrorMessage(error, "上传失败");
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
      `删除 ${item.skillName} 及其服务器文件？`,
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
        if ("status" in error && error.status === 409) return "请先更改已绑定对象的归因 Skill，再删除此包。";
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
          上传归因 Skill 后，可在进化对象配置中绑定，或在启动自进化时选择。
        </p>
      </div>
      <button
        v-if="canManage"
        class="btn primary"
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
      <section>
        <div class="list-heading">
          <div>
            <h3>已上传归因 Skill</h3>
            <p>{{ items.length }} 个包；默认包始终可用且不可删除。</p>
          </div>
          <span
            v-if="!canManage"
            class="badge"
          >只读</span>
        </div>
        <div class="table-scroll">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Skill 名</th>
                <th>上传者</th>
                <th>文件数</th>
                <th>大小</th>
                <th>资源详情</th>
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
                    <span
                      v-if="item.builtIn"
                      class="badge"
                    >平台默认</span>
                  </div>
                </td>
                <td>{{ item.uploaderName }}</td>
                <td>{{ item.fileCount }}</td>
                <td>{{ formatBytes(item.sizeBytes) }}</td>
                <td>
                  <button
                    type="button"
                    class="btn small"
                    :aria-pressed="selected?.id === item.id"
                    @click="selectedId = item.id"
                  >
                    查看详情
                  </button>
                </td>
                <td class="operations">
                  <button
                    class="btn small"
                    type="button"
                    :data-testid="`download-skill-${item.id}`"
                    @click="download(item)"
                  >
                    下载
                  </button>
                  <button
                    v-if="canManage && !item.builtIn"
                    class="btn small danger"
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
        v-if="selected"
        class="skill-detail"
        data-testid="effective-skill-prompt"
      >
        <h3>{{ selected.skillName }}</h3>
        <p v-if="detail.isPending.value">
          正在读取资源详情…
        </p>
        <ErrorState
          v-else-if="detail.isError.value"
          message="无法读取资源详情"
          @retry="detail.refetch()"
        />
        <template v-else-if="detail.data.value">
          <div class="detail-grid">
            <div>
              <h4>已绑定进化对象</h4>
              <p>{{ detail.data.value.targets.join("、") || "暂无绑定对象" }}</p>
            </div>
            <div>
              <h4>目录结构</h4>
              <pre
                data-testid="skill-directory-tree"
                tabindex="0"
              >{{ directoryTree }}</pre>
            </div>
          </div>
          <h4>SKILL.md</h4>
          <pre
            data-testid="skill-resource-prompt"
            tabindex="0"
          >{{ detail.data.value.prompt }}</pre>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.admin-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}

.admin-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

.admin-head .sub {
  margin: 2px 0 0;
}

.admin-head .sub,
.upload-help,
.list-heading p {
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}

.upload-help {
  margin: 0 0 12px;
}

.hidden-input {
  display: none;
}

.operation-error {
  margin: 0 0 12px;
  padding: 8px 10px;
  border: 1px solid var(--state-error-border);
  border-radius: 8px;
  color: var(--state-error-text);
  background: var(--state-error-surface);
  font-size: 11px;
}

.list-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.list-heading h3,
.skill-detail h3 {
  margin: 0;
  color: var(--text);
  font-size: 12px;
  font-weight: 650;
}

.list-heading p {
  margin: 0;
}

.badge {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  background: var(--bg-card);
  font-size: 9.5px;
  white-space: nowrap;
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

.admin-table .operations {
  text-align: right;
  white-space: nowrap;
}

.operations button + button {
  margin-left: 4px;
}

.skill-name {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.skill-name strong,
code {
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

.btn:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--text);
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: var(--text-on-accent);
  font-weight: 600;
}

.btn.primary:hover:not(:disabled) {
  background: var(--blue-deep);
  color: var(--text-on-accent);
}

.btn.small {
  padding: 3px 10px;
}

.btn[aria-pressed="true"] {
  border-color: color-mix(in srgb, var(--blue) 35%, var(--border));
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
  color: var(--blue);
}

.btn.danger,
.btn.danger:hover:not(:disabled) {
  color: var(--red);
}

.btn:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.skill-detail {
  min-width: 0;
  margin-top: 14px;
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: 12px;
  margin: 12px 0;
}

.skill-detail h4 {
  margin: 0;
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 650;
}

.skill-detail p {
  margin: 4px 0 0;
  color: var(--text-dim);
  font-size: 11.5px;
  overflow-wrap: anywhere;
}

.skill-detail pre {
  max-height: 520px;
  margin: 5px 0 0;
  padding: 9px 11px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font: 11px/1.7 var(--mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
