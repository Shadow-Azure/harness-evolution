import type { EventTicketResponse } from "@harness/contracts";

import { request } from "./http";

/**
 * Bind one run topic, its workspace, and replay cursor to a single-use SSE ticket.
 * @param topics Authorized topics, usually `["run:<runId>"]`.
 * @param lastEventId Highest durable event sequence already rendered by REST.
 * @param workspaceId Workspace whose membership must authorize the topics.
 * @returns The opaque ticket, its lifetime, and the granted topics.
 */
export function requestEventTicket(
  topics: string[],
  lastEventId = 0,
  workspaceId?: string,
): Promise<EventTicketResponse> {
  return request<EventTicketResponse>("/api/events/ticket", {
    method: "POST",
    body: JSON.stringify({ topics, lastEventId, workspaceId }),
  });
}
