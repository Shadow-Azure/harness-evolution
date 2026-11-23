<script setup lang="ts">
import type { EvolutionRunControl } from "@harness/contracts";
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";

import { pauseEvolutionRun, resumeEvolutionRun } from "../../../api/evolutionRuns";
import { queryKeys } from "../../../api/queryKeys";
import { formatApiError } from "../../../app/apiError";

const props = defineProps<{
  wid: string;
  run: EvolutionRunControl;
  canManage: boolean;
}>();
const queryClient = useQueryClient();
const pending = ref(false);
const error = ref("");
const accepted = ref<EvolutionRunControl | null>(null);
const control = computed(() => accepted.value ?? props.run);
watch(
  () => [props.wid, props.run.runId, props.run.controlState, props.run.pausedAt,
    props.run.pauseRequestedAt, props.run.canPause, props.run.canResume],
  () => { accepted.value = null; error.value = ""; },
);

async function changeControl(): Promise<void> {
  if (pending.value || !props.canManage) return;
  const resume = control.value.canResume;
  if (!resume && !control.value.canPause) return;
  pending.value = true;
  error.value = "";
  const wid = props.wid;
  const runId = props.run.runId;
  try {
    const response = await (resume ? resumeEvolutionRun : pauseEvolutionRun)(wid, runId);
    if (props.wid === wid && props.run.runId === runId) accepted.value = response;
  } catch (cause) {
    if (props.wid === wid && props.run.runId === runId) {
      error.value = formatApiError(cause, resume ? "继续执行失败" : "暂停请求失败").message;
    }
  } finally {
    pending.value = false;
    void queryClient.invalidateQueries({ queryKey: queryKeys.evolutionRuns(wid) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.evolutionRun(wid, runId) });
  }
}
</script>

<template>
  <div
    class="run-control"
    @click.stop
    @keydown.stop
  >
    <span
      v-if="control.controlState === 'pause_requested'"
      class="control-note"
      role="status"
    >
      暂停中 · 等待当前操作结束
    </span>
    <span
      v-else-if="control.controlState === 'paused'"
      class="control-note"
      role="status"
    >
      已暂停 · 进度已保留，已提交的外部评测可能继续运行
    </span>
    <button
      v-if="canManage && (control.canPause || control.canResume || control.controlState === 'pause_requested')"
      type="button"
      class="control-button"
      :class="{ primary: control.canResume }"
      :disabled="pending || control.controlState === 'pause_requested'"
      :aria-busy="pending"
      @click="changeControl"
    >
      {{ pending ? '提交中…' : control.canResume ? '继续执行' : control.controlState === 'pause_requested' ? '暂停中…' : '暂停' }}
    </button>
    <span
      v-if="error"
      class="control-error"
      role="alert"
    >{{ error }}</span>
  </div>
</template>

<style scoped>
.run-control { position: relative; z-index: 2; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; pointer-events: auto; }
.control-note { color: var(--text-muted); font-size: 12px; }
.control-button { border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; background: var(--bg-card); color: var(--text); font: inherit; font-size: 12px; cursor: pointer; }
.control-button.primary { background: var(--blue); color: var(--text-on-accent); border-color: var(--blue); }
.control-button:disabled { cursor: default; opacity: 0.6; }
.control-button:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
.control-error { flex-basis: 100%; color: var(--red); font-size: 12px; }
</style>
