<script setup lang="ts">
import { ref } from "vue";

import AgentTree from "../../components/agent-tree/AgentTree.vue";
import { demoCoreTree } from "../../components/agent-tree/fixtures/demo-nested";

defineOptions({ name: "AgentTreeDemoPage" });

const expanded = ref(["main", "agent-a"]);

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
      <span class="scope">开发视觉验收 · demo-nested 核心四节点</span>
    </header>
    <AgentTree
      :expanded="expanded"
      :tree="demoCoreTree"
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
