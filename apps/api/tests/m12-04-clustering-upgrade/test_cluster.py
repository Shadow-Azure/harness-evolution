"""Deterministic lexical clustering contracts for m12-04."""

from __future__ import annotations

import time
from random import Random
from typing import cast

import pytest

from app.service.evolution.cluster import (
    CLUSTER_ALGORITHM,
    SIMILARITY_THRESHOLD,
    TYPE_IMPACT,
    ClusterDraft,
    ClusterType,
    ProbeForCluster,
    cluster_hash,
    cluster_probes,
    cluster_severity,
)

EMPTY_HASH = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"


def _probe(
    probe_id: str,
    text: str,
    attribute_type: ClusterType = "prompt",
) -> ProbeForCluster:
    """Build one clustering input for the closed attribution categories."""
    return ProbeForCluster(probe_id=probe_id, attribute_type=attribute_type, text=text)


def test_similar_titles_share_a_cluster_and_unrelated_titles_stay_apart() -> None:
    """Lexical neighbors merge while unrelated bad case titles keep their own cluster."""
    clusters = cluster_probes(
        (
            _probe("p-1", "检索索引读取失败"),
            _probe("p-2", "检索索引读取异常"),
            _probe("p-3", "工具调用超时"),
        ),
    )

    assert clusters == (
        ClusterDraft(
            type="prompt",
            description="prompt 类问题 · 检索索引读取失败",
            probes=("p-1", "p-2"),
        ),
        ClusterDraft(
            type="prompt",
            description="prompt 类问题 · 工具调用超时",
            probes=("p-3",),
        ),
    )


def test_short_near_identical_titles_merge_at_the_documented_threshold() -> None:
    """The short-title boundary stays inside the documented threshold instead of halving."""
    assert cluster_probes(
        (
            _probe("p-1", "超时", attribute_type="error"),
            _probe("p-2", "超时错误", attribute_type="error"),
        ),
    ) == (
        ClusterDraft(
            type="error",
            description="error 类问题 · 超时",
            probes=("p-1", "p-2"),
        ),
    )


def test_input_order_does_not_change_clusters_or_hash() -> None:
    """Shuffled probes yield the same ordered clusters and canonical hash."""
    probes = (
        _probe("p-4", "模型输出格式错误", attribute_type="model"),
        _probe("p-2", "检索索引读取失败"),
        _probe("p-1", "检索索引读取异常"),
        _probe("p-3", "工具调用超时"),
        _probe("p-5", "模型输出格式偏离约定", attribute_type="model"),
    )

    forward = cluster_probes(probes)
    backward = cluster_probes(tuple(reversed(probes)))

    assert forward == backward
    assert cluster_hash(forward) == cluster_hash(backward)


def test_types_keep_the_fixed_order_and_members_stay_probe_sorted() -> None:
    """Clusters are grouped by model, prompt, error and members by probe id."""
    clusters = cluster_probes(
        (
            _probe("p-error", "超时", attribute_type="error"),
            _probe("p-prompt-b", "工具调用超时"),
            _probe("p-model", "模型输出格式错误", attribute_type="model"),
            _probe("p-prompt-a", "工具调用超时异常"),
        ),
    )

    assert [cluster.type for cluster in clusters] == ["model", "prompt", "error"]
    assert clusters[1].probes == ("p-prompt-a", "p-prompt-b")


def test_empty_input_yields_no_clusters_and_the_stable_empty_hash() -> None:
    """No attributed probes produces no cluster and a deterministic digest."""
    assert cluster_probes(()) == ()
    assert cluster_hash(()) == EMPTY_HASH


def test_single_probe_yields_one_cluster() -> None:
    """One attributed probe is a complete cluster, never dropped."""
    assert cluster_probes((_probe("p-only", "检索索引读取失败"),)) == (
        ClusterDraft(
            type="prompt",
            description="prompt 类问题 · 检索索引读取失败",
            probes=("p-only",),
        ),
    )


def test_blank_titles_never_merge() -> None:
    """Without tokens there is no similarity evidence, so blank titles stay singletons."""
    clusters = cluster_probes((_probe("p-1", ""), _probe("p-2", "   ")))

    assert len(clusters) == 2
    assert [cluster.probes for cluster in clusters] == [("p-1",), ("p-2",)]
    assert all("1 条归因" in cluster.description for cluster in clusters)


def test_duplicate_probe_identity_is_collapsed() -> None:
    """Repeated input rows for one probe identity cannot duplicate cluster membership."""
    clusters = cluster_probes(
        (_probe("p-1", "检索索引读取失败"), _probe("p-1", "检索索引读取失败"))
    )

    assert clusters == (
        ClusterDraft(
            type="prompt",
            description="prompt 类问题 · 检索索引读取失败",
            probes=("p-1",),
        ),
    )


def test_long_titles_are_bounded_in_the_cluster_description() -> None:
    """A very long title is truncated so the persisted description stays readable."""
    title = "检索索引读取失败" * 30

    description = cluster_probes((_probe("p-1", title),))[0].description

    assert description.startswith("prompt 类问题 · 检索索引读取失败")
    assert description.endswith("…")
    assert len(description) <= len("prompt 类问题 · ") + 120


def test_upgrade_replaces_the_arbitrary_halving_split() -> None:
    """Three unrelated topics become three clusters instead of two mixed halves."""
    probes = (
        _probe("p-1", "检索索引读取失败"),
        _probe("p-2", "工具调用超时"),
        _probe("p-3", "模型输出格式错误", attribute_type="model"),
        _probe("p-4", "检索索引读取超时"),
        _probe("p-5", "工具调用超时未恢复"),
        _probe("p-6", "模型输出格式不符合要求", attribute_type="model"),
    )

    clusters = cluster_probes(probes)

    membership = {cluster.probes for cluster in clusters}
    assert ("p-1", "p-4") in membership
    assert ("p-2", "p-5") in membership
    assert ("p-3", "p-6") in membership
    assert len(clusters) == 3


def test_large_input_clusters_by_topic_and_stays_deterministic() -> None:
    """A thousand probes over twenty topics finish deterministically within a bound."""
    topics = (
        "检索索引读取失败",
        "工具调用超时",
        "模型输出格式错误",
        "权限校验拒绝",
        "文件路径缺失",
        "网络连接中断",
        "配置键名拼写错误",
        "上下文超出限制",
        "并发写入冲突",
        "重试次数耗尽",
        "缓存键不匹配",
        "日志级别配置错误",
        "环境变量未注入",
        "依赖版本冲突",
        "数据库连接池耗尽",
        "编码格式不兼容",
        "响应字段缺失",
        "请求超时",
        "磁盘空间不足",
        "序列化失败",
    )
    probes: list[ProbeForCluster] = []
    for topic_index, topic in enumerate(topics):
        for item_index in range(50):
            probes.append(
                _probe(
                    f"p-{topic_index:02d}-{item_index:03d}",
                    f"{topic}{item_index:04d}",
                ),
            )
    random = Random(20261118)  # noqa: S311 - deterministic fixture order
    shuffled = list(probes)
    random.shuffle(shuffled)

    started = time.perf_counter()
    clusters = cluster_probes(tuple(shuffled))
    elapsed = time.perf_counter() - started

    assert len(clusters) == len(topics)
    assert all(len(cluster.probes) == 50 for cluster in clusters)
    assert cluster_probes(tuple(reversed(probes))) == clusters
    assert elapsed < 15


def test_large_input_with_a_shared_token_does_not_chain() -> None:
    """A token shared by every title is not enough evidence to merge unrelated cases."""
    probes = tuple(
        _probe(f"p-{index:04d}", f"shared error{index:04d} detail{index:04d}")
        for index in range(600)
    )

    clusters = cluster_probes(probes)

    assert len(clusters) == len(probes)
    memberships = zip(clusters, probes, strict=True)
    assert all(cluster.probes == (probe.probe_id,) for cluster, probe in memberships)


def test_cluster_hash_changes_when_cluster_semantics_change() -> None:
    """Descriptions and member order participate in the canonical digest."""
    clusters = cluster_probes(
        (_probe("p-1", "检索索引读取失败"), _probe("p-2", "检索索引读取异常")),
    )
    changed_description = (
        ClusterDraft(
            type=clusters[0].type,
            description="different",
            probes=clusters[0].probes,
        ),
    )
    changed_probe_order = (
        ClusterDraft(
            type=clusters[0].type,
            description=clusters[0].description,
            probes=tuple(reversed(clusters[0].probes)),
        ),
    )

    assert cluster_hash(clusters) != cluster_hash(changed_description)
    assert cluster_hash(clusters) != cluster_hash(changed_probe_order)


def test_algorithm_version_and_threshold_are_explicit_constants() -> None:
    """The run-visible algorithm identity stays a documented, bounded constant."""
    assert CLUSTER_ALGORITHM == "lexical-jaccard-v1"
    assert 0 < SIMILARITY_THRESHOLD < 1


def test_type_impact_mapping_is_the_fixed_policy() -> None:
    """Placeholder impact values are explicit and stable."""
    assert TYPE_IMPACT == {"error": 9, "prompt": 7, "model": 5}
    mutable_view = cast(dict[str, int], TYPE_IMPACT)
    with pytest.raises(TypeError):
        mutable_view["error"] = 10


def test_cluster_severity_uses_report_weight_and_caps_at_ten() -> None:
    """Severity follows the documented confidence x impact x report weight formula."""
    assert cluster_severity("error", 1) == 7.4
    assert cluster_severity("error", 6) == 10.0
    assert cluster_severity("model", 1) == 3.3
    assert cluster_severity("prompt", 1) == 5.2
