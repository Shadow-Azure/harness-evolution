"""Event bus backpressure, replay handoff, heartbeat, and cleanup."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.service.events import (
    EventBus,
    ReplayEvent,
    RunEventReplayResult,
    SSEEvent,
    stream_events,
)


@dataclass
class StaticReplay:
    """Deterministic replay reader used to verify the SSE orchestration contract."""

    result: RunEventReplayResult

    async def read(
        self,
        topics: tuple[str, ...],
        cursors: Mapping[str, int],
        limit: int,
    ) -> RunEventReplayResult:
        """Return the configured database-like replay page."""
        return self.result


@dataclass
class PagedReplay:
    """Replay source that exposes one persisted event per requested page."""

    pages: list[RunEventReplayResult]
    cursors: list[dict[str, int]] | None = None

    def __post_init__(self) -> None:
        """Initialize the requested cursor history."""
        self.cursors = []

    async def read(
        self,
        topics: tuple[str, ...],
        cursors: Mapping[str, int],
        limit: int,
    ) -> RunEventReplayResult:
        """Return the next configured page while recording each cursor."""
        assert self.cursors is not None
        self.cursors.append(dict(cursors))
        return self.pages.pop(0)


async def test_event_bus_fans_out_by_topic_and_drops_oldest_when_full() -> None:
    """Slow consumers never block producers and retain the newest notifications."""
    bus = EventBus(queue_capacity=2)
    left = await bus.subscribe(("run:a",))
    right = await bus.subscribe(("run:b",))
    try:
        bus.publish("run:a", "run.progress", {"step": 1}, event_id=1)
        bus.publish("run:a", "run.progress", {"step": 2}, event_id=2)
        bus.publish("run:a", "run.progress", {"step": 3}, event_id=3)
        bus.publish("run:b", "run.progress", {"step": 9}, event_id=9)

        assert [left.queue.get_nowait().event_id for _ in range(2)] == [2, 3]
        assert right.queue.get_nowait().event_id == 9
        assert right.queue.empty()
    finally:
        await left.close()
        await right.close()
        await bus.close()


async def test_stream_replays_then_switches_to_live_without_duplicates() -> None:
    """A subscription is opened before replay so the handoff loses no event."""
    bus = EventBus(queue_capacity=10)
    replay = StaticReplay(
        RunEventReplayResult(
            events=(
                ReplayEvent(
                    topic="run:r1",
                    event_id=2,
                    event="run.event",
                    data={"runId": "r1", "seq": 2},
                ),
                ReplayEvent(
                    topic="run:r1",
                    event_id=3,
                    event="run.event",
                    data={"runId": "r1", "seq": 3},
                ),
            ),
            stale_topics=(),
        ),
    )
    stream = stream_events(
        bus=bus,
        replay=replay,
        topics=("run:r1",),
        cursor=1,
        heartbeat_seconds=60,
        replay_limit=100,
    )
    try:
        first = await anext(stream)
        assert (first.event_id, first.event) == (2, "run.event")
        bus.publish("run:r1", "run.event", {"runId": "r1", "seq": 2}, event_id=2)
        bus.publish("run:r1", "run.progress", {"runId": "r1", "unit": 4}, event_id=4)
        second = await anext(stream)
        third = await anext(stream)

        assert second.event_id == 3
        assert third.event_id == 4
        assert third.event == "run.progress"
    finally:
        await stream.aclose()
        await bus.close()


async def test_stream_replays_every_page_before_live_events() -> None:
    """A page limit bounds each read but never truncates persisted history."""
    bus = EventBus(queue_capacity=10)
    replay = PagedReplay(
        pages=[
            RunEventReplayResult(
                events=(
                    ReplayEvent(
                        topic="run:r1",
                        event_id=1,
                        event="run.event",
                        data={"runId": "r1", "seq": 1},
                    ),
                ),
                has_more=True,
                next_cursors={"run:r1": 1},
            ),
            RunEventReplayResult(
                events=(
                    ReplayEvent(
                        topic="run:r1",
                        event_id=2,
                        event="run.event",
                        data={"runId": "r1", "seq": 2},
                    ),
                ),
                has_more=False,
            ),
        ],
    )
    stream = stream_events(
        bus=bus,
        replay=replay,
        topics=("run:r1",),
        cursor=0,
        heartbeat_seconds=60,
        replay_limit=1,
    )
    try:
        first = await anext(stream)
        second = await anext(stream)
        bus.publish(
            "run:r1",
            "run.progress",
            {"runId": "r1", "percent": 50},
            event_id=3,
        )
        third = await anext(stream)
    finally:
        await stream.aclose()
        await bus.close()

    assert [first.event_id, second.event_id, third.event_id] == [1, 2, 3]
    assert replay.cursors == [{"run:r1": 0}, {"run:r1": 1}]


async def test_stream_emits_ping_after_idle_and_cleans_subscription() -> None:
    """Idle connections receive the documented ping event and disconnect cleanly."""
    bus = EventBus(queue_capacity=10)
    stream = stream_events(
        bus=bus,
        replay=StaticReplay(RunEventReplayResult(events=(), stale_topics=())),
        topics=("run:r1",),
        cursor=0,
        heartbeat_seconds=0.01,
        replay_limit=100,
    )
    try:
        heartbeat = await anext(stream)
        assert heartbeat.event == "ping"
        assert heartbeat.data == {}
        assert heartbeat.event_id is None
    finally:
        await stream.aclose()
        await bus.close()
    assert bus.subscriber_count == 0


async def test_stream_emits_reset_for_stale_cursor() -> None:
    """A retention gap asks the client to reload REST state instead of silently skipping."""
    bus = EventBus(queue_capacity=10)
    stream = stream_events(
        bus=bus,
        replay=StaticReplay(
            RunEventReplayResult(events=(), stale_topics=("run:r1",)),
        ),
        topics=("run:r1",),
        cursor=1,
        heartbeat_seconds=60,
        replay_limit=100,
    )
    try:
        reset = await anext(stream)
        assert isinstance(reset, SSEEvent)
        assert reset.event == "reset"
        assert reset.data == {"runId": "r1", "reason": "cursor_expired"}
    finally:
        await stream.aclose()
        await bus.close()
