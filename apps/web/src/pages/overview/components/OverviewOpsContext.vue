<script setup lang="ts">
import type { OverviewTotals, SessionWorkspace } from "@harness/contracts";
import { computed, onBeforeUnmount, ref } from "vue";

import { workspacePath } from "../../../router/workspace";
import {
  workspaceQuotaPercent,
  workspaceRoleLabel,
} from "../../../utils/workspaceDisplay";

const props = defineProps<{
  workspaceId: string;
  workspace: SessionWorkspace | null;
  totals: OverviewTotals | null;
  canManage: boolean;
}>();

const endpoint = computed(
  () => `/api/workspaces/${encodeURIComponent(props.workspaceId)}/bad-cases`,
);
const used = computed(() => props.totals?.used ?? null);
const quota = computed(() => props.totals?.quota ?? null);
const percent = computed(() =>
  used.value === null || quota.value === null
    ? 0
    : workspaceQuotaPercent(used.value, quota.value),
);
const remaining = computed(() =>
  used.value === null || quota.value === null
    ? null
    : Math.max(0, quota.value - used.value),
);
const hot = computed(() => percent.value > 80);
const roleLabel = computed(() =>
  props.workspace ? workspaceRoleLabel(props.workspace.role) : "—",
);
const ingestPath = computed(() =>
  workspacePath(props.workspaceId, "admin"),
);

const copyState = ref<"idle" | "copied" | "failed">("idle");
let resetTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * Copy the workspace ingest endpoint without exposing any credential.
 * @returns A promise resolved after the button state is updated.
 */
async function copyEndpoint(): Promise<void> {
  try {
    if (!navigator.clipboard?.writeText) {
      throw new Error("clipboard unavailable");
    }
    await navigator.clipboard.writeText(endpoint.value);
    copyState.value = "copied";
  } catch {
    copyState.value = "failed";
  }
  if (resetTimer) clearTimeout(resetTimer);
  resetTimer = setTimeout(() => {
    copyState.value = "idle";
  }, 2_000);
}

onBeforeUnmount(() => {
  if (resetTimer) clearTimeout(resetTimer);
});
</script>

<template>
  <aside
    class="ov-side card"
    aria-label="运营上下文"
    data-testid="ov-context"
  >
    <section class="side-sec">
      <h3>空间额度</h3>
      <div class="kv">
        <span class="k">已上报</span>
        <span
          class="v"
          data-testid="ov-context-quota-used"
        ><b>{{ used ?? "—" }}</b> / {{ quota ?? "—" }}</span>
      </div>
      <div class="quota-bar">
        <div
          class="fill"
          :class="{ hot }"
          :style="{ width: `${percent}%` }"
        />
      </div>
      <div class="meta">
        <span data-testid="ov-context-quota-percent">{{ percent }}% 已使用</span>
        <span data-testid="ov-context-quota-remaining">剩余 {{ remaining ?? "—" }}</span>
      </div>
      <p class="note">
        额度在创建空间时设置，空间管理员可随时调整；写入事务内校验。
      </p>
    </section>

    <section class="side-sec">
      <h3>上报接入</h3>
      <div
        class="endpoint"
        data-testid="ov-context-endpoint"
      >
        <span class="method">POST</span>
        <code>{{ endpoint }}</code>
      </div>
      <div class="actions">
        <button
          class="sm-btn"
          data-testid="ov-context-copy"
          type="button"
          @click="copyEndpoint"
        >
          {{ copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制地址" }}
        </button>
        <RouterLink
          v-if="canManage"
          class="sm-btn"
          data-testid="ov-context-ingest-link"
          :to="{ path: ingestPath, query: { tab: 'ingest' } }"
        >
          查看请求示例 →
        </RouterLink>
      </div>
      <p class="note">
        请求体沿用 <b>bad_cases</b> 表类型；空间身份由 URL 与服务端凭据确定。
      </p>
    </section>

    <section class="side-sec">
      <h3>当前空间</h3>
      <div class="kv">
        <span class="k">空间管理员</span>
        <span
          class="v"
          data-testid="ov-context-admin-count"
        ><b>{{ workspace?.spaceAdminCount ?? "—" }}</b> 人</span>
      </div>
      <div class="kv">
        <span class="k">成员</span>
        <span
          class="v"
          data-testid="ov-context-member-count"
        ><b>{{ workspace?.memberCount ?? "—" }}</b> 人</span>
      </div>
      <div class="kv">
        <span class="k">我的角色</span>
        <span
          class="v"
          data-testid="ov-context-role"
        ><span class="badge">{{ roleLabel }}</span></span>
      </div>
      <div class="kv">
        <span class="k">上报来源</span>
        <span
          class="v"
          data-testid="ov-context-sources"
        ><b>{{ totals?.sources ?? "—" }}</b> 个</span>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.ov-side {
  padding: 4px 15px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.side-sec {
  padding: 12px 0;
  border-top: 1px solid var(--border);
}

.side-sec:first-child {
  border-top: 0;
}

.side-sec h3 {
  margin: 0 0 9px;
  color: var(--text);
  font-size: 12.5px;
  font-weight: 650;
}

.kv {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 11px;
}

.kv .k {
  color: var(--text-faint);
  white-space: nowrap;
}

.kv .v {
  overflow: hidden;
  color: var(--text-dim);
  font-family: var(--mono);
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kv .v b {
  color: var(--text);
  font-weight: 650;
}

.quota-bar {
  height: 6px;
  margin: 7px 0 5px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--bg-inset);
}

.quota-bar .fill {
  height: 100%;
  border-radius: 4px;
  background: var(--blue);
}

.quota-bar .fill.hot {
  background: var(--red);
}

.meta {
  display: flex;
  justify-content: space-between;
  color: var(--text-faint);
  font-size: 10px;
}

.endpoint {
  display: flex;
  gap: 7px;
  align-items: center;
  padding: 7px 9px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
}

.endpoint .method {
  flex-shrink: 0;
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--blue) 12%, var(--bg-card));
  color: var(--blue);
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 650;
}

.endpoint code {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  white-space: normal;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 7px;
}

.sm-btn {
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10px;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
}

.sm-btn:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.note {
  margin: 7px 0 0;
  color: var(--text-faint);
  font-size: 9.5px;
  line-height: 1.6;
}

.badge {
  display: inline-block;
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font-family: inherit;
  font-size: 10px;
}
</style>
