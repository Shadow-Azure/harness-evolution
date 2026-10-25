import { MutationCache, QueryCache, QueryClient } from "@tanstack/vue-query";

import { ApiError } from "./http";

/** Application-level handling options for failures surfaced by Vue Query. */
export type AppQueryClientOptions = {
  onError?: (error: unknown) => void;
};

/**
 * Create the application query cache.
 * @param options Application-level failure presenter.
 * @returns Query defaults matching the shared front-end design.
 */
export function createAppQueryClient(
  options: AppQueryClientOptions = {},
): QueryClient {
  const handleError = (error: unknown) => {
    options.onError?.(error);
  };
  return new QueryClient({
    mutationCache: new MutationCache({ onError: handleError }),
    queryCache: new QueryCache({ onError: handleError }),
    defaultOptions: {
      queries: {
        gcTime: 5 * 60 * 1000,
        refetchOnWindowFocus: false,
        retry: (count, error) =>
          !(error instanceof ApiError && error.status < 500) && count < 2,
        staleTime: 30 * 1000
      }
    }
  });
}
