<script setup lang="ts">
import { Handle, Position } from "@vue-flow/core";
import { computed } from "vue";

import { BOX_EDGE, BOX_PAD } from "../layout";
import type { AgentLayoutNodeData } from "../types";

const props = defineProps<{
  data: AgentLayoutNodeData;
}>();

const sourceHandles = computed(() =>
  props.data.chain.items.flatMap((item) => {
    if (item.kind === "gap") {
      return [];
    }
    return [
      {
        id: `h${item.evIdx}`,
        left: BOX_PAD + BOX_EDGE + (props.data.chain.offsets[item.evIdx] ?? 0),
      },
    ];
  }),
);
</script>

<template>
  <button
    class="rf-agent"
    :class="[data.kind, { active: data.active }]"
    :aria-label="data.label"
    :aria-pressed="Boolean(data.active)"
    :style="{ width: `${data.boxW}px` }"
    type="button"
  >
    <div
      class="rf-label"
      :title="data.label"
    >
      {{ data.label }}
    </div>
    <div class="rf-chain">
      <template
        v-for="(item, index) in data.chain.items"
        :key="`${item.kind}-${index}`"
      >
        <span
          v-if="index > 0"
          class="rf-link"
        />
        <span
          v-if="item.kind === 'gap'"
          class="rf-cnode gap"
          :title="`压缩合并 ${item.n} 条 assistant 消息`"
        >
          × {{ item.n }}
        </span>
        <span
          v-else
          class="rf-cnode"
          :class="[
            item.kind,
            {
              evidence:
                data.active &&
                data.activeEvidence !== null &&
                data.activeEvidence === item.evIdx,
            },
          ]"
          :title="`L${item.line} · ${item.name}`"
        >
          <span class="rf-cdot" />
          {{ item.name }}
        </span>
      </template>
    </div>
    <div class="rf-lines">
      {{ data.lines }} 行
    </div>
    <Handle
      id="in"
      type="target"
      :position="Position.Left"
      class="hidden-handle"
    />
    <Handle
      id="in-left"
      type="target"
      :position="Position.Left"
      class="hidden-handle"
    />
    <Handle
      v-for="handle in sourceHandles"
      :id="handle.id"
      :key="handle.id"
      type="source"
      :position="Position.Bottom"
      class="hidden-handle"
      :style="{ left: `${handle.left}px` }"
    />
    <span
      v-for="handle in sourceHandles"
      :key="`stub-${handle.id}`"
      class="rf-stub"
      :style="{ left: `${handle.left}px` }"
    />
  </button>
</template>

<style scoped>
.rf-agent {
  position: relative;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.rf-agent.active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--blue) 32%, transparent),
    var(--shadow-card);
}

.rf-agent:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}

.rf-agent.root {
  border-color: color-mix(in srgb, var(--blue) 42%, var(--border));
}

.rf-agent.sub {
  border-color: color-mix(in srgb, var(--purple) 42%, var(--border));
}

.rf-agent.wf {
  border-color: color-mix(in srgb, var(--orange) 42%, var(--border));
}

.rf-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
  overflow: hidden;
  color: var(--text-dim);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rf-label::before {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--blue);
  content: "";
}

.rf-agent.sub .rf-label::before {
  background: var(--purple);
}

.rf-agent.wf .rf-label::before {
  background: var(--orange);
}

.rf-chain {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 22px;
  overflow: hidden;
}

.rf-link {
  width: 10px;
  height: 2px;
  flex-shrink: 0;
  background: var(--graph-link);
}

.rf-cnode {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  height: 20px;
  box-sizing: border-box;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}

.rf-cnode.gap {
  border: 1px dashed var(--border);
  background: var(--bg-inset);
  color: var(--text-faint);
  font-family: var(--mono);
}

.rf-cnode.skill {
  border: 1px solid color-mix(in srgb, var(--cyan) 55%, transparent);
  background: var(--bg-card);
  color: var(--cyan);
}

.rf-cnode.agent {
  border: 1px solid color-mix(in srgb, var(--purple) 45%, transparent);
  background: color-mix(in srgb, var(--purple) 8%, var(--bg-card));
  color: var(--purple);
}

.rf-cnode.workflow {
  border: 1px solid color-mix(in srgb, var(--orange) 45%, transparent);
  background: color-mix(in srgb, var(--orange) 10%, var(--bg-card));
  color: var(--orange);
}

.rf-cnode.evidence {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--blue) 34%, transparent);
}

.rf-cdot {
  width: 6px;
  height: 6px;
  margin-right: 4px;
  background: currentColor;
  transform: rotate(45deg);
}

.rf-lines {
  margin-top: 3px;
  color: var(--text-faint);
  font-size: 10px;
}

.rf-stub {
  position: absolute;
  bottom: 0;
  width: 1px;
  height: 27px;
  background: var(--graph-branch);
}

.hidden-handle {
  width: 8px;
  height: 8px;
  border: 0;
  background: transparent;
  opacity: 0;
}
</style>
