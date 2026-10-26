"""Deterministic V1 placeholder clustering."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

ClusterType = Literal["model", "prompt", "error"]


@dataclass(frozen=True, slots=True)
class ProbeForCluster:
    """Minimal probe identity required by the placeholder clusterer."""

    probe_id: str
    attribute_type: ClusterType


@dataclass(frozen=True, slots=True)
class ClusterDraft:
    """One deterministic cluster before it receives a persisted identity."""

    type: ClusterType
    description: str
    probes: tuple[str, ...]


TYPE_IMPACT: Mapping[str, int] = MappingProxyType(
    {"error": 9, "prompt": 7, "model": 5},
)


def simple_cluster(probes: Sequence[ProbeForCluster]) -> tuple[ClusterDraft, ...]:
    """Group probes by attribute type and split each group in half deterministically.

    Args:
        probes: Probe identities in any input order.

    Returns:
        Clusters in model, prompt, error order with probes sorted by identity.
    """
    clusters: list[ClusterDraft] = []
    for attribute_type in ("model", "prompt", "error"):
        group = sorted(
            (probe for probe in probes if probe.attribute_type == attribute_type),
            key=lambda probe: probe.probe_id,
        )
        if not group:
            continue
        if len(group) == 1:
            groups = [group]
        else:
            midpoint = (len(group) + 1) // 2
            groups = [group[:midpoint], group[midpoint:]]
        for index, half in enumerate(groups, start=1):
            clusters.append(
                ClusterDraft(
                    type=attribute_type,
                    description=f"{attribute_type} 类问题 · 第 {index} 组（占位聚类）",  # noqa: RUF001
                    probes=tuple(probe.probe_id for probe in half),
                ),
            )
    return tuple(clusters)


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
