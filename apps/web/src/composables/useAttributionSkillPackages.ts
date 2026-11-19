import type { AttributionSkillPackageList } from "@harness/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter } from "vue";

import {
  activateAttributionSkillPackage,
  deleteAttributionSkillPackage,
  downloadAttributionSkillPackage,
  listAttributionSkillPackages,
  uploadAttributionSkillPackage,
} from "../api/attributionSkillPackages";
import { queryKeys } from "../api/queryKeys";

/**
 * Read and mutate workspace attribution Skill packages.
 * @param workspaceId Reactive owning workspace identifier.
 * @returns Package query and upload, activate, download, and delete operations.
 */
export function useAttributionSkillPackages(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const key = computed(() => queryKeys.attributionSkillPackages(toValue(workspaceId)));
  const packages = useQuery<AttributionSkillPackageList>({
    queryKey: key,
    queryFn: () => listAttributionSkillPackages(toValue(workspaceId)),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
  const refresh = async (): Promise<void> => {
    const wid = toValue(workspaceId);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: key.value }),
      queryClient.invalidateQueries({ queryKey: queryKeys.attributionSkills(wid) }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.evolutionTargets(wid),
        predicate: (query) => query.queryKey.at(-1) === "attribution-skill",
      }),
    ]);
  };
  const uploadMutation = useMutation({
    mutationFn: (file: File) =>
      uploadAttributionSkillPackage(toValue(workspaceId), file),
    onSuccess: refresh,
  });
  const activateMutation = useMutation({
    mutationFn: (packageId: string) =>
      activateAttributionSkillPackage(toValue(workspaceId), packageId),
    onSuccess: refresh,
  });
  const deleteMutation = useMutation({
    mutationFn: (packageId: string) =>
      deleteAttributionSkillPackage(toValue(workspaceId), packageId),
    onSuccess: refresh,
  });

  return {
    packages,
    upload: (file: File) => uploadMutation.mutateAsync(file),
    activate: (packageId: string) => activateMutation.mutateAsync(packageId),
    download: (packageId: string) =>
      downloadAttributionSkillPackage(toValue(workspaceId), packageId),
    remove: (packageId: string) => deleteMutation.mutateAsync(packageId),
    isMutating: computed(
      () =>
        uploadMutation.isPending.value ||
        activateMutation.isPending.value ||
        deleteMutation.isPending.value,
    ),
  };
}
