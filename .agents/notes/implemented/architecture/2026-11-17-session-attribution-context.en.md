# Agent Note: Shared Session Attribution Context and Evidence Coordinates

Status: implemented

English | [中文](2026-11-17-session-attribution-context.md)

## Problem

Reloading and assembling a Session for every Badcase creates N+1 reads, gives cases from the same Session inconsistent snapshots, and encourages executors to guess object occurrences or report nodes from summaries. Persisting raw messages long-term would also expand the sensitive-data boundary.

## Decision

Before engine execution, the attribution Runner batch-reads normalized Agent nodes and every matching occurrence of the user-selected object. It builds one `attribution-context/v1` bundle per Session, then derives a per-Badcase projection containing only a bundle reference, report coordinate, and path from the object to the report node. The bundle also contains knowledge evidence, historical probe IDs, source versions, redaction declarations, and degradation warnings; every event reference resolves to an evidence point in the same bundle. The manifest uses the SHA-256 of canonical bundle JSON instead of a temporary per-case coordinate hash. Raw messages, credentials, and complete payloads do not enter the bundle, report, or business tables by default.

## Alternatives considered

Copying a complete bundle into every Probe Report was rejected because it amplifies storage and retains Trace data long-term. Calling an upstream API per case was rejected because snapshots from one Session could drift, so batched normalized facts are the default source; raw content may be fetched temporarily only when an executor explicitly needs it and the m12-01 seam is available. Allowing the model to select another `probe_object` was rejected because it bypasses the user-selected target and PotentialMatcher revision semantics.

## Consequences

Multiple Badcases in one Session share the same hash and structural snapshot while retaining distinct report coordinates. Missing nodes, degraded relations, and truncation produce explicit warnings instead of fabricated messages or versions. The current boundary retains at most 512 Agent nodes and 256 object occurrences and applies deterministic truncation with warnings. A bundle lives only for one Runner invocation and the later Agent executor can consume its projection directly; cross-retry audit should use a short-lived execution artifact rather than Probe Report storage.
