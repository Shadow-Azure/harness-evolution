<script setup lang="ts">
import type { SessionTree } from "@harness/contracts";
import {
  VueFlow,
  useVueFlow,
  type EdgeTypesObject,
  type NodeMouseEvent,
  type NodeTypesObject,
} from "@vue-flow/core";
import "@vue-flow/core/dist/style.css";
import { Background } from "@vue-flow/background";
import { ControlButton } from "@vue-flow/controls";
import "@vue-flow/controls/dist/style.css";
import {
  computed,
  markRaw,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";

import AgentNode from "./nodes/AgentNode.vue";
import CollapseNode from "./nodes/CollapseNode.vue";
import OrthEdge from "./edges/OrthEdge.vue";
import { buildGraph } from "./layout";
import type { AgentLayoutNode, MeasureText } from "./types";

defineOptions({ name: "AgentTree" });

const props = withDefaults(
  defineProps<{
    tree: SessionTree;
    expanded?: string[];
    activeAgentId?: string | null;
    activeEventIndex?: number | null;
    height?: string;
  }>(),
  {
    expanded: () => [],
    activeAgentId: null,
    activeEventIndex: null,
    height: "720px",
  },
);

const emit = defineEmits<{
  "toggle-expanded": [agentId: string];
  "node-select": [agentId: string];
}>();

const nodeTypes = markRaw({
  agent: markRaw(AgentNode),
  collapse: markRaw(CollapseNode),
}) as unknown as NodeTypesObject;
const edgeTypes = markRaw({
  orth: markRaw(OrthEdge),
}) as unknown as EdgeTypesObject;

const browserMeasure: MeasureText = (text, font) => {
  if (
    typeof document === "undefined" ||
    typeof CanvasRenderingContext2D === "undefined"
  ) {
    return [...text].length * 6;
  }
  try {
    const context = document.createElement("canvas").getContext("2d");
    if (!context) {
      return [...text].length * 6;
    }
    context.font = font;
    return context.measureText(text).width;
  } catch {
    return [...text].length * 6;
  }
};

const expandedIds = ref(new Set(props.expanded));
watch(
  () => props.expanded,
  (next) => {
    expandedIds.value = new Set(next);
  },
);

const graph = computed(() =>
  buildGraph(props.tree, {
    expanded: expandedIds.value,
    measureText: browserMeasure,
  }),
);
const renderedNodes = computed(() =>
  graph.value.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      active: Boolean(props.activeAgentId && node.data.agentId === props.activeAgentId),
      activeEvidence:
        props.activeAgentId && node.data.agentId === props.activeAgentId
          ? props.activeEventIndex
          : null,
    },
  })),
);
const { fitView, getViewport, setCenter, zoomIn, zoomOut } = useVueFlow();
const treeRoot = ref<HTMLElement | null>(null);
let fitAnimationFrame: number | undefined;
let fitRetryTimer: ReturnType<typeof setTimeout> | undefined;
let fitSequence = 0;
let resizeObserver: ResizeObserver | undefined;

function cancelScheduledFit() {
  fitSequence += 1;
  if (fitAnimationFrame !== undefined) {
    cancelAnimationFrame(fitAnimationFrame);
    fitAnimationFrame = undefined;
  }
  if (fitRetryTimer !== undefined) {
    clearTimeout(fitRetryTimer);
    fitRetryTimer = undefined;
  }
}

function scheduleFitView() {
  cancelScheduledFit();
  const sequence = fitSequence;
  const fit = async () => {
    await nextTick();
    if (sequence !== fitSequence) {
      return;
    }
    await fitView({ padding: 0.12 });
  };

  if (typeof requestAnimationFrame === "function") {
    fitAnimationFrame = requestAnimationFrame(() => {
      fitAnimationFrame = requestAnimationFrame(() => {
        fitAnimationFrame = undefined;
        void fit();
      });
    });
  } else {
    void fit();
  }

  fitRetryTimer = setTimeout(() => {
    fitRetryTimer = undefined;
    if (sequence === fitSequence) {
      void fit();
    }
  }, 120);
}

watch(
  () => graph.value.nodes.map((node) => node.id).join("|"),
  () => {
    scheduleFitView();
  },
  { flush: "post" },
);

watch(
  [() => props.activeAgentId, () => props.activeEventIndex],
  async ([agentId]) => {
    if (!agentId) return;
    await nextTick();
    locateAgent(agentId);
  },
  { flush: "post", immediate: true },
);

function handleWindowResize() {
  scheduleFitView();
}

onMounted(() => {
  if (treeRoot.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => {
      scheduleFitView();
    });
    resizeObserver.observe(treeRoot.value);
  } else if (typeof window !== "undefined") {
    window.addEventListener("resize", handleWindowResize);
  }
});

onBeforeUnmount(() => {
  cancelScheduledFit();
  resizeObserver?.disconnect();
  resizeObserver = undefined;
  if (typeof window !== "undefined") {
    window.removeEventListener("resize", handleWindowResize);
  }
});

function onNodeClick(event: NodeMouseEvent) {
  const node = event.node as AgentLayoutNode;
  if (node.type === "collapse") {
    toggleCollapse(node);
    return;
  }
  if (node.data.agentId) {
    emit("node-select", node.data.agentId);
    locateAgent(node.data.agentId);
  }
}

/**
 * Center the viewport on one rendered Agent.
 * @param agentId Stable Agent identifier.
 * @returns Nothing.
 */
function locateAgent(agentId: string) {
  const node = graph.value.nodes.find(
    (candidate) => candidate.data.agentId === agentId,
  );
  if (!node) return;
  const zoom = Math.max(getViewport().zoom, 0.85);
  void setCenter(
    node.position.x + node.data.visualW / 2,
    node.position.y + 40,
    { zoom, duration: 260 },
  );
}

defineExpose({ fitView, locateAgent, zoomIn, zoomOut });

function toggleCollapse(node: AgentLayoutNode) {
  const agentId = node.data.parentForCollapse ?? node.data.parentAgentId;
  if (!agentId) {
    return;
  }
  const next = new Set(expandedIds.value);
  next.add(agentId);
  expandedIds.value = next;
  emit("toggle-expanded", agentId);
}

function onNodesInitialized() {
  scheduleFitView();
}

</script>

<template>
  <section
    ref="treeRoot"
    class="agent-tree"
    data-testid="agent-tree"
    :style="{ height }"
    aria-label="Agent 执行流图"
  >
    <VueFlow
      :nodes="renderedNodes"
      :edges="graph.edges"
      :node-types="nodeTypes"
      :edge-types="edgeTypes"
      :nodes-draggable="false"
      :nodes-connectable="false"
      :nodes-focusable="false"
      :edges-focusable="false"
      :elements-selectable="true"
      :min-zoom="0.2"
      :max-zoom="2.5"
      :fit-view-on-init="false"
      @node-click="onNodeClick"
      @nodes-initialized="onNodesInitialized"
    >
      <Background
        :gap="22"
        color="var(--graph-grid)"
      />
      <div
        class="vue-flow__controls agent-tree-controls"
        role="group"
        aria-label="图谱控制"
      >
        <ControlButton
          aria-label="放大"
          title="放大"
          @click="zoomIn"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
        </ControlButton>
        <ControlButton
          aria-label="缩小"
          title="缩小"
          @click="zoomOut"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
          >
            <path d="M5 12h14" />
          </svg>
        </ControlButton>
        <ControlButton
          aria-label="适应画布"
          title="适应画布"
          @click="fitView({ padding: 0.12 })"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
          >
            <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />
          </svg>
        </ControlButton>
      </div>
    </VueFlow>
    <p
      v-if="graph.diagnostics.length"
      class="diagnostics"
      role="status"
    >
      {{ graph.diagnostics.map((item) => item.code).join(" · ") }}
    </p>
  </section>
</template>

<style scoped>
.agent-tree {
  position: relative;
  width: 100%;
  min-height: 320px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-panel);
}

.agent-tree :deep(.vue-flow) {
  width: 100%;
  height: 100%;
}

.agent-tree :deep(.vue-flow__edge-path) {
  stroke: var(--graph-branch);
}

.agent-tree-controls {
  position: absolute;
  right: 10px;
  bottom: 10px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
}

.agent-tree-controls :deep(.vue-flow__controls-button) {
  width: 28px;
  height: 28px;
  border: 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
}

.agent-tree-controls :deep(.vue-flow__controls-button:last-child) {
  border-bottom: 0;
}

.agent-tree-controls :deep(svg) {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.diagnostics {
  position: absolute;
  top: 10px;
  left: 10px;
  margin: 0;
  padding: 3px 6px;
  border: 1px solid color-mix(in srgb, var(--orange) 28%, transparent);
  border-radius: 5px;
  background: color-mix(in srgb, var(--orange) 8%, var(--bg-card));
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}
</style>
