import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter } from "vue";

import {
  cancelAttributionJob,
  listAttributionJobs,
  retryAttributionJob,
  startAttributionJob,
} from "../api/evolutionRuns";
import { queryKeys } from "../api/queryKeys";

/**
 * Read and control durable attribution work for one evolution run.
 * @param workspaceId Workspace route identifier.
 * @param runId Evolution run identifier.
 * @returns Polling history plus start, retry, and cancellation mutations.
 */
export function useAttributionJobs(
  workspaceId: MaybeRefOrGetter<string>,
  runId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const key = () => queryKeys.attributionJobs(toValue(workspaceId), toValue(runId));
  const invalidate = async () => queryClient.invalidateQueries({ queryKey: key() });
  const jobs = useQuery({
    queryKey: computed(key),
    queryFn: () => listAttributionJobs(toValue(workspaceId), toValue(runId)),
    enabled: computed(
      () => toValue(workspaceId).length > 0 && toValue(runId).length > 0,
    ),
    refetchInterval: 2_000,
  });
  const start = useMutation({
    mutationFn: () => startAttributionJob(toValue(workspaceId), toValue(runId)),
    onSuccess: invalidate,
  });
  const retry = useMutation({
    mutationFn: (jobId: string) =>
      retryAttributionJob(toValue(workspaceId), toValue(runId), jobId),
    onSuccess: invalidate,
  });
  const cancel = useMutation({
    mutationFn: (jobId: string) =>
      cancelAttributionJob(toValue(workspaceId), toValue(runId), jobId),
    onSuccess: invalidate,
  });
  return { jobs, start, retry, cancel };
}
