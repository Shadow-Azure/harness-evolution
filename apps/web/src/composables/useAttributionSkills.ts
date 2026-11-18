import type {
  AttributionSkillList,
  EffectiveAttributionSkill,
} from "@harness/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter } from "vue";

import {
  bindTargetAttributionSkill,
  getTargetAttributionSkill,
  listAttributionSkills,
  unbindTargetAttributionSkill,
} from "../api/attributionSkills";
import { queryKeys } from "../api/queryKeys";

/**
 * Read visible revisions and manage the effective Skill of one reactive target.
 * @param workspaceId Route workspace identifier.
 * @param targetId Selected target identifier, or an empty value when unavailable.
 * @returns Queries and target bind/unbind mutations.
 */
export function useAttributionSkills(
  workspaceId: MaybeRefOrGetter<string>,
  targetId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const skills = useQuery<AttributionSkillList>({
    queryKey: computed(() => queryKeys.attributionSkills(toValue(workspaceId))),
    queryFn: () => listAttributionSkills(toValue(workspaceId)),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
  const effective = useQuery<EffectiveAttributionSkill>({
    queryKey: computed(() =>
      queryKeys.targetAttributionSkill(
        toValue(workspaceId),
        toValue(targetId) || "empty",
      ),
    ),
    queryFn: () =>
      getTargetAttributionSkill(toValue(workspaceId), toValue(targetId)),
    enabled: computed(
      () => toValue(workspaceId).length > 0 && toValue(targetId).length > 0,
    ),
    retry: false,
  });
  const bindMutation = useMutation({
    mutationFn: (skillRevisionId: string) =>
      bindTargetAttributionSkill(toValue(workspaceId), toValue(targetId), {
        skillRevisionId,
      }),
    onSuccess: (value) => {
      queryClient.setQueryData(
        queryKeys.targetAttributionSkill(
          toValue(workspaceId),
          toValue(targetId),
        ),
        value,
      );
    },
  });
  const unbindMutation = useMutation({
    mutationFn: () =>
      unbindTargetAttributionSkill(toValue(workspaceId), toValue(targetId)),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.targetAttributionSkill(
          toValue(workspaceId),
          toValue(targetId),
        ),
      }),
  });

  return {
    skills,
    effective,
    bindTarget: (revisionId: string): Promise<EffectiveAttributionSkill> =>
      bindMutation.mutateAsync(revisionId),
    useDefault: (): Promise<void> => unbindMutation.mutateAsync(),
    isMutating: computed(
      () => bindMutation.isPending.value || unbindMutation.isPending.value,
    ),
  };
}
