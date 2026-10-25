import type { ChangePasswordRequest, LoginRequest } from "@harness/contracts";
import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import { safeRedirect } from "../router/safeRedirect";
import { useAuthStore } from "../stores/auth";

/**
 * Read a stable API error code without coupling views to the transport module.
 * @param error Error exposed by an auth request state.
 * @returns The code when the failure carries one.
 */
export function authErrorCode(error: Error | null): string | undefined {
  if (!error || !("code" in error) || typeof error.code !== "string") {
    return undefined;
  }
  return error.code;
}

/**
 * Login mutation helpers for the authentication page.
 * @returns Login mutation and reactive pending state.
 */
export function useLogin() {
  const auth = useAuthStore();
  const route = useRoute();
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: (credentials: LoginRequest) => auth.login(credentials),
    onSuccess: async () => {
      await router.push(safeRedirect(route.query.redirect));
    },
  });
  return {
    data: mutation.data,
    isLoading: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error,
    refetch: (credentials: LoginRequest) => mutation.mutateAsync(credentials),
  };
}

/**
 * Logout mutation that clears memory and server-state caches before navigating.
 * @returns Logout mutation and reactive pending state.
 */
export function useLogout() {
  const auth = useAuthStore();
  const queryClient = useQueryClient();
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: () => auth.logout(queryClient),
    onSettled: async () => {
      await router.push("/login");
    },
  });
  return {
    data: mutation.data,
    isLoading: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error,
    refetch: () => mutation.mutateAsync(),
  };
}

/**
 * Current authenticated user read from the in-memory store.
 * @returns Readonly current-user computed value.
 */
export function useCurrentUser() {
  const auth = useAuthStore();
  return {
    data: computed(() => auth.user),
    isLoading: computed(() => !auth.isBootstrapped),
    isError: computed(() => false),
    error: computed<Error | null>(() => null),
    refetch: () => auth.loadCurrentUser(),
  };
}

/**
 * Forced password-change mutation with refresh-before-return semantics.
 * @returns Password-change mutation and reactive pending state.
 */
export function useChangePassword() {
  const auth = useAuthStore();
  const route = useRoute();
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: (passwords: ChangePasswordRequest) => auth.changePassword(passwords),
    onSuccess: async () => {
      await router.push(safeRedirect(route.query.redirect));
    },
  });
  return {
    data: mutation.data,
    isLoading: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error,
    refetch: (passwords: ChangePasswordRequest) => mutation.mutateAsync(passwords),
  };
}
