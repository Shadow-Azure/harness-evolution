<script setup lang="ts">
defineProps<{ badge?: boolean }>();
</script>

<template>
  <span
    v-if="badge"
    class="runtime-badge"
  >归因未运行</span>
  <p
    v-else
    class="runtime-notice"
    role="status"
  >
    <strong>归因运行时不可用。</strong>
    已保存的绑定会保留。请管理员检查公共 AI Agent Provider 的 Skill 能力，以及 Linux 服务账号的 bubblewrap 沙箱。需要使用单条证据工具时，请在服务端 .env 显式设置 HE_ATTRIBUTION_BWRAP_ENABLED=false。重启并通过预检后，后台会继续处理原批次。
  </p>
</template>

<style scoped>
.runtime-notice {
  margin: 0;
  padding: var(--space-sm) var(--space-md);
  border-left: 3px solid var(--orange);
  background: var(--surface-raised);
  color: var(--text-secondary);
  line-height: 1.5;
}
.runtime-notice strong { color: var(--text-primary); }
.runtime-badge {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--orange);
  border-radius: var(--radius-pill);
  color: var(--text-primary);
  font-size: 11px;
  white-space: nowrap;
}
</style>
