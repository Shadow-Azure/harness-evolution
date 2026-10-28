// @vitest-environment jsdom

import type { EventTicketResponse } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type Mock,
  type MockInstance,
} from "vitest";
import {
  defineComponent,
  nextTick,
  ref,
  type PropType,
  type Ref,
} from "vue";

import { queryKeys } from "../api/queryKeys";
import {
  useRunEvents,
  type EventSourceConstructor,
  type UseRunEventsHandlers,
  type UseRunEventsOptions,
} from "./useRunEvents";

interface ScheduledTimer {
  callback: () => void;
  delay: number;
  cancelled: boolean;
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<string, Array<(event: Event) => void>>();
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ): void {
    const listenerFn =
      typeof listener === "function"
        ? listener
        : (event: Event) => listener.handleEvent(event);
    const bucket = this.listeners.get(type) ?? [];
    bucket.push(listenerFn);
    this.listeners.set(type, bucket);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    this.emitRaw(type, JSON.stringify(data));
  }

  emitRaw(type: string, data: string): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data } as MessageEvent);
    }
  }

  fail(): void {
    this.onerror?.(new Event("error"));
  }

  static latest(): FakeEventSource {
    const latest = this.instances.at(-1);
    if (!latest) throw new Error("no EventSource was opened");
    return latest;
  }
}

interface Harness {
  wrapper: VueWrapper;
  client: QueryClient;
  invalidate: MockInstance;
  loadedSeq: Ref<number>;
  active: Ref<boolean>;
  runId: Ref<string>;
  requestTicket: Mock;
  timers: ScheduledTimer[];
}

const wrappers: VueWrapper[] = [];

function eventPayload(seq: number) {
  return {
    seq,
    eventType: "eval_completed",
    level: "info",
    stage: "eval",
    stepIndex: 4,
    clusterId: null,
    roundId: null,
    jobId: null,
    message: `事件 ${seq}`,
    createdAt: "2026-10-28T12:00:00+08:00",
    payload: null,
    error: null,
  };
}

interface EventsHarnessState {
  runId: Ref<string>;
  loadedSeq: Ref<number>;
  active: Ref<boolean>;
  handlers: UseRunEventsHandlers;
  options: UseRunEventsOptions;
}

const EventsHarness = defineComponent({
  props: {
    state: {
      type: Object as PropType<EventsHarnessState>,
      required: true,
    },
  },
  setup(props) {
    useRunEvents(
      props.state.runId,
      props.state.loadedSeq,
      props.state.active,
      props.state.handlers,
      props.state.options,
    );
    return () => null;
  },
});

function mountEvents(
  handlers: UseRunEventsHandlers = {},
  overrides: Partial<UseRunEventsOptions> = {},
): Harness {
  const client = new QueryClient({
    defaultOptions: { queries: { gcTime: 0, retry: false } },
  });
  const invalidate = vi
    .spyOn(client, "invalidateQueries")
    .mockResolvedValue(undefined);
  const loadedSeq = ref(0);
  const active = ref(true);
  const runId = ref("run-1");
  const requestTicket = vi.fn(
    async (topics: string[], lastEventId: number): Promise<EventTicketResponse> => {
      void lastEventId;
      return {
        ticket: `ticket-${requestTicket.mock.calls.length}`,
        expiresIn: 60,
        topics,
      };
    },
  );
  const timers: ScheduledTimer[] = [];
  const options: UseRunEventsOptions = {
    eventSource: FakeEventSource as unknown as EventSourceConstructor,
    requestTicket,
    reconnectDelayMs: 3_000,
    setTimeoutFn: (callback, delayMs) => {
      const timer: ScheduledTimer = {
        callback,
        delay: delayMs,
        cancelled: false,
      };
      timers.push(timer);
      return timer;
    },
    clearTimeoutFn: (handle) => {
      (handle as ScheduledTimer).cancelled = true;
    },
    ...overrides,
  };

  const state: EventsHarnessState = {
    runId,
    loadedSeq,
    active,
    handlers,
    options,
  };
  const wrapper = mount(EventsHarness, {
    props: { state },
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  });
  wrappers.push(wrapper);
  return {
    wrapper,
    client,
    invalidate,
    loadedSeq,
    active,
    runId,
    requestTicket:
      (overrides.requestTicket as unknown as Mock | undefined) ?? requestTicket,
    timers,
  };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", undefined);
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useRunEvents", () => {
  it("requests a ticket for the run cursor and opens the stream", async () => {
    const harness = mountEvents();

    await flushPromises();

    expect(harness.requestTicket).toHaveBeenCalledWith(["run:run-1"], 0);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.latest().url).toBe("/api/events?ticket=ticket-1");
  });

  it("appends run events and advances the replay cursor", async () => {
    const onEvent = vi.fn();
    const harness = mountEvents({ onEvent });
    await flushPromises();

    FakeEventSource.latest().emit("run.event", eventPayload(7));

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ seq: 7, message: "事件 7" }),
    );
    expect(harness.loadedSeq.value).toBe(7);
  });

  it("ignores malformed run.event frames without moving the cursor", async () => {
    const onEvent = vi.fn();
    const harness = mountEvents({ onEvent });
    await flushPromises();

    FakeEventSource.latest().emitRaw("run.event", "{not-json");
    FakeEventSource.latest().emit("run.event", { message: "no seq" });

    expect(onEvent).not.toHaveBeenCalled();
    expect(harness.loadedSeq.value).toBe(0);
  });

  it("invalidates the run prefix and notifies progress", async () => {
    const onProgress = vi.fn();
    const harness = mountEvents({ onProgress });
    await flushPromises();

    FakeEventSource.latest().emit("run.progress", { runId: "run-1" });
    await flushPromises();

    expect(onProgress).toHaveBeenCalledTimes(1);
    expect(harness.invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.evolutionRun("run-1"),
    });
  });

  it("closes and invalidates a blocked run without ending the subscription", async () => {
    const onBlocked = vi.fn();
    const harness = mountEvents({ onBlocked });
    await flushPromises();
    const source = FakeEventSource.latest();

    source.emit("run.blocked", {
      runId: "run-1",
      blockedStage: "eval",
      retryAttempts: 1,
      nextRetryAt: "2026-10-28T12:05:00+08:00",
    });
    await flushPromises();

    expect(source.closed).toBe(true);
    expect(onBlocked).toHaveBeenCalledWith(
      expect.objectContaining({ blockedStage: "eval", retryAttempts: 1 }),
    );
    expect(harness.invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.evolutionRun("run-1"),
    });
    expect(harness.timers).toHaveLength(0);
  });

  it.each(["run.completed", "run.failed", "run.interrupted"])(
    "closes permanently after %s",
    async (terminal) => {
      const handler = vi.fn();
      mountEvents({
        onCompleted: terminal === "run.completed" ? handler : undefined,
        onFailed: terminal === "run.failed" ? handler : undefined,
        onInterrupted: terminal === "run.interrupted" ? handler : undefined,
      });
      await flushPromises();
      const source = FakeEventSource.latest();

      source.emit(terminal, { runId: "run-1" });
      source.fail();

      expect(source.closed).toBe(true);
      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({ runId: "run-1" }),
      );
      expect(FakeEventSource.instances).toHaveLength(1);
    },
  );

  it("re-requests a ticket for a fresh stream after the socket drops", async () => {
    const harness = mountEvents();
    await flushPromises();
    const first = FakeEventSource.latest();
    first.emit("run.event", eventPayload(5));

    first.fail();

    expect(first.closed).toBe(true);
    expect(harness.timers).toHaveLength(1);
    expect(harness.timers[0]?.delay).toBe(3_000);

    harness.timers[0]?.callback();
    await flushPromises();

    expect(harness.requestTicket).toHaveBeenNthCalledWith(
      2,
      ["run:run-1"],
      5,
    );
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it("closes and reports a cursor reset for a REST reload", async () => {
    const onReset = vi.fn();
    mountEvents({ onReset });
    await flushPromises();
    const source = FakeEventSource.latest();

    source.emit("reset", { runId: "run-1", reason: "cursor_expired" });

    expect(source.closed).toBe(true);
    expect(onReset).toHaveBeenCalledWith(
      expect.objectContaining({ reason: "cursor_expired" }),
    );
  });

  it("retries the ticket request when it fails", async () => {
    const requestTicket = vi
      .fn()
      .mockRejectedValueOnce(new Error("ticket expired"))
      .mockResolvedValue({
        ticket: "ticket-late",
        expiresIn: 60,
        topics: ["run:run-1"],
      });
    const harness = mountEvents({}, { requestTicket });

    await flushPromises();

    expect(requestTicket).toHaveBeenCalledTimes(1);
    expect(harness.timers).toHaveLength(1);

    harness.timers[0]?.callback();
    await flushPromises();

    expect(requestTicket).toHaveBeenCalledTimes(2);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.latest().url).toBe("/api/events?ticket=ticket-late");
  });

  it("unsubscribes when the run becomes inactive and resubscribes later", async () => {
    const harness = mountEvents();
    await flushPromises();
    const first = FakeEventSource.latest();

    harness.active.value = false;
    await nextTick();
    expect(first.closed).toBe(true);

    harness.active.value = true;
    await flushPromises();

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(harness.requestTicket).toHaveBeenCalledTimes(2);
  });

  it("closes the stream and cancels pending reconnects on unmount", async () => {
    const harness = mountEvents();
    await flushPromises();
    const source = FakeEventSource.latest();
    source.fail();
    const timer = harness.timers[0];

    harness.wrapper.unmount();
    expect(source.closed).toBe(true);
    expect(timer?.cancelled).toBe(true);

    timer?.callback();
    await flushPromises();

    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("stays inert when the browser has no EventSource", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { gcTime: 0, retry: false } },
    });
    const requestTicket = vi.fn();
    const state: EventsHarnessState = {
      runId: ref("run-1"),
      loadedSeq: ref(0),
      active: ref(true),
      handlers: {},
      options: { requestTicket },
    };
    const wrapper = mount(EventsHarness, {
      props: { state },
      global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
    });
    wrappers.push(wrapper);

    await flushPromises();

    expect(requestTicket).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
