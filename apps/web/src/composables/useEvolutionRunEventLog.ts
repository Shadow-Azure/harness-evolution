import type {
  EvolutionRunEvent,
  EvolutionRunEventLevel,
} from "@harness/contracts";
import { computed, ref, watch, type MaybeRefOrGetter } from "vue";
import { toValue } from "vue";

import { listEvolutionRunEvents } from "../api/evolutionRuns";

/**
 * Merge one event page without duplicating cursors or SSE replays.
 * @param current Existing sequence-ordered events.
 * @param incoming New events from REST or live notification.
 * @returns A fresh sequence-ordered list.
 */
export function mergeRunEvents(
  current: readonly EvolutionRunEvent[],
  incoming: readonly EvolutionRunEvent[],
): EvolutionRunEvent[] {
  const bySequence = new Map<number, EvolutionRunEvent>();
  for (const event of [...current, ...incoming]) bySequence.set(event.seq, event);
  return [...bySequence.values()].sort((left, right) => left.seq - right.seq);
}

/**
 * Load and paginate durable execution-log events for one run.
 * @param runId Evolution run identifier.
 * @param level Active severity filter.
 * @param enabled Whether the log tab is visible.
 * @returns Observable event state and refresh/load-more actions.
 */
export function useEvolutionRunEventLog(
  runId: MaybeRefOrGetter<string>,
  level: MaybeRefOrGetter<EvolutionRunEventLevel | undefined>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  const items = ref<EvolutionRunEvent[]>([]);
  const nextSeq = ref(0);
  const hasMore = ref(false);
  const isPending = ref(false);
  const error = ref<unknown>(null);
  const appendError = ref<unknown>(null);
  let requestGeneration = 0;
  let snapshotKey = "";

  function resetSnapshot(): void {
    items.value = [];
    nextSeq.value = 0;
    hasMore.value = false;
    isPending.value = false;
    error.value = null;
    appendError.value = null;
  }

  async function refresh(): Promise<void> {
    if (!toValue(enabled) || !toValue(runId)) return;
    const generation = ++requestGeneration;
    isPending.value = true;
    error.value = null;
    appendError.value = null;
    try {
      const page = await listEvolutionRunEvents(toValue(runId), {
        afterSeq: 0,
        limit: 100,
        level: toValue(level),
      });
      if (generation !== requestGeneration) return;
      items.value = mergeRunEvents([], page.items);
      nextSeq.value = page.nextSeq;
      hasMore.value = page.hasMore;
    } catch (caught) {
      if (generation === requestGeneration) error.value = caught;
    } finally {
      if (generation === requestGeneration) isPending.value = false;
    }
  }

  async function loadMore(): Promise<void> {
    if (!toValue(enabled) || !hasMore.value || isPending.value) return;
    const generation = requestGeneration;
    isPending.value = true;
    appendError.value = null;
    try {
      const page = await listEvolutionRunEvents(toValue(runId), {
        afterSeq: nextSeq.value,
        limit: 100,
        level: toValue(level),
      });
      if (generation !== requestGeneration) return;
      items.value = mergeRunEvents(items.value, page.items);
      nextSeq.value = page.hasMore ? page.nextSeq : Math.max(nextSeq.value, page.nextSeq);
      hasMore.value = page.hasMore;
    } catch (caught) {
      if (generation === requestGeneration) appendError.value = caught;
    } finally {
      if (generation === requestGeneration) isPending.value = false;
    }
  }

  watch(
    [() => toValue(runId), () => toValue(level), () => toValue(enabled)],
    ([currentRun, currentLevel, visible]) => {
      const nextSnapshotKey = `${currentRun ?? ""}\0${currentLevel ?? ""}`;
      if (nextSnapshotKey !== snapshotKey) {
        snapshotKey = nextSnapshotKey;
        requestGeneration += 1;
        resetSnapshot();
      }
      if (visible && currentRun) void refresh();
    },
    { immediate: true },
  );

  return {
    items: computed(() => items.value),
    nextSeq: computed(() => nextSeq.value),
    hasMore: computed(() => hasMore.value),
    isPending: computed(() => isPending.value),
    error: computed(() => error.value),
    appendError: computed(() => appendError.value),
    refresh,
    loadMore,
  };
}
