"""Deterministic evidence-completeness confidence for rule-v1 attributions.

A case-level confidence is a rule score over three independent signals:
whether the two trigger points are comparable, whether the reported failure
names the attributed object, and whether the reported failure pins the exact
target version or body hash. The same persisted evidence always produces the
same score, and the engine never calls a model to obtain it.
"""

from __future__ import annotations

from dataclasses import dataclass

_THREE_VOTE_SCORE = 0.9
"""All three signals agree; the case is pinned from every available angle."""

_TWO_VOTE_SCORE = 0.8
"""Two signals agree; one evidence angle is absent."""

_ONE_VOTE_SCORE = 0.5
"""Only one signal holds; the attribution rests on one evidence angle."""

_NO_VOTE_SCORE = 0.3
"""No signal holds; the attribution has no direct evidence."""

_CONTRADICTION_SCORE = 0.2
"""The failure pins the target version but names another object."""

_REVISION_PREFIXES = ("tag:", "digest:", "provider:")

LOW_CONFIDENCE_CLUSTER_GATE_ENABLED = False
"""Reserved switch: keep low-confidence attributions out of clusters.

The gate stays disabled here; enabling it is a separate clustering decision
that must also add the query-side filter. This constant documents the switch
without changing today's cluster membership.
"""

LOW_CONFIDENCE_CLUSTER_THRESHOLD = 0.5
"""At or above this completeness score an attribution is not low confidence."""


@dataclass(frozen=True, slots=True)
class EvidenceSignals:
    """The three rule-decidable checks behind one case-level confidence."""

    order_comparable: bool
    failure_signature_match: bool
    version_proof: bool

    @property
    def votes(self) -> int:
        """Return how many independent signals hold."""
        return (
            int(self.order_comparable) + int(self.failure_signature_match) + int(self.version_proof)
        )

    @property
    def contradictory(self) -> bool:
        """Return whether the version proves an object that the failure does not name.

        An exact version hit while the bad case names another object is
        conflicting evidence rather than a simple missing signal: the failure
        was reported against a different object than the version it pins.
        """
        return self.version_proof and not self.failure_signature_match


def failure_signature(
    object_type: str | None,
    object_name: str | None,
) -> tuple[str, str] | None:
    """Return the normalized object identity a failure is reported against.

    Args:
        object_type: Object kind declared by the bad case or the run target.
        object_name: Object name declared by the bad case or the run target.

    Returns:
        A case-folded ``(type, name)`` pair, or ``None`` when either side is
        absent or blank.
    """
    if object_type is None or object_name is None:
        return None
    kind = object_type.strip().casefold()
    name = object_name.strip().casefold()
    if not kind or not name:
        return None
    return kind, name


def _identity_forms(value: str | None) -> set[str]:
    """Return one persisted identity plus its prefix-free form."""
    if value is None:
        return set()
    trimmed = value.strip()
    if not trimmed:
        return set()
    forms = {trimmed}
    for prefix in _REVISION_PREFIXES:
        if trimmed.startswith(prefix):
            bare = trimmed[len(prefix) :]
            if bare:
                forms.add(bare)
    return forms


def version_identity_forms(
    target_version: str | None,
    target_revision: str | None,
) -> frozenset[str]:
    """Return every persisted form that counts as a direct version hit.

    A bad case may record the version a human selected (for example
    ``v2.0.0``) while the run persists the normalized revision identity
    (``tag:v2.0.0`` or ``digest:...``). Both sides keep their prefix-free forms
    so a body hash recorded bare by the trace parser still matches.

    Args:
        target_version: User-selected version stored on the run.
        target_revision: Normalized revision resolved for the run.

    Returns:
        The accepted identity strings; empty when neither side carries one.
    """
    forms: set[str] = set()
    for value in (target_version, target_revision):
        forms.update(_identity_forms(value))
    return frozenset(forms)


def extract_signals(
    *,
    order_state: str,
    case_object_type: str | None,
    case_object_name: str | None,
    case_object_version: str | None,
    probe_type: str,
    probe_object: str,
    target_version: str | None,
    target_revision: str | None,
) -> EvidenceSignals:
    """Evaluate the three evidence signals from persisted attribution inputs.

    Args:
        order_state: Matcher order state; only ``comparable`` counts.
        case_object_type: Object kind the bad case reports.
        case_object_name: Object name the bad case reports.
        case_object_version: Version or revision the bad case reports.
        probe_type: Object kind the attribution is written against.
        probe_object: Object name the attribution is written against.
        target_version: Version selected for the run.
        target_revision: Revision resolved for the run.

    Returns:
        The three booleans consumed by :func:`evidence_score`.
    """
    signature = failure_signature(case_object_type, case_object_name)
    target_signature = failure_signature(probe_type, probe_object)
    case_version = (
        case_object_version.strip()
        if isinstance(case_object_version, str) and case_object_version.strip()
        else None
    )
    return EvidenceSignals(
        order_comparable=order_state == "comparable",
        failure_signature_match=(
            signature is not None and target_signature is not None and signature == target_signature
        ),
        version_proof=(
            case_version is not None
            and case_version in version_identity_forms(target_version, target_revision)
        ),
    )


def evidence_score(signals: EvidenceSignals) -> float:
    """Map the three signals to the documented completeness band.

    Args:
        signals: The evaluated evidence signals.

    Returns:
        A deterministic score: three votes ``>= 0.9``, two votes ``0.7-0.9``,
        one vote around ``0.5``, no votes below ``0.5``, and contradictory
        evidence lower than either a missing or a single signal.
    """
    if signals.contradictory:
        return _CONTRADICTION_SCORE
    if signals.votes == 3:
        return _THREE_VOTE_SCORE
    if signals.votes == 2:
        return _TWO_VOTE_SCORE
    if signals.votes == 1:
        return _ONE_VOTE_SCORE
    return _NO_VOTE_SCORE


def attribution_confidence(conclusion: str, signals: EvidenceSignals) -> float:
    """Return confidence in the conclusion, not confidence in an attribution.

    An attributed conclusion carries the evidence-completeness score. A
    non-target conclusion is supported by the absence of those signals, so its
    confidence is the complement. Both stay a 0-1 float for the existing API
    field.

    Args:
        conclusion: Closed attribution conclusion (``attributed`` or ``non_target``).
        signals: The evaluated evidence signals.

    Returns:
        A deterministic confidence in the stated conclusion.
    """
    score = evidence_score(signals)
    return score if conclusion == "attributed" else 1.0 - score
