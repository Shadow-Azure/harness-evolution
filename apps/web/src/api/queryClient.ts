import { QueryClient } from "@tanstack/vue-query";

/**
 * Create the application query cache.
 * @returns Query defaults matching the shared front-end design.
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 5 * 60 * 1000,
        retry: false,
        staleTime: 30 * 1000
      }
    }
  });
}
