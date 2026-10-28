import type { EventTicketResponse } from "@harness/contracts";

import { request } from "./http";

/**
 * Bind one run topic and replay cursor to a single-use SSE ticket.
 * @param topics Authorized topics, usually `["run:<runId>"]`.
 * @param lastEventId Highest durable event sequence already rendered by REST.
 * @returns The opaque ticket, its lifetime, and the granted topics.
 */
export function requestEventTicket(
  topics: string[],
  lastEventId = 0,
): Promise<EventTicketResponse> {
  return request<EventTicketResponse>("/api/events/ticket", {
    method: "POST",
    body: JSON.stringify({ topics, lastEventId }),
  });
}
