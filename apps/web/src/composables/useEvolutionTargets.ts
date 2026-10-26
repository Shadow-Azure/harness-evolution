import type { EvolutionTarget, EvolutionTargetWrite } from "@harness/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";

import {
  createEvolutionTarget,
  deleteEvolutionTarget,
  listEvolutionTargets,
  listEvolutionTargetVersions,
  updateEvolutionTarget,
} from "../api/evolutionTargets";
import { queryKeys } from "../api/queryKeys";

async function invalidateTargetDependents(
  queryClient: ReturnType<typeof useQueryClient>,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.evolutionTargets }),
    queryClient.invalidateQueries({ queryKey: queryKeys.catalogs }),
  ]);
}

/**
 * Read target configuration and expose cache-aware CRUD mutations.
 * @returns Collection query state and mutation methods.
 */
export function useEvolutionTargets() {
  const queryClient = useQueryClient();
  const targets = useQuery({
    queryKey: queryKeys.evolutionTargets,
    queryFn: listEvolutionTargets,
  });
  const createMutation = useMutation({
    mutationFn: (body: EvolutionTargetWrite) => createEvolutionTarget(body),
    onSuccess: () => invalidateTargetDependents(queryClient),
  });
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: EvolutionTargetWrite;
    }) => updateEvolutionTarget(id, body),
    onSuccess: () => invalidateTargetDependents(queryClient),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteEvolutionTarget(id),
    onSuccess: () => invalidateTargetDependents(queryClient),
  });

  return {
    ...targets,
    createTarget: (body: EvolutionTargetWrite): Promise<EvolutionTarget> =>
      createMutation.mutateAsync(body),
    updateTarget: (
      id: string,
      body: EvolutionTargetWrite,
    ): Promise<EvolutionTarget> => updateMutation.mutateAsync({ id, body }),
    deleteTarget: (id: string): Promise<void> =>
      deleteMutation.mutateAsync(id),
  };
}

/**
 * Read remote versions for one selected target.
 * @param targetId Reactive target identifier, or null when no target is selected.
 * @returns Version query state.
 */
export function useEvolutionTargetVersions(targetId: Ref<string | null>) {
  return useQuery({
    enabled: computed(() => Boolean(targetId.value)),
    queryKey: computed(() =>
      targetId.value
        ? queryKeys.evolutionTargetVersions(targetId.value)
        : (["evolution", "targets", "empty", "versions"] as const),
    ),
    queryFn: () => listEvolutionTargetVersions(targetId.value as string),
    retry: false,
  });
}
