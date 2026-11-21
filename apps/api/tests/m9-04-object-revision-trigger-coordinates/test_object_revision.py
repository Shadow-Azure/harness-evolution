"""M9-04 object revision resolution from tags, bodies, digests, and evidence."""

from __future__ import annotations

import json
from typing import Literal

from app.service.acquisition.agent_tree import assemble_agent_trees
from app.service.acquisition.normalize import ParsedTranscript, normalize_transcript
from app.utils.time import SHANGHAI

ROOT_ID = "50000000-0000-4000-8000-000000000001"
CHILD_ID = "agent-revision-child"
CHILD_TWO_ID = "agent-revision-child-two"
SKILL_PATH = "/workspace/.claude/skills/review"
SKILL_BODY = "# Synthetic review\n\nOnly inspect synthetic inputs."
LISTING_DIGEST = "0123456789abcdef"


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(text: str = "synthetic task", *, agent_id: str = ROOT_ID) -> dict[str, object]:
    """Build one user turn with an explicit timestamp."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "agentId": agent_id,
        "timestamp": "2026-11-16T01:00:00Z",
        "message": {"content": text},
    }


def assistant(
    message_id: str,
    *,
    tools: tuple[tuple[str, str, dict[str, object]], ...] = (),
    timestamp: str = "2026-11-16T01:01:00Z",
    attribution_skill: str | None = None,
) -> dict[str, object]:
    """Build one assistant record with optional explicit and attribution evidence."""
    content: list[dict[str, object]] = [{"type": "text", "text": "synthetic answer"}]
    for tool_id, name, tool_input in tools:
        content.append(
            {
                "type": "tool_use",
                "id": tool_id,
                "name": name,
                "input": tool_input,
            },
        )
    record: dict[str, object] = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": "model-main",
            "stop_reason": "end_turn",
            "content": content,
            "usage": {"input_tokens": 4, "output_tokens": 2},
        },
    }
    if attribution_skill is not None:
        record["attributionSkill"] = attribution_skill
    return record


def skill_injection(
    tool_use_id: str,
    *,
    path: str = SKILL_PATH,
    body: str = SKILL_BODY,
    timestamp: str = "2026-11-16T01:02:00Z",
) -> dict[str, object]:
    """Build the isMeta Skill body injection keyed by the Skill call identity."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "isMeta": True,
        "sourceToolUseID": tool_use_id,
        "message": {
            "content": f"Base directory for this skill: {path}\n\n{body}\n\n## Notes\nsuffix",
        },
    }


def skill_listing(*, names: list[str], digests: list[str]) -> dict[str, object]:
    """Build one opaque Skill listing attachment."""
    return {
        "type": "attachment",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:03:00Z",
        "attachment": {"type": "skill_listing", "names": names, "digests": digests},
    }


def prompt_snapshot(body: str, *, agent_id: str = CHILD_ID) -> dict[str, object]:
    """Build one injected child Agent definition."""
    return {
        "type": "prompt_snapshot",
        "sessionId": ROOT_ID,
        "agentId": agent_id,
        "systemPrompt": [body],
    }


def attachment_prompt_snapshot(body: str, *, agent_id: str = CHILD_ID) -> dict[str, object]:
    """Build the attachment-nested prompt snapshot shape observed in production."""
    return {
        "type": "attachment",
        "sessionId": ROOT_ID,
        "agentId": agent_id,
        "attachment": {"type": "prompt_snapshot", "systemPrompt": [body]},
    }


def parse(
    records: tuple[object, ...],
    *,
    agent_id: str = ROOT_ID,
    agent_kind: Literal["main", "subagent"] = "main",
    meta: dict[str, object] | None = None,
) -> ParsedTranscript:
    """Normalize one deterministic transcript."""
    return normalize_transcript(
        jsonl(*records),
        root_session_id=ROOT_ID,
        agent_id=agent_id,
        agent_kind=agent_kind,
        agent_meta=meta,
    )


def child_meta(
    *,
    agent_type: str = "reviewer",
    tool_use_id: str = "tool-agent",
    is_builtin: bool = False,
    description: str = "synthetic child",
) -> dict[str, object]:
    """Build one closed child metadata shape."""
    return {
        "agentType": agent_type,
        "description": description,
        "spawnDepth": 1,
        "toolUseId": tool_use_id,
        "isBuiltIn": is_builtin,
    }


def test_explicit_skill_version_becomes_tag_revision() -> None:
    """Explicit skillVersion is persisted and yields a tag revision."""
    parsed = parse(
        (
            user(),
            assistant(
                "message-1",
                tools=(("tool-skill", "Skill", {"skill": "review", "skillVersion": "v1.2.3"}),),
            ),
        ),
    )

    event = parsed.events[0]
    assert event.object_version == "v1.2.3"
    assert event.object_revision == "tag:v1.2.3"
    assert event.triggered_at is not None
    assert event.triggered_at.tzinfo == SHANGHAI
    assert event.triggered_at.hour == 9


def test_explicit_agent_version_becomes_tag_revision() -> None:
    """Agent call metadata supplies object_version and a tag revision."""
    parsed = parse(
        (
            user(),
            assistant(
                "message-1",
                tools=(
                    (
                        "tool-agent",
                        "Agent",
                        {"subagent_type": "reviewer", "agentVersion": "2026.1"},
                    ),
                ),
            ),
        ),
    )

    event = parsed.events[0]
    assert event.object_version == "2026.1"
    assert event.object_revision == "tag:2026.1"


def test_skill_body_revision_is_path_insensitive() -> None:
    """The normalized body alone identifies a Skill; the source path never does."""
    first = parse(
        (
            user("first task"),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "review"}),)),
            skill_injection("tool-skill"),
        ),
    )
    second = parse(
        (
            user("unrelated task"),
            assistant("message-2", tools=(("tool-skill", "Skill", {"skill": "review"}),)),
            skill_injection("tool-skill"),
        ),
    )
    moved = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "review"}),)),
            skill_injection("tool-skill", path="/workspace/other/skills/review"),
        ),
    )

    expected_revision = f"digest:{first.events[0].definition_hash}"
    assert first.events[0].object_revision == expected_revision
    assert second.events[0].object_revision == expected_revision
    assert moved.events[0].object_revision == expected_revision


def test_body_hash_wins_over_listing_digest() -> None:
    """A body hash is preferred even when the listing exposes a digest."""
    parsed = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "review"}),)),
            skill_injection("tool-skill"),
            skill_listing(names=["review"], digests=[LISTING_DIGEST]),
        ),
    )

    revision = parsed.events[0].object_revision
    assert revision is not None
    assert revision.startswith("digest:")
    assert revision != f"digest:{LISTING_DIGEST}"


def test_listing_digest_is_an_opaque_fallback() -> None:
    """Without a tag or body, the 16-hex listing digest is the fallback."""
    parsed = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "legacy"}),)),
            skill_listing(names=["legacy"], digests=[LISTING_DIGEST]),
        ),
    )

    assert parsed.events[0].object_revision == f"digest:{LISTING_DIGEST}"


def test_explicit_tag_without_version_becomes_tag_revision() -> None:
    """A tag is enough for a tag revision even when no semantic version exists."""
    parsed = parse(
        (
            user(),
            assistant(
                "message-1",
                tools=(("tool-skill", "Skill", {"skill": "review", "tag": "release-7"}),),
            ),
        ),
    )

    assert parsed.events[0].object_version is None
    assert parsed.events[0].object_revision == "tag:release-7"


def test_single_name_top_level_listing_digest_is_used_as_fallback() -> None:
    """A single-skill listing attachment may expose its digest at the top level."""
    parsed = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "legacy"}),)),
            {
                "type": "attachment",
                "sessionId": ROOT_ID,
                "timestamp": "2026-11-16T01:03:00Z",
                "attachment": {
                    "type": "skill_listing",
                    "names": ["legacy"],
                    "digest": LISTING_DIGEST,
                },
            },
        ),
    )

    assert parsed.events[0].object_revision == f"digest:{LISTING_DIGEST}"


def test_skill_listing_skills_and_content_shapes_are_supported() -> None:
    """Observed listing object and content-line shapes both yield fallbacks."""
    objects = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "legacy"}),)),
            {
                "type": "attachment",
                "sessionId": ROOT_ID,
                "timestamp": "2026-11-16T01:03:00Z",
                "attachment": {
                    "type": "skill_listing",
                    "skills": [{"name": "legacy", "digest": LISTING_DIGEST}],
                },
            },
        ),
    )
    content = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "legacy"}),)),
            {
                "type": "attachment",
                "sessionId": ROOT_ID,
                "timestamp": "2026-11-16T01:03:00Z",
                "attachment": {
                    "type": "skill_listing",
                    "content": f"- legacy: synthetic skill (digest: {LISTING_DIGEST})",
                },
            },
        ),
    )

    assert objects.events[0].object_revision == f"digest:{LISTING_DIGEST}"
    assert content.events[0].object_revision == f"digest:{LISTING_DIGEST}"


def test_missing_tag_body_and_digest_is_unknown() -> None:
    """No usable identity is recorded as explicit unknown, never by name."""
    parsed = parse(
        (
            user(),
            assistant("message-1", tools=(("tool-skill", "Skill", {"skill": "review"}),)),
        ),
    )

    assert parsed.events[0].object_version is None
    assert parsed.events[0].object_revision == "unknown"


def test_agent_revision_is_stable_across_tasks_and_attached_to_parent_event() -> None:
    """Agent identity is the definition body plus type, not the delegated task."""
    main = parse(
        (
            user(),
            assistant(
                "message-main",
                tools=(("tool-agent", "Agent", {"subagent_type": "reviewer"}),),
            ),
        ),
    )
    first = parse(
        (
            prompt_snapshot("You are a synthetic reviewer."),
            user("first delegated task"),
        ),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta=child_meta(),
    )
    second = parse(
        (
            prompt_snapshot("You are a synthetic reviewer."),
            user("a different delegated task"),
        ),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta=child_meta(),
    )

    assert first.agent_revision is not None
    assert first.agent_revision == second.agent_revision
    tree = assemble_agent_trees((main, first)).trees[0]
    parent = next(node for node in tree.nodes if node.kind == "main")
    assert parent.events[0].object_revision == first.agent_revision
    assert parent.events[0].definition_hash == first.agent_definition_hash


def test_attachment_definition_hash_reaches_parent_event_without_revision() -> None:
    """A child without agentType still contributes its body hash to the parent event."""
    main = parse(
        (
            user(),
            assistant(
                "message-main",
                tools=(("tool-agent", "Agent", {"subagent_type": "reviewer"}),),
            ),
        ),
    )
    child = parse(
        (
            attachment_prompt_snapshot("You are a synthetic reviewer."),
            user(),
        ),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta={"name": "synthetic reviewer"},
    )

    assert child.agent_definition_hash is not None
    assert child.agent_revision is None
    tree = assemble_agent_trees((main, child)).trees[0]
    parent = next(node for node in tree.nodes if node.kind == "main")
    child_node = next(node for node in tree.nodes if node.id == CHILD_ID)
    event = next(item for item in parent.events if item.tool_use_id == child_node.tool_use_id)
    assert event.definition_hash == child.agent_definition_hash
    assert event.object_revision == "unknown"


def test_attachment_definition_hash_yields_revision_and_parent_event() -> None:
    """The nested attachment shape feeds the existing revision and parent propagation."""
    main = parse(
        (
            user(),
            assistant(
                "message-main",
                tools=(("tool-agent", "Agent", {"subagent_type": "reviewer"}),),
            ),
        ),
    )
    child = parse(
        (
            attachment_prompt_snapshot("You are a synthetic reviewer."),
            user(),
        ),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta=child_meta(),
    )

    assert child.agent_definition_hash is not None
    assert child.agent_revision is not None
    tree = assemble_agent_trees((main, child)).trees[0]
    parent = next(node for node in tree.nodes if node.kind == "main")
    event = next(item for item in parent.events if item.kind == "agent")
    assert event.definition_hash == child.agent_definition_hash
    assert event.object_revision == child.agent_revision


def test_parent_tag_wins_while_child_definition_hash_still_propagates() -> None:
    """An explicit Agent tag stays the revision even without a child revision."""
    main = parse(
        (
            user(),
            assistant(
                "message-main",
                tools=(
                    (
                        "tool-agent",
                        "Agent",
                        {"subagent_type": "reviewer", "agentVersion": "2026.1"},
                    ),
                ),
            ),
        ),
    )
    child = parse(
        (
            attachment_prompt_snapshot("You are a synthetic reviewer."),
            user(),
        ),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta={"name": "synthetic reviewer", "toolUseId": "tool-agent", "spawnDepth": 1},
    )

    assert child.agent_definition_hash is not None
    assert child.agent_revision is None
    tree = assemble_agent_trees((main, child)).trees[0]
    parent = next(node for node in tree.nodes if node.kind == "main")
    event = parent.events[0]
    assert event.object_revision == "tag:2026.1"
    assert event.definition_hash == child.agent_definition_hash


def test_builtin_agent_revision_has_no_body_but_keeps_type_identity() -> None:
    """A builtin Agent hashes type and builtin marker without a definition body."""
    parsed = parse(
        (
            user(),
            assistant(
                "message-main",
                tools=(("tool-agent", "Agent", {"subagent_type": "Explore"}),),
            ),
        ),
    )
    explore = parse(
        (prompt_snapshot("unused"), user()),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta=child_meta(agent_type="Explore", is_builtin=True),
    )
    plan = parse(
        (prompt_snapshot("unused"), user()),
        agent_id=CHILD_TWO_ID,
        agent_kind="subagent",
        meta=child_meta(agent_type="Plan", is_builtin=True),
    )

    assert explore.agent_definition_hash is None
    assert explore.agent_revision is not None
    assert explore.agent_revision != plan.agent_revision
    tree = assemble_agent_trees((parsed, explore)).trees[0]
    parent = next(node for node in tree.nodes if node.kind == "main")
    assert parent.events[0].object_revision == explore.agent_revision


def test_non_builtin_agent_without_body_stays_unknown() -> None:
    """A missing prompt_snapshot body cannot be guessed from the type name."""
    child = parse(
        (user(),),
        agent_id=CHILD_ID,
        agent_kind="subagent",
        meta=child_meta(),
    )

    assert child.agent_revision is None


def test_attribution_skill_does_not_replace_explicit_trigger() -> None:
    """attributionSkill is supplementary and never becomes a trigger event."""
    without_trigger = parse(
        (user(), assistant("message-1", attribution_skill="review")),
    )
    with_trigger = parse(
        (
            user(),
            assistant(
                "message-1",
                tools=(("tool-skill", "Skill", {"skill": "review"}),),
                attribution_skill="review",
            ),
        ),
    )

    assert without_trigger.attribution_skills == ("review",)
    assert without_trigger.events == ()
    assert len(with_trigger.events) == 1
    assert with_trigger.events[0].kind == "skill"


def test_missing_trigger_timestamp_stays_null() -> None:
    """A missing assistant timestamp is not replaced by a neighbouring record."""
    parsed = parse(
        (
            user(),
            {
                "type": "assistant",
                "sessionId": ROOT_ID,
                "message": {
                    "id": "message-1",
                    "model": "model-main",
                    "stop_reason": "end_turn",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-skill",
                            "name": "Skill",
                            "input": {"skill": "review"},
                        },
                    ],
                },
            },
        ),
    )

    assert parsed.events[0].triggered_at is None
    assert parsed.events[0].object_revision == "unknown"
