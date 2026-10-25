import { QueryClient } from "@tanstack/vue-query";

import { ApiError } from "./http";

/**
 * Create the application query cache.
 * @returns Query defaults matching the shared front-end design.
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
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
