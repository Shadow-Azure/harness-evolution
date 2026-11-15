<script setup lang="ts">
import type {
  Workspace,
  WorkspaceCredential,
  WorkspaceCredentialCreated,
} from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { computed, ref } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import {
  ingestExampleBody,
  ingestExampleCurl,
  useWorkspaceCredentialMutations,
  useWorkspaceCredentials,
} from "../../../composables/useWorkspaces";
import { workspaceQuotaPercent } from "../../../utils/workspaceDisplay";

const props = withDefaults(
  defineProps<{
    workspaceId: string;
    workspace?: Workspace | null;
    canManage: boolean;
  }>(),
  {
    workspace: null,
  },
);

const credentialsQuery = useWorkspaceCredentials(
  () => props.workspaceId,
  () => props.canManage,
);
const mutations = useWorkspaceCredentialMutations(() => props.workspaceId);

const createdCredential = ref<WorkspaceCredentialCreated | null>(null);
const operationError = ref("");

const endpoint = computed(() => {
  const origin =
    typeof globalThis.location === "object" && globalThis.location
      ? globalThis.location.origin
      : "";
  return `${origin}/api/workspaces/${encodeURIComponent(props.workspaceId)}/bad-cases`;
});
const credentials = computed<WorkspaceCredential[]>(
  () => credentialsQuery.data.value?.items ?? [],
);
const activeCredentials = computed(() =>
  credentials.value.filter((credential) => credential.revokedAt === null),
);
const used = computed(() => props.workspace?.used ?? 0);
const quota = computed(() => props.workspace?.quota ?? 0);
const quotaPercent = computed(() =>
  workspaceQuotaPercent(used.value, quota.value),
);
const bodyExample = computed(ingestExampleBody);
const curlExample = computed(() =>
  ingestExampleCurl(
    endpoint.value,
    createdCredential.value?.credential ?? "<workspace credential>",
  ),
);

async function rotateCredential(): Promise<void> {
  if (!props.canManage) return;
  operationError.value = "";
  try {
    createdCredential.value = await mutations.createCredential();
  } catch (error) {
    operationError.value = credentialErrorMessage(error, "生成凭据失败");
  }
}

async function revokeCredential(credential: WorkspaceCredential): Promise<void> {
  operationError.value = "";
  try {
    await ElMessageBox.confirm(
      `撤销凭据 ${credential.prefix}… 后，上游使用它的上报会立即失败。`,
      "撤销上报凭据",
      {
        type: "warning",
        confirmButtonText: "撤销",
        cancelButtonText: "取消",
      },
    );
  } catch {
    return;
  }
  try {
    await mutations.revokeCredential(credential.id);
    ElMessage.success("凭据已撤销");
  } catch (error) {
    operationError.value = credentialErrorMessage(error, "撤销凭据失败");
  }
}

function closeCredentialDialog(): void {
  createdCredential.value = null;
}

async function copyText(value: string, message: string): Promise<void> {
  try {
    await globalThis.navigator?.clipboard?.writeText(value);
    ElMessage.success(message);
  } catch {
    ElMessage.warning("浏览器未授权剪贴板，请手动选择复制。");
  }
}

function credentialErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "code" in error) {
    switch (String(error.code)) {
      case "CREDENTIAL_LIMIT":
        return "最多保留 3 个有效凭据，请先撤销不再使用的凭据。";
      case "CREDENTIAL_NOT_FOUND":
        return "凭据不存在或已被删除。";
      case "WORKSPACE_FORBIDDEN":
        return "当前角色没有管理凭据的权限。";
      default:
        break;
    }
  }
  return `${fallback}，请稍后重试。`;
}

function formatTime(value: string | null): string {
  return value ? value.slice(0, 16).replace("T", " ") : "—";
}
</script>

<template>
  <div data-testid="ingest-tab">
    <div class="admin-head">
      <div>
        <h2>bad case 上报接入</h2>
        <p class="sub">
          每个空间有独立的上报地址与凭据；请求体沿用 bad case 契约，空间身份不信任 body。
        </p>
      </div>
      <div
        v-if="canManage"
        class="actions"
      >
        <button
          class="btn"
          data-testid="rotate-credential"
          :disabled="mutations.isCreating.value"
          type="button"
          @click="rotateCredential"
        >
          {{ mutations.isCreating.value ? "生成中…" : "重新生成凭据" }}
        </button>
      </div>
    </div>

    <p
      v-if="operationError"
      class="operation-error"
      role="alert"
      data-testid="ingest-operation-error"
    >
      {{ operationError }}
    </p>

    <div class="ingest-card">
      <h3>上报地址 <span class="badge ok">已启用</span></h3>
      <div class="ingest-endpoint">
        <span class="method">POST</span>
        <span
          class="url"
          data-testid="ingest-endpoint"
        >{{ endpoint }}</span>
        <button
          class="btn small"
          type="button"
          @click="copyText(endpoint, '上报地址已复制')"
        >
          复制
        </button>
      </div>
      <p class="field-help">
        服务端从 URL 解析 workspace，再校验 <code>Authorization</code> 凭据；body 不接受 workspace 字段，多带会返回 <code>422</code>。
      </p>
    </div>

    <div
      v-if="!canManage"
      class="ingest-card readonly-card"
      data-testid="ingest-readonly"
    >
      <h3>空间凭据</h3>
      <p class="field-help">
        只有空间管理员及以上可以查看与轮换上报凭据；当前角色为只读。
      </p>
    </div>

    <template v-else>
      <LoadingSkeleton
        v-if="credentialsQuery.isPending.value"
        label="正在读取上报凭据"
        :rows="2"
      />
      <ErrorState
        v-else-if="credentialsQuery.error.value"
        code="WORKSPACE_CREDENTIALS_UNAVAILABLE"
        message="上报凭据读取失败，请重试。"
        @retry="credentialsQuery.refetch"
      />
      <div
        v-else
        class="ingest-card"
      >
        <h3>空间凭据 <span class="badge">{{ activeCredentials.length }} 个有效</span></h3>
        <div
          v-if="credentials.length === 0"
          class="empty-credentials"
          data-testid="no-credentials"
        >
          还没有凭据。点击「重新生成凭据」创建第一条；明文只在创建时展示一次。
        </div>
        <div
          v-else
          class="table-scroll"
        >
          <table class="admin-table">
            <thead>
              <tr>
                <th>前缀</th>
                <th>创建时间</th>
                <th>最近使用</th>
                <th>状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="credential in credentials"
                :key="credential.id"
                :data-testid="`credential-row-${credential.id}`"
              >
                <td class="mono">
                  {{ credential.prefix }}…
                </td>
                <td class="mono">
                  {{ formatTime(credential.createdAt) }}
                </td>
                <td class="mono">
                  {{ formatTime(credential.lastUsedAt) }}
                </td>
                <td>
                  <span
                    class="badge"
                    :class="credential.revokedAt ? 'muted' : 'ok'"
                  >
                    {{ credential.revokedAt ? "已撤销" : "有效" }}
                  </span>
                </td>
                <td class="row-actions">
                  <button
                    v-if="!credential.revokedAt"
                    class="link danger"
                    type="button"
                    @click="revokeCredential(credential)"
                  >
                    撤销
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="field-help">
          服务端只保存摘要；轮换后旧凭据立即失效，切换窗口内新旧凭据可短暂并存（最多 3 个有效）。
        </p>
      </div>
    </template>

    <div class="ingest-grid">
      <div class="ingest-card">
        <h3>额度</h3>
        <div class="qc-v">
          {{ used }} <span>/ {{ quota }}</span>
        </div>
        <div
          class="ws-quota-bar"
          :class="{ hot: quotaPercent > 80 }"
        >
          <span :style="{ width: `${quotaPercent}%` }" />
        </div>
        <p class="field-help">
          达到上限时写入返回 <code>409 QUOTA_EXCEEDED</code>，不自动丢弃旧数据。
        </p>
      </div>
      <div class="ingest-card">
        <h3>接入检查</h3>
        <ul class="check-list">
          <li>凭据明文只展示一次，关闭后不可再次读取。</li>
          <li>空间身份只从 URL 与服务端凭据解析。</li>
          <li>成员与只读角色不能查看或轮换凭据。</li>
        </ul>
      </div>
    </div>

    <div class="ingest-card">
      <h3>请求体示例（bad case 契约）</h3>
      <pre
        class="codebox"
        data-testid="ingest-body-example"
      >{{ bodyExample }}</pre>
    </div>

    <div class="ingest-card">
      <h3>curl 示例</h3>
      <pre
        class="codebox"
        data-testid="ingest-curl-example"
      >{{ curlExample }}</pre>
    </div>

    <ElDialog
      :model-value="createdCredential !== null"
      :show-close="false"
      :teleported="false"
      destroy-on-close
      title="凭据已生成"
      width="min(560px, calc(100vw - 32px))"
      @close="closeCredentialDialog"
    >
      <div
        v-if="createdCredential"
        data-testid="one-time-credential"
      >
        <p class="credential-warning">
          明文只展示这一次。关闭后无法再次读取；请立即复制并保存到安全位置。
        </p>
        <div class="credential-secret">
          <code data-testid="new-credential-plaintext">{{ createdCredential.credential }}</code>
          <button
            class="btn small"
            type="button"
            @click="copyText(createdCredential.credential, '凭据已复制')"
          >
            复制
          </button>
        </div>
        <p class="field-help">
          前缀 <span class="mono">{{ createdCredential.prefix }}…</span>；上游切换完成后，可在列表中撤销旧凭据。
        </p>
      </div>
      <template #footer>
        <footer
          v-if="createdCredential"
          class="form-actions"
        >
          <button
            class="btn primary"
            data-testid="acknowledge-credential"
            type="button"
            @click="closeCredentialDialog"
          >
            我已保存
          </button>
        </footer>
      </template>
    </ElDialog>
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

.ingest-card {
  margin-bottom: 12px;
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
}

.ingest-card h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 6px;
  color: var(--text-dim);
  font-size: 11.5px;
  font-weight: 650;
}

.ingest-endpoint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10.5px;
}

.ingest-endpoint .method {
  flex-shrink: 0;
  color: var(--green);
  font-weight: 700;
}

.ingest-endpoint .url {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.codebox {
  max-height: 260px;
  margin: 8px 0 0;
  padding: 9px 11px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.ingest-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.qc-v {
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

.field-help {
  margin: 6px 0 0;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.badge {
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 9.5px;
  font-weight: 400;
  white-space: nowrap;
}

.badge.ok {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  background: color-mix(in srgb, var(--green) 9%, transparent);
  color: var(--green);
}

.badge.muted {
  color: var(--text-faint);
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
  padding: 8px 9px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

.admin-table th {
  background: var(--bg-card);
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 650;
  white-space: nowrap;
}

.admin-table tr:last-child td {
  border-bottom: none;
}

.row-actions {
  text-align: right;
  white-space: nowrap;
}

.empty-credentials {
  padding: 14px;
  border: 1px dashed var(--border);
  border-radius: 8px;
  color: var(--text-faint);
  font-size: 11px;
}

.check-list {
  margin: 0;
  padding-left: 16px;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.7;
}

.credential-warning {
  margin: 0 0 10px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--orange) 35%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--orange) 8%, var(--bg-card));
  color: var(--orange);
  font-size: 11px;
}

.credential-secret {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-inset);
}

.credential-secret code {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text);
  font-family: var(--mono);
  font-size: 11px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
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

.btn.small {
  padding: 3px 8px;
  font-size: 11px;
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

.mono {
  font-family: var(--mono);
}

@media (max-width: 980px) {
  .ingest-grid {
    grid-template-columns: 1fr;
  }
}
</style>
