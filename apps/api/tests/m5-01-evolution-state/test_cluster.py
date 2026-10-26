"""Deterministic placeholder clustering contracts."""

from app.service.evolution.cluster import (
    TYPE_IMPACT,
    ClusterDraft,
    ProbeForCluster,
    cluster_hash,
    simple_cluster,
)

PROBES = (
    ProbeForCluster("p-error-2", "error"),
    ProbeForCluster("p-model-3", "model"),
    ProbeForCluster("p-prompt-1", "prompt"),
    ProbeForCluster("p-model-1", "model"),
    ProbeForCluster("p-error-1", "error"),
    ProbeForCluster("p-model-2", "model"),
)


def test_simple_cluster_uses_fixed_type_order_and_split_rule() -> None:
    """Each non-empty type is sorted, split deterministically, and kept in type order."""
    assert simple_cluster(PROBES) == (
        ClusterDraft(
            type="model",
            description="model 类问题 · 第 1 组（占位聚类）",  # noqa: RUF001
            probes=("p-model-1", "p-model-2"),
        ),
        ClusterDraft(
            type="model",
            description="model 类问题 · 第 2 组（占位聚类）",  # noqa: RUF001
            probes=("p-model-3",),
        ),
        ClusterDraft(
            type="prompt",
            description="prompt 类问题 · 第 1 组（占位聚类）",  # noqa: RUF001
            probes=("p-prompt-1",),
        ),
        ClusterDraft(
            type="error",
            description="error 类问题 · 第 1 组（占位聚类）",  # noqa: RUF001
            probes=("p-error-1",),
        ),
        ClusterDraft(
            type="error",
            description="error 类问题 · 第 2 组（占位聚类）",  # noqa: RUF001
            probes=("p-error-2",),
        ),
    )


def test_cluster_hash_is_stable_for_equivalent_inputs() -> None:
    """Shuffled probes produce the same canonical hash after clustering."""
    reversed_probes = tuple(reversed(PROBES))

    clusters = simple_cluster(PROBES)
    reversed_clusters = simple_cluster(reversed_probes)

    assert clusters == reversed_clusters
    assert cluster_hash(clusters) == cluster_hash(reversed_clusters)


def test_cluster_hash_changes_when_cluster_semantics_change() -> None:
    """Descriptions and probe order participate in the canonical hash."""
    clusters = simple_cluster(PROBES)
    changed_description = (
        ClusterDraft(
            type=clusters[0].type,
            description="different",
            probes=clusters[0].probes,
        ),
        *clusters[1:],
    )
    changed_probe_order = (
        ClusterDraft(
            type=clusters[0].type,
            description=clusters[0].description,
            probes=tuple(reversed(clusters[0].probes)),
        ),
        *clusters[1:],
    )

    assert cluster_hash(clusters) != cluster_hash(changed_description)
    assert cluster_hash(clusters) != cluster_hash(changed_probe_order)


def test_empty_input_has_stable_empty_hash() -> None:
    """No probes yields no clusters and a deterministic value."""
    assert simple_cluster(()) == ()
    assert cluster_hash(()) == cluster_hash(())


def test_type_impact_mapping_is_the_fixed_v1_policy() -> None:
    """Placeholder impact values are explicit and stable."""
    assert TYPE_IMPACT == {"error": 9, "prompt": 7, "model": 5}
