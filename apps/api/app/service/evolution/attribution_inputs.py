"""Immutable, workspace-local evidence and inputs for individual attribution executions."""

from __future__ import annotations

import errno
import hashlib
import json
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.service.evolution.attribution_contracts import canonical_json_hash

if TYPE_CHECKING:
    from app.service.evolution.attribution import AttributionInput

SESSION_FILES = ("session_tree.json", "traces.json", "trace_coverage.json")


def file_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def disk_id(value: str) -> str:
    """Preserve ordinary external IDs and encode anything unsafe as one path segment."""
    return (
        value
        if re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}", value)
        else "~" + file_digest(value)
    )


def publish_directory(directory: Path, files: Mapping[str, str]) -> None:
    """Expose complete directories atomically. A concurrent publisher may win."""
    if directory.is_dir():
        return
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as staging:
        ready = Path(staging) / "ready"
        ready.mkdir()
        for filename, content in files.items():
            (ready / filename).write_bytes(content.encode("utf-8"))
        try:
            ready.rename(directory)
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY) or not directory.is_dir():
                raise


def _hash_segment(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch("[a-f0-9]{64}", value):
        raise ValueError("invalid digest in attribution input manifest")
    return value


class CaseInputArchive:
    def __init__(self, root: Path, item: AttributionInput):
        self.item = item
        self.case_path = (
            root / "attribute_input/batches" / disk_id(item.run_id) / disk_id(item.bad_case_id)
        )
        self.sessions = root / "attribute_input/sessions" / disk_id(item.session_id)
        self.sources = root / "attribute_source/snapshots"

    def _identity(self) -> dict[str, Any]:
        item = self.item
        identity: dict[str, Any] = {
            "schemaVersion": 1,
            "workspaceId": item.workspace_id,
            "batchId": item.run_id,
            "trigger": item.batch_trigger,
            "badcaseId": item.bad_case_id,
            "sessionId": item.session_id,
            "target": {
                "type": item.probe_type,
                "name": item.probe_object,
                "version": item.selected_version,
                "revision": item.object_version,
            },
            "skill": {
                "name": item.attribution_skill_key,
                "revision": item.attribution_skill_revision,
                "snapshotHash": item.attribution_skill_content_hash,
            },
        }

        if item.definition:
            identity["definitionKey"] = item.definition.key
            identity["gitSource"] = {
                "repoUrl": item.repo_url,
                "commit": item.definition.commit,
                "path": item.definition.path,
            }
        else:
            identity["definitionKey"] = canonical_json_hash(
                [item.probe_type, item.probe_object, item.object_version]
            )
        return identity

    def load(self) -> dict[str, str] | None:
        if not self.case_path.exists():
            return None
        manifest = json.loads((self.case_path / "manifest.json").read_bytes())
        if any(manifest[k] != v for k, v in self._identity().items()):
            raise ValueError("attribution batch input identity mismatch")
        evidence_hash = _hash_segment(manifest["evidenceHash"])
        source_hash = _hash_segment(manifest["sourceHash"])
        data = {
            name: (self.sessions / evidence_hash / name).read_bytes().decode()
            for name in SESSION_FILES
        }
        if canonical_json_hash({k: file_digest(v) for k, v in data.items()}) != evidence_hash:
            raise ValueError("attribution evidence checksum mismatch")
        data["input_badcase.json"] = (self.case_path / "input_badcase.json").read_bytes().decode()
        prompt = (self.sources / source_hash / "attribute_source.md").read_bytes().decode()
        data["attribute_source.md"] = prompt
        if file_digest(prompt) != source_hash or canonical_json_hash(data) != manifest["inputHash"]:
            raise ValueError("attribution batch input checksum mismatch")
        return data

    def publish(self, data: Mapping[str, str]) -> dict[str, str]:
        evidence = {name: data[name] for name in SESSION_FILES}
        evidence_hash = canonical_json_hash({k: file_digest(v) for k, v in evidence.items()})
        source_hash = file_digest(data["attribute_source.md"])
        publish_directory(self.sessions / evidence_hash, evidence)
        publish_directory(
            self.sources / source_hash, {"attribute_source.md": data["attribute_source.md"]}
        )
        manifest = {
            **self._identity(),
            "evidenceHash": evidence_hash,
            "sourceHash": source_hash,
            "inputHash": canonical_json_hash(data),
        }
        publish_directory(
            self.case_path,
            {
                "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
                "input_badcase.json": data["input_badcase.json"],
            },
        )
        frozen = self.load()
        if frozen is None or frozen != data:
            # The runner must compute the report manifest against the winner's inputs.
            # A retry loads them before computing its execution manifest.
            raise ValueError("different attribution inputs already frozen for this batch and case")
        return frozen
