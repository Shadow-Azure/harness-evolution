import { useRoute } from "vue-router";
import { computed, type ComputedRef } from "vue";

/**
 * Read the workspace id owned by the matched route.
 * @returns Reactive route workspace identifier, or an empty string outside a shell route.
 */
export function useWorkspaceId(): ComputedRef<string> {
  const route = useRoute();
  return computed(() =>
    typeof route.params.wid === "string" ? route.params.wid : "",
  );
}
