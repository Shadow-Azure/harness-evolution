"""Deterministic evidence-completeness confidence for rule-v1 attributions.

A case-level confidence is a rule score over three independent signals:
whether the two trigger points are comparable, whether the reported failure
names the attributed object, and whether the reported failure pins the exact
resolved revision or body hash. The same persisted evidence always produces the
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
"""The failure pins the target revision but names another object."""

_REVISION_PREFIXES = ("tag:", "digest:", "provider:")

LOW_CONFIDENCE_CLUSTER_GATE_ENABLED = False
"""Reserved switch: keep low-confidence attributions out of clusters.

The gate stays disabled here; enabling it is a separate clustering decision
that must also add the query-side filter. This constant documents the switch
without changing today's cluster membership.
"""

LOW_CONFIDENCE_CLUSTER_THRESHOLD = 0.6
"""Below this completeness score an attribution is low confidence.

The threshold sits above the one-vote band (0.5) so enabling the gate later
filters attributions that rest on a single evidence angle as well as the
no-evidence and contradictory bands, while two-vote and three-vote cases pass.
"""


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


def failure_signature(object_name: str | None) -> str | None:
    """Return the normalized object name a failure is reported against.

    The potential matcher's same-object rule is name-based, and catalog sync
    defaults a missing upstream object type to ``skill``; including the type
    here would turn a legitimate self report into a contradiction. The name is
    therefore the whole failure signature.

    Args:
        object_name: Object name declared by the bad case or the run target.

    Returns:
        A case-folded name, or ``None`` when the value is absent or blank.
    """
    if object_name is None:
        return None
    name = object_name.strip().casefold()
    return name or None


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


def version_identity_forms(revision: str | None) -> frozenset[str]:
    """Return every persisted form that counts as a direct revision hit.

    The resolved revision keeps its ``tag:`` / ``digest:`` / ``provider:``
    prefix and its prefix-free form, so a body hash recorded bare by the trace
    parser still matches while the selected human version never has to join the
    cache-key identity.

    Args:
        revision: Normalized revision resolved for the run.

    Returns:
        The accepted identity strings; empty when the run has no revision.
    """
    return frozenset(_identity_forms(revision))


def _version_proof(case_version: str | None, revision: str | None) -> bool:
    """Return whether the case version and the resolved revision overlap."""
    if case_version is None:
        return False
    return bool(_identity_forms(case_version) & _identity_forms(revision))


def extract_signals(
    *,
    order_state: str,
    case_object_name: str | None,
    case_object_version: str | None,
    probe_object: str,
    target_revision: str | None,
) -> EvidenceSignals:
    """Evaluate the three evidence signals from persisted attribution inputs.

    Args:
        order_state: Matcher order state; only ``comparable`` counts.
        case_object_name: Object name the bad case reports.
        case_object_version: Version or revision the bad case reports.
        probe_object: Object name the attribution is written against.
        target_revision: Normalized revision resolved for the run.

    Returns:
        The three booleans consumed by :func:`evidence_score`.
    """
    signature = failure_signature(case_object_name)
    target_signature = failure_signature(probe_object)
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
        version_proof=_version_proof(case_version, target_revision),
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
