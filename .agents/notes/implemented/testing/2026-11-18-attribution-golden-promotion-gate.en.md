# Agent Note: Attribution Golden shadow evaluation and promotion gate

Status: implemented

English | [中文](2026-11-18-attribution-golden-promotion-gate.md)

## Problem

Attribution output feeds clustering, proposals, and patches, so valid Probe Report JSON alone cannot reveal a wrong object conclusion, invented evidence, prompt injection, or degraded context. Allowing a new engine or Skill revision to become the workspace default without comparison would spread unreviewed behavior into the production chain and leave no durable basis for the human decision.

## Decision

The repository maintains a sanitized, versioned Golden Set. Shadow evaluation reuses production executor input, output, and Probe Report V2 projection but never calls the Runner or writes runs, Probe Reports, candidates, clusters, or cache entries. Reports measure conclusion and category accuracy, evidence validity, introduction/detection-point hits, schema compliance, safety, failures, latency, and tokens; the deterministic evaluation hash excludes observed latency. Every evaluation, acceptance, rejection, and rollback is an isolated append-only event, while each revision stores its current `candidate/eligible/rejected` state. Only an `eligible` revision can become the workspace default; target bindings may still select candidates for controlled experiments. An administrator may accept only the same persisted report that passed every threshold. Rollback prefers the previous eligible revision of the same Skill and otherwise restores platform `rule-v1`.

## Alternatives considered

We did not store shadow output in Probe Reports with a flag because any shared-table path could be consumed accidentally by caching, clustering, or downstream queries. We did not keep only ephemeral CI JSON because runtime acceptance and rollback need auditable identities. We did not prohibit candidate target bindings because a narrow object-level experiment is needed to produce real comparisons; the production default remains hard-gated by quality state.

## Consequences

The stub verifies the complete promotion structure without access to the internal model, and a real Agent later reuses the same Golden input and thresholds. The existing rule-v1 platform default is explicitly grandfathered as eligible, while its comparison report preserves evidence and safety gaps. A Golden Set change produces a new hash, so an old evaluation cannot masquerade as the new baseline; thresholds, evaluation identity, human reason, and rollback target remain traceable.
