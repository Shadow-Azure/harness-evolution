<script setup lang="ts">
import type { BadCase, SessionTree } from "@harness/contracts";
import { computed, nextTick, onErrorCaptured, ref, watch } from "vue";

import LaneDag from "./lane/LaneDag.vue";
import { buildLaneModel } from "./lane/laneModel";
import AgentTree from "./tree/AgentTree.vue";

defineOptions({ name: "AgentFlow" });

type FlowMode = "dag" | "tree";

const props = withDefaults(
  defineProps<{
    tree: SessionTree;
    expanded?: string[];
    activeAgentId?: string | null;
    activeEventIndex?: number | null;
    problems?: BadCase[];
    activeBadCaseId?: string | null;
    dagHeight?: string;
    treeHeight?: string;
    defaultMode?: FlowMode;
  }>(),
  {
    expanded: () => [],
    activeAgentId: null,
    activeEventIndex: null,
    problems: () => [],
    activeBadCaseId: null,
    dagHeight: "clamp(360px, 48vh, 520px)",
    treeHeight: "720px",
    defaultMode: "dag",
  },
);

const emit = defineEmits<{
  "toggle-expanded": [agentId: string];
  "node-select": [agentId: string];
  "badcase-select": [badCaseId: string];
  "collapse-all": [];
}>();

const mode = ref<FlowMode>(props.defaultMode);
const laneDagRef = ref<{
  locateBadCase: (badCaseId: string) => void;
  locateLane: (agentId: string) => void;
  fit: () => void;
  reset: () => void;
} | null>(null);
const treeRef = ref<{
  locateBadCase: (badCaseId: string) => Promise<void>;
  locateAgent: (agentId: string) => void;
} | null>(null);
const laneError = ref<string | null>(null);

const laneModel = computed(() =>
  buildLaneModel(props.tree, props.activeBadCaseId ?? null),
);

onErrorCaptured((error) => {
  laneError.value = error instanceof Error ? error.message : String(error);
  mode.value = "tree";
  return false;
});

function setMode(next: FlowMode) {
  if (mode.value === next) {
    return;
  }
  mode.value = next;
}

watch(
  () => props.defaultMode,
  (next) => {
    mode.value = next;
  },
);

watch(
  () => [props.activeBadCaseId, laneModel.value.lanes.length],
  () => {
    if (mode.value !== "dag" || !props.activeBadCaseId) {
      return;
    }
    void nextTick().then(() => {
      laneDagRef.value?.locateBadCase(props.activeBadCaseId!);
    });
  },
  { flush: "post" },
);

/**
 * Center the active view on one bad case.
 *
 * @param badCaseId Selected bad case identifier.
 * @returns Nothing.
 */
function locateBadCase(badCaseId: string) {
  if (mode.value === "dag") {
    laneDagRef.value?.locateBadCase(badCaseId);
    return;
  }
  void treeRef.value?.locateBadCase(badCaseId);
}

/**
 * Center the active view on one Agent lane or node.
 *
 * @param agentId Agent identifier of the target.
 * @returns Nothing.
 */
function locateAgent(agentId: string) {
  if (mode.value === "dag") {
    laneDagRef.value?.locateLane(agentId);
    return;
  }
  treeRef.value?.locateAgent(agentId);
}

defineExpose({
  locateBadCase,
  locateAgent,
  setMode,
  mode,
  laneError,
  fit: () => laneDagRef.value?.fit(),
  reset: () => laneDagRef.value?.reset(),
});
</script>

<template>
  <section
    class="agent-flow"
    data-testid="agent-flow"
  >
    <div class="flow-mode-bar">
      <span class="flow-mode-hint">
        <template v-if="laneError">
          小窗口 lane DAG 渲染失败，已回退到结构树。
        </template>
        <template v-else-if="mode === 'dag'">
          全部 lane 展开；滚轮缩放 / 拖拽平移，不按数量折叠。
        </template>
        <template v-else>
          结构树视图；选中 case 与深链在两种视图间共享。
        </template>
      </span>
      <div class="flow-mode-actions">
        <button
          v-if="mode === 'tree' && expanded.length"
          type="button"
          class="collapse-tree"
          data-testid="collapse-tree"
          @click="emit('collapse-all')"
        >
          收起分支
        </button>
        <div
          class="flow-mode"
          role="group"
          aria-label="执行流视图"
        >
          <button
            type="button"
            data-testid="flow-mode-dag"
            :aria-pressed="mode === 'dag'"
            :class="{ active: mode === 'dag' }"
            @click="setMode('dag')"
          >
            执行序 DAG
          </button>
          <button
            type="button"
            data-testid="flow-mode-tree"
            :aria-pressed="mode === 'tree'"
            :class="{ active: mode === 'tree' }"
            @click="setMode('tree')"
          >
            结构树
          </button>
        </div>
      </div>
    </div>
    <LaneDag
      v-if="mode === 'dag'"
      ref="laneDagRef"
      :height="dagHeight"
      :model="laneModel"
      :selected-case-id="activeBadCaseId"
      @select-case="emit('badcase-select', $event)"
    />
    <AgentTree
      v-else
      ref="treeRef"
      :active-agent-id="activeAgentId"
      :active-bad-case-id="activeBadCaseId"
      :active-event-index="activeEventIndex"
      :expanded="expanded"
      :height="treeHeight"
      :problems="problems"
      :tree="tree"
      @badcase-select="emit('badcase-select', $event)"
      @node-select="emit('node-select', $event)"
      @toggle-expanded="emit('toggle-expanded', $event)"
    />
  </section>
</template>

<style scoped>
.agent-flow {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.flow-mode-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.flow-mode-hint {
  color: var(--text-faint);
  font-size: 10px;
}

.flow-mode-actions {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.collapse-tree {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10px;
  cursor: pointer;
}

.flow-mode {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
}

.flow-mode button {
  padding: 3px 9px;
  border: 0;
  border-right: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 10px;
  font-weight: 650;
  cursor: pointer;
}

.flow-mode button:last-child {
  border-right: 0;
}

.flow-mode button.active {
  background: var(--surface-selected);
  color: var(--blue);
}
</style>
