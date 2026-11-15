import type { EvolutionTarget, EvolutionTargetWrite } from "@harness/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter, type Ref } from "vue";

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
  workspaceId: string,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.evolutionTargets(workspaceId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.catalogs(workspaceId),
    }),
  ]);
}

/**
 * Read target configuration of one workspace and expose cache-aware CRUD mutations.
 * @param workspaceId Workspace route identifier.
 * @returns Collection query state and mutation methods.
 */
export function useEvolutionTargets(workspaceId: MaybeRefOrGetter<string>) {
  const queryClient = useQueryClient();
  const targets = useQuery({
    queryKey: computed(() => queryKeys.evolutionTargets(toValue(workspaceId))),
    queryFn: () => listEvolutionTargets(toValue(workspaceId)),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
  const createMutation = useMutation({
    mutationFn: (body: EvolutionTargetWrite) =>
      createEvolutionTarget(toValue(workspaceId), body),
    onSuccess: () =>
      invalidateTargetDependents(queryClient, toValue(workspaceId)),
  });
  const updateMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: EvolutionTargetWrite;
    }) => updateEvolutionTarget(toValue(workspaceId), id, body),
    onSuccess: () =>
      invalidateTargetDependents(queryClient, toValue(workspaceId)),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      deleteEvolutionTarget(toValue(workspaceId), id),
    onSuccess: () =>
      invalidateTargetDependents(queryClient, toValue(workspaceId)),
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
 * Read remote versions for one selected target of the route workspace.
 * @param workspaceId Workspace route identifier.
 * @param targetId Reactive target identifier, or null when no target is selected.
 * @returns Version query state.
 */
export function useEvolutionTargetVersions(
  workspaceId: MaybeRefOrGetter<string>,
  targetId: Ref<string | null>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(targetId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.evolutionTargetVersions(
        toValue(workspaceId),
        targetId.value ?? "empty",
      ),
    ),
    queryFn: () =>
      listEvolutionTargetVersions(
        toValue(workspaceId),
        targetId.value as string,
      ),
    retry: false,
  });
}
