<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import AgentTree from "../../components/agent-tree/AgentTree.vue";
import {
  demoCoreTree,
  demoNestedTree,
} from "../../components/agent-tree/fixtures/demo-nested";

defineOptions({ name: "AgentTreeDemoPage" });

const route = useRoute();
const isLarge = computed(() => route.query.variant === "large");
const tree = computed(() => (isLarge.value ? demoNestedTree : demoCoreTree));
const expanded = ref<string[]>([]);

watch(
  isLarge,
  (large) => {
    expanded.value = large ? ["agent-a"] : ["main", "agent-a"];
  },
  { immediate: true },
);

function toggleExpanded(agentId: string) {
  if (!expanded.value.includes(agentId)) {
    expanded.value = [...expanded.value, agentId];
  }
}
</script>

<template>
  <section
    class="agent-tree-demo"
    data-testid="agent-tree-demo"
  >
    <header>
      <div>
        <span class="eyebrow">AGENT FLOW</span>
        <h1>Agent 执行流图</h1>
      </div>
      <span class="scope">
        开发视觉验收 · {{ isLarge ? "collapse / trunk 大图" : "demo-nested 核心四节点" }}
      </span>
    </header>
    <AgentTree
      :expanded="expanded"
      :tree="tree"
      @toggle-expanded="toggleExpanded"
    />
  </section>
</template>

<style scoped>
.agent-tree-demo {
  min-height: calc(100vh - var(--shell-header-height));
  padding: var(--space-lg) var(--space-xl);
  background: var(--bg);
}

header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

h1 {
  margin: 2px 0 0;
  color: var(--text);
  font-size: 17px;
  font-weight: 650;
}

.eyebrow,
.scope {
  color: var(--text-faint);
  font-size: 10.5px;
  letter-spacing: 0.3px;
}

.scope {
  font-family: var(--mono);
}

@media (max-width: 860px) {
  .agent-tree-demo {
    padding: var(--space-md);
  }

  header {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--space-xs);
  }
}
</style>
