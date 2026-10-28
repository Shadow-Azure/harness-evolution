import type {
  EvolutionRunEvent,
  EventTicketResponse,
} from "@harness/contracts";
import { useQueryClient } from "@tanstack/vue-query";
import {
  onUnmounted,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from "vue";

import { requestEventTicket } from "../api/events";
import { queryKeys } from "../api/queryKeys";

/** Run-level lifecycle payload sent beside durable `run.event` frames. */
export interface RunLifecycleNotice {
  runId?: string;
  stage?: string;
  blockedStage?: "patch" | "push" | "eval" | null;
  retryAttempts?: number;
  nextRetryAt?: string | null;
  message?: string;
  reason?: string;
}

/** Optional consumers for live run notifications. */
export interface UseRunEventsHandlers {
  onEvent?: (event: EvolutionRunEvent) => void;
  onProgress?: () => void;
  onBlocked?: (notice: RunLifecycleNotice) => void;
  onCompleted?: (notice: RunLifecycleNotice) => void;
  onFailed?: (notice: RunLifecycleNotice) => void;
  onInterrupted?: (notice: RunLifecycleNotice) => void;
  onReset?: (notice: RunLifecycleNotice) => void;
}

/** Constructor compatible with the browser `EventSource`. */
export type EventSourceConstructor = new (url: string) => EventSource;

/** Injectable browser capabilities used to keep the composable deterministic. */
export interface UseRunEventsOptions {
  /** Alternative EventSource constructor; defaults to the global one. */
  eventSource?: EventSourceConstructor;
  /** Ticket request used before opening a stream. */
  requestTicket?: (
    topics: string[],
    lastEventId: number,
  ) => Promise<EventTicketResponse>;
  /** Delay before a failed stream asks for a fresh ticket. */
  reconnectDelayMs?: number;
  /** Timer used for reconnects; defaults to the global `setTimeout`. */
  setTimeoutFn?: (callback: () => void, delayMs: number) => unknown;
  /** Timer cancellation paired with `setTimeoutFn`. */
  clearTimeoutFn?: (handle: unknown) => void;
}

function parseRunEvent(data: unknown): EvolutionRunEvent | null {
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed === null || typeof parsed !== "object") return null;
    const seq = (parsed as { seq?: unknown }).seq;
    return typeof seq === "number" ? (parsed as EvolutionRunEvent) : null;
  } catch {
    return null;
  }
}

function parseLifecycleNotice(data: unknown): RunLifecycleNotice {
  if (typeof data !== "string") return {};
  try {
    const parsed: unknown = JSON.parse(data);
    return parsed !== null && typeof parsed === "object"
      ? (parsed as RunLifecycleNotice)
      : {};
  } catch {
    return {};
  }
}

/**
 * Subscribe one run detail page to live SSE events.
 *
 * The stream owns run activity only: it asks for a single-use ticket bound to
 * `run:<runId>` and the already-loaded cursor, appends durable `run.event`
 * frames, invalidates the run query on progress, and closes on every terminal
 * state. A dropped connection retries with a fresh ticket after three seconds
 * so the cursor stays authoritative. Page restarts (`reset`) close the stream
 * and hand control back to the REST snapshot.
 * @param rid Evolution run identifier.
 * @param loadedSeq Highest durable event sequence already rendered, advanced in place.
 * @param isActive Whether the run is preparing or running and may be subscribed.
 * @param handlers Optional live-notification callbacks.
 * @param options Injectable EventSource, ticket request, and reconnect timer.
 * @returns No value; cleanup is registered on the owning component.
 */
export function useRunEvents(
  rid: MaybeRefOrGetter<string>,
  loadedSeq: Ref<number>,
  isActive: MaybeRefOrGetter<boolean>,
  handlers: UseRunEventsHandlers = {},
  options: UseRunEventsOptions = {},
): void {
  const queryClient = useQueryClient();
  const eventSourceFactory = options.eventSource ?? globalThis.EventSource;
  const requestTicket = options.requestTicket ?? requestEventTicket;
  const reconnectDelayMs = options.reconnectDelayMs ?? 3_000;
  const scheduleTimer =
    options.setTimeoutFn ??
    ((callback: () => void, delayMs: number) =>
      globalThis.setTimeout(callback, delayMs));
  const cancelTimer =
    options.clearTimeoutFn ??
    ((handle: unknown) =>
      globalThis.clearTimeout(handle as Parameters<typeof clearTimeout>[0]));

  let source: EventSource | null = null;
  let generation = 0;
  let closed = false;
  let reconnectHandle: unknown = null;

  function invalidateRun(): void {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.evolutionRun(toValue(rid)),
    });
  }

  function closeSource(): void {
    if (source === null) return;
    source.close();
    source = null;
  }

  function cancelReconnect(): void {
    if (reconnectHandle === null) return;
    cancelTimer(reconnectHandle);
    reconnectHandle = null;
  }

  function scheduleReconnect(attempt: number): void {
    if (closed || attempt !== generation || !toValue(isActive)) return;
    cancelReconnect();
    reconnectHandle = scheduleTimer(() => {
      reconnectHandle = null;
      if (closed || !toValue(isActive)) return;
      void connect();
    }, reconnectDelayMs);
  }

  function handleEventMessage(data: unknown): void {
    if (closed) return;
    const event = parseRunEvent(data);
    if (event === null) return;
    if (event.seq > loadedSeq.value) loadedSeq.value = event.seq;
    handlers.onEvent?.(event);
  }

  function registerLifecycle(
    target: EventSource,
    type: string,
    callback: ((notice: RunLifecycleNotice) => void) | undefined,
    terminal: boolean,
  ): void {
    target.addEventListener(type, (event) => {
      if (terminal) closed = true;
      closeSource();
      invalidateRun();
      callback?.(parseLifecycleNotice((event as MessageEvent).data));
    });
  }

  async function connect(): Promise<void> {
    if (closed || !toValue(isActive) || source !== null) return;
    if (!eventSourceFactory) return;
    const runId = toValue(rid);
    if (!runId) return;
    const attempt = ++generation;
    let ticket: EventTicketResponse;
    try {
      ticket = await requestTicket([`run:${runId}`], loadedSeq.value);
    } catch {
      scheduleReconnect(attempt);
      return;
    }
    if (closed || attempt !== generation || !toValue(isActive) || source !== null) {
      return;
    }
    const next = new eventSourceFactory(
      `/api/events?ticket=${encodeURIComponent(ticket.ticket)}`,
    );
    source = next;

    next.addEventListener("run.event", (event) => {
      handleEventMessage((event as MessageEvent).data);
    });
    next.addEventListener("run.progress", () => {
      invalidateRun();
      handlers.onProgress?.();
    });
    registerLifecycle(next, "run.blocked", handlers.onBlocked, false);
    registerLifecycle(next, "run.completed", handlers.onCompleted, true);
    registerLifecycle(next, "run.failed", handlers.onFailed, true);
    registerLifecycle(next, "run.interrupted", handlers.onInterrupted, true);
    next.addEventListener("reset", (event) => {
      closeSource();
      handlers.onReset?.(parseLifecycleNotice((event as MessageEvent).data));
    });
    next.onerror = () => {
      closeSource();
      if (closed || !toValue(isActive)) return;
      scheduleReconnect(generation);
    };
  }

  watch(
    [() => toValue(isActive), () => toValue(rid)],
    ([active]) => {
      generation += 1;
      cancelReconnect();
      closeSource();
      if (active) void connect();
    },
    { immediate: true },
  );

  onUnmounted(() => {
    closed = true;
    generation += 1;
    cancelReconnect();
    closeSource();
  });
}
