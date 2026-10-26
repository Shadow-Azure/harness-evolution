<script setup lang="ts">
import type { EvolutionTarget } from "@harness/contracts";
import { computed } from "vue";

import { useEvolutionTargets } from "../../../composables/useEvolutionTargets";
import { useAuthStore } from "../../../stores/auth";
import TargetTable from "./components/TargetTable.vue";

defineOptions({ name: "TargetConfigPage" });

const auth = useAuthStore();
const { data, error, isPending, refetch } = useEvolutionTargets();

const targets = computed(() => data.value?.items ?? []);
const canWrite = computed(() => auth.user?.role === "admin");

function openCreate(): void {
  // Creation dialog wiring belongs to the form task.
}

function openEdit(target: EvolutionTarget): void {
  void target;
  // Edit dialog wiring belongs to the form task.
}

function removeTarget(target: EvolutionTarget): void {
  void target;
  // Delete confirmation belongs to the actions task.
}
</script>

<template>
  <section
    class="target-config-page"
    data-testid="target-config-page"
  >
    <header class="page-heading">
      <div>
        <p class="eyebrow">
          EVOLUTION
        </p>
        <h1>进化对象配置</h1>
        <p class="lede">
          配置可被自进化修改的 skill 与 agent；仓库、引用和路径由后端校验。
        </p>
      </div>
    </header>

    <TargetTable
      :can-write="canWrite"
      :error="error"
      :loading="isPending"
      :targets="targets"
      @create="openCreate"
      @delete="removeTarget"
      @edit="openEdit"
      @retry="refetch"
    />
  </section>
</template>

<style scoped>
.target-config-page {
  display: grid;
  min-width: 0;
  gap: 16px;
  padding: 8px 0 24px;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--purple);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

h1 {
  margin: 0;
  color: var(--text);
  font-size: var(--font-title);
  font-weight: 650;
}

.lede {
  max-width: 680px;
  margin: 7px 0 0;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 640px) {
  .target-config-page {
    padding-top: 2px;
  }
}
</style>
