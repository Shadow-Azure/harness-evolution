#!/usr/bin/env python3
"""Generate one `probe_report.json` with a fixed, machine-valid structure.

The selected_target comes from input_badcase.json. The caller supplies a verdict
about that target, a root cause or evidence gap, an analysis with evidence
references, and optionally the identity of a known causal object and a proposal.
The original reporting object is preserved in from_bad_cases.

Returns 0 and prints the written JSON path on success; prints the error and
returns non-zero on validation failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CONCLUSIONS = ("attributed", "non_target", "inconclusive")

ATTRIBUTE_TYPES: tuple[str, ...] = ("prompt", "model", "error", "flow", "context", "unknown")

DEFAULT_BAD_CASE_TYPE = "skill"
PROBE_FILENAME = "probe_report.json"

class ValidationError(Exception):
    """Raised when the caller-supplied input cannot yield a valid report."""

def _load_json(path: Path) -> dict[str, Any]:
    """Read and parse a UTF-8 JSON file, raising a helpful error on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot read input file {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path} does not contain a JSON object")
    return data

def _find_bad_case(session_data: dict[str, Any], bad_case_id: str) -> dict[str, Any]:
    """Locate one bad-case row by id inside an `input_badcase.json` body."""
    bad_cases = session_data.get("bad_cases")
    if not isinstance(bad_cases, list):
        raise ValidationError("'bad_cases' is missing or not a list")
    for row in bad_cases:
        if isinstance(row, dict) and row.get("bad_case_id") == bad_case_id:
            return row
    raise ValidationError(f"bad_case_id {bad_case_id!r} not found in input_badcase.json")

def _text(value: Any) -> str:
    """Return a plain string or '' (never None / non-str)."""
    return value if isinstance(value, str) else ""

def _resolve_object_version(
    *,
    probe_object: str,
    reported_object: str,
    reported_version: str,
    requested_version: str,
) -> str:
    """Return the version of the actual attribution target.

    The reported `object_version` belongs to the **reported** object. When the
    model attributes a discovery to a different upstream skill/agent, inheriting
    that version would file the report under a version its target never had and
    the launch-wizard hit query (`probe_object + object_version + probe_type`)
    would never match it. An explicit version is therefore mandatory whenever
    the two objects differ; same-object reports keep the reported version.
    """
    if requested_version:
        return requested_version
    if reported_object and probe_object != reported_object:
        raise ValidationError(
            f"--object-version is required when --probe_object ({probe_object!r}) "
            f"differs from the reported object ({reported_object!r}): the reported "
            "version belongs to the reporting object",
        )
    return reported_version

def build_report(
    *,
    session_id: str,
    bad_case: dict[str, Any],
    selected_target: dict[str, Any],
    conclusion: str,
    root_cause: str,
    evidence_references: list[str],
    probe_object: str | None,
    object_version: str | None,
    attribute_type: str,
    probe_description: str,
    probe_analysis: str,
    probe_type: str | None,
    detail_description: str | None,
    proposal: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble a probe_report with structure owned by the program.

    `probe_object` is model-provided — the actual attribution target, which
    may differ from the input `object` when the bad case is a discovery and
    the real defect owner is upstream. The reported `object` and its version
    are preserved verbatim inside `from_bad_cases`.
    """
    if not isinstance(selected_target, dict) or not _text(selected_target.get("name")).strip():
        raise ValidationError("input_badcase.json has no selected_target name")
    if conclusion not in CONCLUSIONS:
        raise ValidationError("invalid --conclusion")
    if conclusion == "attributed" and attribute_type == "unknown":
        raise ValidationError("attributed requires a known --attribute-type")
    if not root_cause.strip():
        raise ValidationError("--root-cause requires a cause or an evidence gap")
    if any(not ref.strip() or len(ref) > 512 for ref in evidence_references):
        raise ValidationError("each --evidence-ref must be 1 to 512 characters")
    if probe_type == "agents":
        probe_type = "agent"
    if probe_type and probe_type not in ("skill", "agent", "knowledge"):
        raise ValidationError(f"invalid --probe_type: {probe_type}")
    if not probe_object and (object_version or probe_type):
        raise ValidationError("--probe_object is required with a causal object type or version")
    bad_case_id = _text(bad_case.get("bad_case_id"))
    if not bad_case_id:
        raise ValidationError("bad-case row has no 'bad_case_id'")

    from_bad_case: dict[str, Any] = {
        "bad_case_id": bad_case_id,
        "type": _text(bad_case.get("type")),
        "object": _text(bad_case.get("object")),
        "object_version": _text(bad_case.get("object_version")),
        "bad_case_type": _text(bad_case.get("bad_case_type")),
        "bad_case_session_id": _text(bad_case.get("bad_case_session_id")) or session_id,
        "title": _text(bad_case.get("title")),
        "reason": _text(bad_case.get("reason")),
        "source": _text(bad_case.get("source")),
    }
    if detail_description is not None and detail_description:
        from_bad_case["detail_description"] = detail_description

    identity = json.dumps(
        [
            session_id,
            selected_target.get("type"),
            selected_target["name"],
            selected_target.get("version"),
            selected_target.get("revision"),
            bad_case_id,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    report: dict[str, Any] = {
        "probe_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "selected_target": selected_target,
        "conclusion": conclusion,
        "root_cause": root_cause,
        "evidence_references": evidence_references,
        "attribute_type": attribute_type,
        "probe_description": probe_description,
        "probe_analysis": probe_analysis,
        "from_bad_cases": [from_bad_case],
    }
    if probe_object:
        report["probe_object"] = probe_object
        report["probe_type"] = probe_type or DEFAULT_BAD_CASE_TYPE
        report["object_version"] = _resolve_object_version(
            probe_object=probe_object,
            reported_object=_text(bad_case.get("object")),
            reported_version=_text(bad_case.get("object_version")),
            requested_version=(object_version or "").strip(),
        )
    if proposal:
        report["proposal"] = proposal
    return report

def _default_output(session_dir: Path, bad_case_id: str) -> Path:
    """Derive the conventional output path under the session work directory."""
    return session_dir / "badcases" / bad_case_id / PROBE_FILENAME

def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments with required-field enforcement."""
    parser = argparse.ArgumentParser(
        description="Emit one machine-valid probe_report.json; structure is script-owned.",
    )
    parser.add_argument("--input-badcase", required=True, type=Path,
                        help="Path to the session's input_badcase.json")
    parser.add_argument("--bad-case-id", required=True,
                        help="The bad_case_id this probe report is for")
    parser.add_argument("--conclusion", required=True, choices=CONCLUSIONS,
                        help="Whether the selected target caused this particular bad case")
    parser.add_argument("--root-cause", required=True,
                        help="Cause supported by evidence, or the gap preventing a determination")
    parser.add_argument("--evidence-ref", action="append", default=[],
                        help="Trace coordinate supporting the verdict; repeat for multiple references")
    parser.add_argument("--probe_object",
                        help="The actual attribution target (may differ from input 'object' for discoveries)")
    parser.add_argument("--object-version", dest="object_version", default=None,
                        help="The actual attribution target's version; required when "
                            "--probe_object differs from the reported object")
    parser.add_argument("--probe_type",
                        help="Probe kind: 'skill', 'agent' or 'knowledge' (default 'skill')")
    parser.add_argument("--attribute-type", required=True, choices=ATTRIBUTE_TYPES,
                        help="Closed attribution category (prompt/model/error/flow/context/unknown)")
    parser.add_argument("--probe-description", required=True,
                        help="What the problem is and how to fix it (model-provided)")
    parser.add_argument("--probe-analysis", required=True,
                        help="The reasoning/analysis, sanitized (model-provided)")
    parser.add_argument("--detail-description",
                        help="Optional detailed description for from_bad_cases")
    parser.add_argument("--proposal-target-skill")
    parser.add_argument("--proposal-target-location")
    parser.add_argument("--proposal-change")
    parser.add_argument("--proposal-expected-behavior")
    parser.add_argument("--proposal-evaluation-plan")
    parser.add_argument("--output", type=Path,
                        help="Output path; defaults to <input-dir>/badcases/<id>/probe_report.json")
    return parser.parse_args(argv)

def _build_proposal(args: argparse.Namespace) -> dict[str, Any] | None:
    """Collect the optional proposal object from its flat CLI fields."""
    fields = {
        "target_skill": getattr(args, "proposal_target_skill", None),
        "target_location": getattr(args, "proposal_target_location", None),
        "change": getattr(args, "proposal_change", None),
        "expected_behavior": getattr(args, "proposal_expected_behavior", None),
        "evaluation_plan": getattr(args, "proposal_evaluation_plan", None),
    }
    present = {k: v for k, v in fields.items() if v}
    return present or None

def main(argv: list[str] | None = None) -> int:
    """Entry point; returns process exit code."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    input_path: Path = args.input_badcase
    if not input_path.is_file():
        print(f"error: input_badcase not found: {input_path}", file=sys.stderr)
        return 2

    try:
        session_data = _load_json(input_path)
        session_id = _text(session_data.get("session_id"))
        if not session_id:
            raise ValidationError("input_badcase.json has no 'session_id'")
        bad_case = _find_bad_case(session_data, args.bad_case_id)

        proposal = _build_proposal(args)
        report = build_report(
            session_id=session_id,
            bad_case=bad_case,
            selected_target=session_data.get("selected_target"),
            conclusion=args.conclusion,
            root_cause=args.root_cause,
            evidence_references=args.evidence_ref,
            probe_object=args.probe_object,
            object_version=args.object_version,
            attribute_type=args.attribute_type,
            probe_description=args.probe_description,
            probe_analysis=args.probe_analysis,
            probe_type=args.probe_type,
            detail_description=args.detail_description,
            proposal=proposal,
        )
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output is not None:
        out_path = args.output
    else:
        out_path = _default_output(input_path.parent, args.bad_case_id)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"error: cannot write {out_path}: {exc}", file=sys.stderr)
        return 2

    print(out_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())