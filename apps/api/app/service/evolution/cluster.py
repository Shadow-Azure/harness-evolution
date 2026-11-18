"""Deterministic lexical clustering over attributed bad cases."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

ClusterType = Literal["model", "prompt", "error"]

CLUSTER_ALGORITHM = "lexical-jaccard-v1"
"""Stable algorithm identity recorded with each cluster run."""

SIMILARITY_THRESHOLD = 0.3
"""Jaccard similarity at or above which two probes join the same cluster."""

TYPE_ORDER: tuple[ClusterType, ...] = ("model", "prompt", "error")

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]+")


@dataclass(frozen=True, slots=True)
class ProbeForCluster:
    """Minimal attributed-probe evidence consumed by the lexical clusterer."""

    probe_id: str
    attribute_type: ClusterType
    text: str = ""


@dataclass(frozen=True, slots=True)
class ClusterDraft:
    """One deterministic cluster before it receives a persisted identity."""

    type: ClusterType
    description: str
    probes: tuple[str, ...]


TYPE_IMPACT: Mapping[str, int] = MappingProxyType(
    {"error": 9, "prompt": 7, "model": 5},
)
TYPE_CONFIDENCE: Mapping[str, float] = MappingProxyType(
    {"error": 0.82, "prompt": 0.74, "model": 0.66},
)
"""Cluster-level placeholder confidence by category."""


def cluster_severity(
    cluster_type: ClusterType,
    report_count: int,
) -> float:
    """Return the documented bounded severity for one cluster.

    Args:
        cluster_type: Closed attribution category of the cluster.
        report_count: Distinct source bad cases behind the cluster.

    Returns:
        ``round(min(10, confidence x impact x reportWeight), 1)`` where
        ``reportWeight = 1 + 0.1 x min(reportCount - 1, 5)``.
    """
    weight = 1 + 0.1 * min(max(report_count, 1) - 1, 5)
    return round(
        min(10.0, TYPE_CONFIDENCE[cluster_type] * TYPE_IMPACT[cluster_type] * weight),
        1,
    )


def cluster_probes(probes: Sequence[ProbeForCluster]) -> tuple[ClusterDraft, ...]:
    """Group probes of one category whose text tokens are lexically similar.

    Each category is clustered independently. Probes with no comparable text
    tokens stay in their own singleton cluster, so missing evidence can never
    produce a false semantic merge. Clusters and members are ordered by probe
    identity, which makes the result independent of database row order.

    Args:
        probes: Attributed probe identities with their bad case summary text.

    Returns:
        Clusters in model, prompt, error order with members sorted by probe id.
    """
    unique: dict[str, ProbeForCluster] = {}
    for probe in probes:
        current = unique.get(probe.probe_id)
        if current is None or (probe.attribute_type, probe.text) < (
            current.attribute_type,
            current.text,
        ):
            unique[probe.probe_id] = probe

    clusters: list[ClusterDraft] = []
    for attribute_type in TYPE_ORDER:
        group = sorted(
            (probe for probe in unique.values() if probe.attribute_type == attribute_type),
            key=lambda probe: probe.probe_id,
        )
        if not group:
            continue
        token_sets = [_tokens(probe.text) for probe in group]
        for members in _connected_components(token_sets):
            member_probes = tuple(group[index].probe_id for index in members)
            representative = group[members[0]].text
            clusters.append(
                ClusterDraft(
                    type=attribute_type,
                    description=_description(
                        attribute_type,
                        representative,
                        len(members),
                    ),
                    probes=member_probes,
                ),
            )
    return tuple(clusters)


def _connected_components(token_sets: Sequence[frozenset[str]]) -> tuple[tuple[int, ...], ...]:
    """Return deterministic single-link components for one category.

    Args:
        token_sets: Token set of each probe in the category, in probe order.

    Returns:
        Member indexes per component, ordered by their smallest member index.
    """
    parent = list(range(len(token_sets)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    postings: dict[str, list[int]] = {}
    for index, token_set in enumerate(token_sets):
        for token in token_set:
            postings.setdefault(token, []).append(index)

    for members in postings.values():
        if len(members) < 2:
            continue
        for position, left in enumerate(members):
            for right in members[position + 1 :]:
                if _jaccard(token_sets[left], token_sets[right]) >= SIMILARITY_THRESHOLD:
                    union(left, right)

    components: dict[int, list[int]] = {}
    for index in range(len(token_sets)):
        components.setdefault(find(index), []).append(index)
    return tuple(
        tuple(sorted(members)) for members in sorted(components.values(), key=lambda item: item[0])
    )


def _tokens(text: str) -> frozenset[str]:
    """Return comparable ASCII tokens and CJK character bigrams for one text.

    Args:
        text: Representative bad case summary.

    Returns:
        Lower-case tokens; CJK runs longer than one character become bigrams.
    """
    tokens: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(text.lower()):
        value = match.group(0)
        if value.isascii() or len(value) == 1:
            tokens.add(value)
        else:
            tokens.update(value[index : index + 2] for index in range(len(value) - 1))
    return frozenset(tokens)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Return the Jaccard similarity of two token sets.

    Args:
        left: First token set.
        right: Second token set.

    Returns:
        Intersection over union in ``[0, 1]``; empty sets score zero.
    """
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if not intersection:
        return 0.0
    return intersection / len(left | right)


def _description(
    attribute_type: ClusterType,
    representative: str,
    member_count: int,
) -> str:
    """Return one readable cluster description bounded for the database/UI.

    Args:
        attribute_type: Closed attribution category of the cluster.
        representative: Title text of the first probe in the cluster.
        member_count: Number of probes in the cluster.

    Returns:
        Category prefix plus the representative title, or a count fallback.
    """
    headline = _headline(representative)
    if headline:
        return f"{attribute_type} 类问题 · {headline}"
    return f"{attribute_type} 类问题 · {member_count} 条归因"


def _headline(text: str, limit: int = 120) -> str:
    """Normalize one summary into whitespace-free, bounded display text.

    Args:
        text: Raw representative text.
        limit: Maximum rendered character count, including the ellipsis.

    Returns:
        Collapsed single-line text, truncated with an ellipsis when needed.
    """
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def cluster_hash(clusters: Sequence[ClusterDraft]) -> str:
    """Return a canonical SHA-256 digest for one ordered cluster result.

    Args:
        clusters: Ordered cluster drafts.

    Returns:
        Lower-case SHA-256 hex digest.
    """
    payload = [
        {
            "type": cluster.type,
            "description": cluster.description,
            "probes": list(cluster.probes),
        }
        for cluster in clusters
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
