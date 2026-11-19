"""Golden hashes for the public systematic-debugging SKILL.md body extraction."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from app.service.acquisition.normalize import normalize_transcript
from app.service.acquisition.parsers.claude_code import _definition_body
from app.service.evolution.target_content import TargetContentResolver
from app.third_party_api.git.content import SubprocessGitContent
from app.utils.definition import (
    definition_file_hash,
    definition_hash,
    strip_definition_frontmatter,
)

FIXTURE = Path(__file__).parent / "fixtures" / "systematic-debugging-SKILL.md"
ROOT_ID = "m13-golden-root"
SKILL_PATH = "/plugins/superpowers/skills/systematic-debugging"
TRACE_BODY_HASH = "8e54e1438967ef93b31b8d4dfc22f67b9315a567c30f63dc177bf715db2683d8"
WHOLE_FILE_HASH = "a9a79740379b1d42c8734eca861d226abe66cadebf06ea2b9091883ca868ba4e"


def _git(repo: Path, *args: str) -> None:
    """Run one deterministic local git command."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 - fixed local test binary and argv
        (git, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _jsonl(*records: object) -> str:
    """Encode deterministic JSONL parser input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def _parser_records(body: str) -> tuple[dict[str, object], ...]:
    """Build the minimal Skill call and injection records for the parser."""
    user: dict[str, object] = {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-19T01:00:00Z",
        "message": {"content": "debug this failure"},
    }
    assistant: dict[str, object] = {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-19T01:01:00Z",
        "message": {
            "id": "message-golden",
            "model": "synthetic-model",
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-golden",
                    "name": "Skill",
                    "input": {"skill": "systematic-debugging"},
                },
            ],
            "usage": {"input_tokens": 3, "output_tokens": 1},
        },
    }
    injection: dict[str, object] = {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-19T01:02:00Z",
        "isMeta": True,
        "sourceToolUseID": "tool-golden",
        "message": {
            "content": f"Base directory for this skill: {SKILL_PATH}\n\n{body}",
        },
    }
    return user, assistant, injection


def test_public_skill_body_matches_the_trace_definition_hash() -> None:
    """Frontmatter is the only difference between the whole file and the trace body."""
    content = FIXTURE.read_text(encoding="utf-8")
    body = strip_definition_frontmatter(content)

    assert definition_hash(content) == WHOLE_FILE_HASH
    assert definition_hash(body) == TRACE_BODY_HASH
    assert definition_hash(content) != definition_hash(body)
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() != WHOLE_FILE_HASH


async def test_target_resolver_strips_skill_and_agent_frontmatter(tmp_path: Path) -> None:
    """Skill and Agent file reads hash only the body the parser sees."""
    content = FIXTURE.read_text(encoding="utf-8")
    agent = "---\nname: reviewer\n---\n\n# Reviewer\n\nCheck evidence.\n"
    repo = tmp_path / "repo"
    (repo / "skills" / "systematic-debugging").mkdir(parents=True)
    (repo / "agents" / "reviewer").mkdir(parents=True)
    (repo / "skills" / "systematic-debugging" / "SKILL.md").write_text(content)
    (repo / "agents" / "reviewer" / "AGENT.md").write_text(agent)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "public fixture")
    _git(repo, "tag", "main")

    resolver = TargetContentResolver(
        SubprocessGitContent(cache_root=tmp_path / "cache"),
    )
    skill = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="skills/systematic-debugging",
        version="main",
    )
    reviewer = await resolver.resolve(
        object_type="agent",
        repo_url=str(repo),
        sub_dir="agents/reviewer",
        version="main",
    )

    assert skill.target_revision == f"digest:{TRACE_BODY_HASH}"
    assert reviewer.target_revision == f"digest:{definition_file_hash(agent)}"
    assert definition_file_hash(agent) != definition_hash(agent)


async def test_target_resolver_accepts_lowercase_agent_file(tmp_path: Path) -> None:
    """agent.md is accepted when the repository uses lowercase definition files."""
    agent = "---\nname: reviewer\n---\n\n# Reviewer\n\nCheck evidence.\n"
    repo = tmp_path / "repo-lower"
    (repo / "agents" / "reviewer").mkdir(parents=True)
    (repo / "agents" / "reviewer" / "agent.md").write_text(agent)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "lowercase agent")
    _git(repo, "tag", "main")
    resolver = TargetContentResolver(
        SubprocessGitContent(cache_root=tmp_path / "cache-lower"),
    )
    resolved = await resolver.resolve(
        object_type="agent",
        repo_url=str(repo),
        sub_dir="agents/reviewer",
        version="main",
    )
    assert resolved.target_revision == f"digest:{definition_file_hash(agent)}"


def test_parser_skill_injection_reaches_the_same_golden_body_hash() -> None:
    """The parser's injected body (without frontmatter) resolves the trace hash."""
    content = FIXTURE.read_text(encoding="utf-8")
    body = strip_definition_frontmatter(content)
    parsed = normalize_transcript(
        _jsonl(*_parser_records(body)),
        root_session_id=ROOT_ID,
        agent_id=ROOT_ID,
        agent_kind="main",
        agent_meta=None,
    )

    assert parsed.events[0].definition_hash == TRACE_BODY_HASH
    assert parsed.events[0].object_revision == f"digest:{TRACE_BODY_HASH}"


def test_parser_agent_body_matches_frontmatter_stripped_agent_file() -> None:
    """The parser's agent prompt body and a frontmatter agent file share one hash."""
    agent = "---\nname: reviewer\n---\n\n# Reviewer\n\nCheck evidence.\n"
    body = strip_definition_frontmatter(agent)
    parsed = _definition_body({"systemPrompt": body}, "prompt_snapshot")
    assert parsed is not None
    assert definition_hash(parsed) == definition_file_hash(agent)


class _KnowledgeSource:
    """Serve the public file as a knowledge document body."""

    def __init__(self, body: str) -> None:
        """Bind the document content."""
        self._body = body

    async def read_document(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        revision: str,
    ) -> str:
        """Return the full document, including any frontmatter."""
        del repo_url, sub_dir, revision
        return self._body


async def test_knowledge_reads_keep_the_full_normalized_content_hash(tmp_path: Path) -> None:
    """Knowledge documents are not definition files and keep their whole body."""
    content = FIXTURE.read_text(encoding="utf-8")
    resolver = TargetContentResolver(
        SubprocessGitContent(cache_root=tmp_path / "cache"),
        knowledge=_KnowledgeSource(content),
    )

    resolved = await resolver.resolve(
        object_type="knowledge",
        repo_url="knowledge://provider",
        sub_dir="docs",
        version="main",
    )

    assert resolved.target_revision == f"digest:{definition_hash(content)}"
    assert resolved.target_revision != f"digest:{definition_file_hash(content)}"
