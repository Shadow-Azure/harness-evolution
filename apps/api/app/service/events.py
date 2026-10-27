"""In-memory SSE fan-out with bounded queues and replay/live handoff."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """One serialized Server-Sent Event notification."""

    event: str
    data: dict[str, Any]
    event_id: int | None = None
    topic: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    """One persisted event reconstructed by the replay boundary."""

    topic: str
    event_id: int
    event: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RunEventReplayResult:
    """Ordered replay page plus per-topic continuation and retention metadata."""

    events: tuple[ReplayEvent, ...] = ()
    stale_topics: tuple[str, ...] = ()
    next_cursors: Mapping[str, int] = field(default_factory=dict)
    has_more: bool = False


class RunEventReplay(Protocol):
    """Persistence boundary owned by the later evolution event repository."""

    async def read(
        self,
        topics: tuple[str, ...],
        cursors: Mapping[str, int],
        limit: int,
    ) -> RunEventReplayResult:
        """Return persisted events after each topic cursor and stale topic cursors."""


class RunEventRecorder(Protocol):
    """Persistence boundary used by recovery and functional run workers."""

    async def record_interrupted(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        job_id: str,
    ) -> int:
        """Persist one interruption event and return its run sequence, if supported."""


class RunTopicAuthorizer(Protocol):
    """Phase-owned resource authorization invoked before issuing SSE tickets."""

    async def authorize(self, topics: tuple[str, ...], *, user_id: str) -> None:
        """Reject topics whose resources are missing, complete, or not visible."""


class ShapeRunTopicAuthorizer:
    """M1 fallback that leaves resource existence to the future evolution repository."""

    async def authorize(self, topics: tuple[str, ...], *, user_id: str) -> None:
        """Accept syntactically validated topics until m5 installs its authorizer."""
        return None


@dataclass(slots=True)
class Subscription:
    """One SSE connection's shared queue across all authorized topics."""

    bus: "EventBus"
    topics: tuple[str, ...]
    queue: asyncio.Queue[SSEEvent]
    closed: bool = field(default=False)

    async def close(self) -> None:
        """Remove this connection from every topic exactly once."""
        if self.closed:
            return
        self.closed = True
        self.bus._remove(self)


class EventBus:
    """Fan out run notifications without ever blocking a producer."""

    def __init__(self, queue_capacity: int = 100) -> None:
        """Create a bus whose slowdown policy is bounded per connection."""
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive")
        self._queue_capacity = queue_capacity
        self._by_topic: dict[str, set[asyncio.Queue[SSEEvent]]] = defaultdict(set)
        self._subscriptions: dict[asyncio.Queue[SSEEvent], Subscription] = {}
        self._closed = False

    @property
    def subscriber_count(self) -> int:
        """Return the number of live SSE connections, not topic memberships."""
        return len(self._subscriptions)

    async def subscribe(self, topics: tuple[str, ...]) -> Subscription:
        """Create one queue and attach it to every authorized topic."""
        if self._closed:
            raise RuntimeError("event bus is closed")
        unique_topics = tuple(dict.fromkeys(topics))
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=self._queue_capacity)
        subscription = Subscription(bus=self, topics=unique_topics, queue=queue)
        self._subscriptions[queue] = subscription
        for topic in unique_topics:
            self._by_topic[topic].add(queue)
        return subscription

    def publish(
        self,
        topic: str,
        event: str,
        data: Mapping[str, Any],
        *,
        event_id: int | None = None,
    ) -> None:
        """Queue one event for each subscriber; drop the oldest on queue overflow."""
        if self._closed:
            return
        item = SSEEvent(
            event=event,
            data=dict(data),
            event_id=event_id,
            topic=topic,
        )
        for queue in tuple(self._by_topic.get(topic, ())):
            if queue.full():
                items: list[SSEEvent] = []
                while not queue.empty():
                    items.append(queue.get_nowait())
                progress_index = next(
                    (index for index, queued in enumerate(items) if queued.event == "run.progress"),
                    None,
                )
                if progress_index is None:
                    for queued in items:
                        queue.put_nowait(queued)
                    subscription = self._subscriptions.get(queue)
                    if subscription is not None:
                        subscription.closed = True
                        self._remove(subscription)
                    logger.warning(
                        "closing slow SSE subscriber rather than dropping critical events",
                        extra={"topic": topic, "event": event},
                    )
                    continue
                items.pop(progress_index)
                for queued in items:
                    queue.put_nowait(queued)
                logger.warning(
                    "compacting progress notification for slow subscriber",
                    extra={"topic": topic, "event": event},
                )
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning(
                    "SSE notification dropped at bounded queue",
                    extra={"topic": topic, "event": event},
                )

    async def close(self) -> None:
        """Close every subscription and reject future publishers."""
        self._closed = True
        for subscription in tuple(self._subscriptions.values()):
            await subscription.close()

    def _remove(self, subscription: Subscription) -> None:
        """Remove a subscription from the reverse indexes."""
        self._subscriptions.pop(subscription.queue, None)
        for topic in subscription.topics:
            queues = self._by_topic.get(topic)
            if queues is None:
                continue
            queues.discard(subscription.queue)
            if not queues:
                self._by_topic.pop(topic, None)


async def stream_events(
    *,
    bus: EventBus,
    replay: RunEventReplay,
    topics: tuple[str, ...],
    cursor: int,
    heartbeat_seconds: float,
    replay_limit: int,
) -> AsyncGenerator[SSEEvent, None]:
    """Replay persisted history before live events while suppressing handoff duplicates."""
    subscription = await bus.subscribe(topics)
    highest_event = dict.fromkeys(topics, cursor)
    replay_cursors = dict.fromkeys(topics, cursor)
    reset_topics: set[str] = set()
    try:
        while True:
            previous_cursors = dict(replay_cursors)
            page = await replay.read(topics, replay_cursors, replay_limit)
            for topic in page.stale_topics:
                if topic in reset_topics:
                    continue
                reset_topics.add(topic)
                run_id = topic.removeprefix("run:")
                yield SSEEvent(
                    event="reset",
                    data={"runId": run_id, "reason": "cursor_expired"},
                    topic=topic,
                )
            for replayed in sorted(page.events, key=lambda item: item.event_id):
                highest_event[replayed.topic] = max(
                    highest_event.get(replayed.topic, cursor),
                    replayed.event_id,
                )
                replay_cursors[replayed.topic] = max(
                    replay_cursors.get(replayed.topic, cursor),
                    replayed.event_id,
                )
                yield SSEEvent(
                    event=replayed.event,
                    data=dict(replayed.data),
                    event_id=replayed.event_id,
                    topic=replayed.topic,
                )
            for topic, next_cursor in page.next_cursors.items():
                replay_cursors[topic] = max(
                    replay_cursors.get(topic, cursor),
                    next_cursor,
                )
            if not page.has_more:
                break
            if replay_cursors == previous_cursors:
                raise RuntimeError("run event replay reported more pages without advancing")

        while True:
            if subscription.closed and subscription.queue.empty():
                return
            try:
                item = await asyncio.wait_for(
                    subscription.queue.get(),
                    timeout=heartbeat_seconds,
                )
            except TimeoutError:
                if subscription.closed and subscription.queue.empty():
                    return
                yield SSEEvent(event="ping", data={})
                continue
            if item.topic is None:
                yield item
                continue
            previous = highest_event.get(item.topic, cursor)
            if (
                item.event == "run.event"
                and item.event_id is not None
                and item.event_id <= previous
            ):
                continue
            if item.event == "run.event" and item.event_id is not None:
                highest_event[item.topic] = item.event_id
            yield item
    finally:
        await subscription.close()
