import type {
  PublicUser,
  Workspace,
  WorkspaceBadCaseLabelConfiguration,
  WorkspaceBadCaseLabelRequest,
  WorkspaceBadCaseLabelSuggestion,
  WorkspaceCreateRequest,
  WorkspaceCredentialCreated,
  WorkspaceMember,
  WorkspaceMemberCreateRequest,
  WorkspaceMemberUpdateRequest,
  WorkspaceUpdateRequest,
} from "@harness/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import {
  computed,
  onScopeDispose,
  ref,
  toValue,
  type MaybeRefOrGetter,
  type Ref,
} from "vue";

import { queryKeys } from "../api/queryKeys";
import { useAuthStore } from "../stores/auth";
import {
  addWorkspaceMember,
  appointSelfAsSpaceAdmin,
  createWorkspace,
  createWorkspaceCredential,
  listMemberCandidates,
  listWorkspaceBadCaseLabels,
  listWorkspaceBadCaseLabelSuggestions,
  listWorkspaceCredentials,
  listWorkspaceMembers,
  listWorkspaces,
  removeWorkspaceMember,
  replaceWorkspaceBadCaseLabels,
  revokeWorkspaceCredential,
  updateWorkspace,
  updateWorkspaceMember,
} from "../api/workspaces";
import { listUsers } from "../api/users";

type QueryClient = ReturnType<typeof useQueryClient>;

async function refreshAuthSession(): Promise<void> {
  try {
    await useAuthStore().loadSession();
  } catch {
    // The admin table already has the authoritative list; a failed session
    // refresh must not turn a successful mutation into an error.
  }
}

async function invalidateWorkspaceList(
  queryClient: QueryClient,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.workspaces() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.authSession }),
  ]);
  await refreshAuthSession();
}

async function invalidateWorkspaceAdmin(
  queryClient: QueryClient,
  workspaceId: string,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.admin(workspaceId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.workspaces(),
    }),
    queryClient.invalidateQueries({ queryKey: queryKeys.authSession }),
  ]);
  await refreshAuthSession();
}

/**
 * Read every workspace visible to the current session for the management page.
 * @returns Workspace collection query state.
 */
export function useWorkspaceList() {
  return useQuery({
    queryKey: queryKeys.workspaces(),
    queryFn: listWorkspaces,
  });
}

/**
 * Read every user in the organization for the workspace creation dialog.
 * @param enabled Whether the caller is the global administrator.
 * @returns Public user collection query state.
 */
export function useAllUsers(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: queryKeys.users(),
    queryFn: listUsers,
    enabled: computed(() => toValue(enabled)),
  });
}

/**
 * Read the membership table of one workspace.
 * @param workspaceId Workspace route identifier.
 * @param enabled Whether the effective role may list members (viewers cannot).
 * @returns Member collection query state.
 */
export function useWorkspaceMembers(
  workspaceId: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.adminMembers(toValue(workspaceId))),
    queryFn: () => listWorkspaceMembers(toValue(workspaceId)),
    enabled: computed(
      () => toValue(enabled) && toValue(workspaceId).length > 0,
    ),
  });
}

/**
 * Search users who are not members of one workspace.
 * @param workspaceId Workspace route identifier.
 * @param query Reactive search text.
 * @param enabled Whether the add-member dialog is open.
 * @returns Bounded non-member candidate query state.
 */
export function useMemberCandidates(
  workspaceId: MaybeRefOrGetter<string>,
  query: Ref<string>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.adminMemberCandidates(toValue(workspaceId), query.value),
    ),
    queryFn: () =>
      listMemberCandidates(toValue(workspaceId), query.value.trim()),
    enabled: computed(
      () => toValue(enabled) && toValue(workspaceId).length > 0,
    ),
    staleTime: 10_000,
  });
}

/**
 * Read every ingest credential row of one workspace without plaintext.
 * @param workspaceId Workspace route identifier.
 * @param enabled Whether the caller may manage the workspace.
 * @returns Credential collection query state.
 */
export function useWorkspaceCredentials(
  workspaceId: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.adminCredentials(toValue(workspaceId)),
    ),
    queryFn: () => listWorkspaceCredentials(toValue(workspaceId)),
    enabled: computed(
      () => toValue(enabled) && toValue(workspaceId).length > 0,
    ),
  });
}

/**
 * Create one workspace and refresh every workspace-derived cache.
 * @returns Workspace creation mutation.
 */
export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: WorkspaceCreateRequest) => createWorkspace(body),
    onSuccess: () => invalidateWorkspaceList(queryClient),
  });
  return {
    isPending: mutation.isPending,
    createWorkspace: (body: WorkspaceCreateRequest): Promise<Workspace> =>
      mutation.mutateAsync(body),
  };
}

/**
 * Update one workspace's permitted fields.
 * @param workspaceId Workspace route identifier.
 * @returns Workspace update mutation.
 */
export function useUpdateWorkspace(workspaceId: MaybeRefOrGetter<string>) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: WorkspaceUpdateRequest) =>
      updateWorkspace(toValue(workspaceId), body),
    onSuccess: async () => {
      await Promise.all([
        invalidateWorkspaceList(queryClient),
        queryClient.invalidateQueries({
          queryKey: queryKeys.workspace(toValue(workspaceId)),
        }),
      ]);
    },
  });
  return {
    isPending: mutation.isPending,
    updateWorkspace: (body: WorkspaceUpdateRequest): Promise<Workspace> =>
      mutation.mutateAsync(body),
  };
}

/**
 * Add one existing user to the route workspace.
 * @param workspaceId Workspace route identifier.
 * @returns Member creation mutation.
 */
export function useAddWorkspaceMember(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: WorkspaceMemberCreateRequest) =>
      addWorkspaceMember(toValue(workspaceId), body),
    onSuccess: () => invalidateWorkspaceAdmin(queryClient, toValue(workspaceId)),
  });
  return {
    isPending: mutation.isPending,
    addMember: (body: WorkspaceMemberCreateRequest): Promise<WorkspaceMember> =>
      mutation.mutateAsync(body),
  };
}

/**
 * Change one workspace member's role.
 * @param workspaceId Workspace route identifier.
 * @returns Member update mutation.
 */
export function useUpdateWorkspaceMember(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({
      userId,
      body,
    }: {
      userId: string;
      body: WorkspaceMemberUpdateRequest;
    }) => updateWorkspaceMember(toValue(workspaceId), userId, body),
    onSuccess: () => invalidateWorkspaceAdmin(queryClient, toValue(workspaceId)),
  });
  return {
    isPending: mutation.isPending,
    updateMember: (
      userId: string,
      body: WorkspaceMemberUpdateRequest,
    ): Promise<WorkspaceMember> => mutation.mutateAsync({ userId, body }),
  };
}

/**
 * Remove one workspace member.
 * @param workspaceId Workspace route identifier.
 * @returns Member removal mutation.
 */
export function useRemoveWorkspaceMember(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (userId: string) =>
      removeWorkspaceMember(toValue(workspaceId), userId),
    onSuccess: () => invalidateWorkspaceAdmin(queryClient, toValue(workspaceId)),
  });
  return {
    isPending: mutation.isPending,
    removeMember: (userId: string): Promise<void> =>
      mutation.mutateAsync(userId),
  };
}

/**
 * Write a real space-administrator row for the global administrator.
 * @param workspaceId Workspace route identifier.
 * @returns Idempotent self-appointment mutation.
 */
export function useAppointSelfAsSpaceAdmin(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => appointSelfAsSpaceAdmin(toValue(workspaceId)),
    onSuccess: () => invalidateWorkspaceAdmin(queryClient, toValue(workspaceId)),
  });
  return {
    isPending: mutation.isPending,
    appointSelf: (): Promise<WorkspaceMember> => mutation.mutateAsync(),
  };
}

/**
 * Mint and revoke ingest credentials of the route workspace.
 * @param workspaceId Workspace route identifier.
 * @returns Credential mutation helpers.
 */
export function useWorkspaceCredentialMutations(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const createMutation = useMutation({
    mutationFn: () => createWorkspaceCredential(toValue(workspaceId)),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.adminCredentials(toValue(workspaceId)),
      }),
  });
  const revokeMutation = useMutation({
    mutationFn: (credentialId: string) =>
      revokeWorkspaceCredential(toValue(workspaceId), credentialId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.adminCredentials(toValue(workspaceId)),
      }),
  });
  return {
    isCreating: createMutation.isPending,
    isRevoking: revokeMutation.isPending,
    createCredential: (): Promise<WorkspaceCredentialCreated> =>
      createMutation.mutateAsync(),
    revokeCredential: (credentialId: string): Promise<void> =>
      revokeMutation.mutateAsync(credentialId),
  };
}

/**
 * Read the public badcase labels accepted by one workspace.
 *
 * Every member can read the label set; it drives the workspace's visible
 * badcase boundary, not a secret, so the query stays enabled for viewers too.
 * @param workspaceId Workspace route identifier.
 * @param enabled Whether the label query should run.
 * @returns Label configuration query state.
 */
export function useWorkspaceBadCaseLabels(
  workspaceId: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.adminBadCaseLabels(toValue(workspaceId)),
    ),
    queryFn: () => listWorkspaceBadCaseLabels(toValue(workspaceId)),
    enabled: computed(
      () => toValue(enabled) && toValue(workspaceId).length > 0,
    ),
  });
}

/** Debounce applied to label candidates so typing stays responsive. */
const LABEL_SUGGESTION_DEBOUNCE_MS = 200;

/**
 * Load public catalog label candidates for the label input.
 *
 * The dropdown is advisory: lookups debounce for 200ms, only the newest
 * response may replace the candidate list, and a failed lookup clears the
 * candidates instead of surfacing an error so free-text entry keeps working.
 * @param workspaceId Workspace route identifier.
 * @returns Candidate list state plus its deferred loader and reset helper.
 */
export function useWorkspaceBadCaseLabelSuggestions(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const suggestions = ref<WorkspaceBadCaseLabelSuggestion[]>([]);
  const loading = ref(false);
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  let requestSequence = 0;

  function cancelDebounce(): void {
    if (debounceTimer === undefined) return;
    globalThis.clearTimeout(debounceTimer);
    debounceTimer = undefined;
  }

  async function fetchSuggestions(
    query: string,
    sequence: number,
  ): Promise<void> {
    loading.value = true;
    try {
      const response = await listWorkspaceBadCaseLabelSuggestions(
        toValue(workspaceId),
        { q: query },
      );
      if (sequence !== requestSequence) return;
      suggestions.value = response.items;
    } catch {
      if (sequence !== requestSequence) return;
      suggestions.value = [];
    } finally {
      if (sequence === requestSequence) loading.value = false;
    }
  }

  /**
   * Queue one debounced candidate lookup, dropping the pending one.
   * @param query Prefix to match; an empty string requests the most common labels.
   * @returns No value.
   */
  function load(query: string): void {
    cancelDebounce();
    const sequence = ++requestSequence;
    const prefix = query.trim();
    loading.value = true;
    debounceTimer = globalThis.setTimeout(() => {
      debounceTimer = undefined;
      void fetchSuggestions(prefix, sequence);
    }, LABEL_SUGGESTION_DEBOUNCE_MS);
  }

  /**
   * Clear candidates and cancel any debounced lookup.
   * @returns No value.
   */
  function reset(): void {
    cancelDebounce();
    requestSequence += 1;
    suggestions.value = [];
    loading.value = false;
  }

  onScopeDispose(cancelDebounce);

  return { suggestions, loading, load, reset };
}

/**
 * Atomically replace a workspace's accepted labels and historical assignments.
 * @param workspaceId Workspace route identifier.
 * @returns Label replacement mutation.
 */
export function useReplaceWorkspaceBadCaseLabels(
  workspaceId: MaybeRefOrGetter<string>,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (body: WorkspaceBadCaseLabelRequest) =>
      replaceWorkspaceBadCaseLabels(toValue(workspaceId), body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.adminBadCaseLabels(toValue(workspaceId)),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.workspace(toValue(workspaceId)),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.workspaces(),
        }),
        queryClient.invalidateQueries({ queryKey: queryKeys.authSession }),
      ]);
      await refreshAuthSession();
    },
  });
  return {
    isPending: mutation.isPending,
    replaceLabels: (
      body: WorkspaceBadCaseLabelRequest,
    ): Promise<WorkspaceBadCaseLabelConfiguration> => mutation.mutateAsync(body),
  };
}

/**
 * Build the JSON ingest example shown on the ingest tab.
 *
 * The body mirrors the bad case ingest contract and deliberately contains only
 * synthetic values; workspace identity is resolved from the URL and credential.
 * @returns Pretty-printed JSON request body.
 */
export function ingestExampleBody(): string {
  return JSON.stringify(
    {
      badCaseId: "BC-HC-021",
      sessionId: "cb819c5b-286f-4eab-a681-4ba5414b844d",
      badCaseType: "self",
      objectName: "deep-research",
      objectType: "skill",
      objectVersion: "v2.4.0",
      title: "输出缺少来源校验",
      reason: "12 条结论中有 5 条没有附带来源。",
      metaData: {
        file: "skills/deep-research/SKILL.md",
        line: 91,
      },
      source: "agent-runtime",
      createdAt: "2026-11-09T15:58:00+08:00",
    },
    null,
    2,
  );
}

/**
 * Build the copy-ready curl example for one workspace.
 * @param endpoint Absolute ingest endpoint.
 * @param credential Plaintext credential while the one-time dialog is open.
 * @returns Multi-line curl command.
 */
export function ingestExampleCurl(
  endpoint: string,
  credential: string,
): string {
  const body = ingestExampleBody().replace(/\n\s*/g, " ");
  return [
    `curl -X POST '${endpoint}' \\`,
    `  -H 'Authorization: Bearer ${credential}' \\`,
    "  -H 'Content-Type: application/json' \\",
    `  -d '${body}'`,
  ].join("\n");
}

/** Public user list used by the creation dialog. */
export type WorkspaceUser = PublicUser;
