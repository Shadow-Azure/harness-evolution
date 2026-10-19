# Bilingual Pairing

English | [中文](README.md)

Every document in the corpus is paired across Chinese and English, and a machine certifies that "both sides say the same thing": humans make translation choices, gates own consistency. This page is the sole home of the pairing contract.

## Trio

- A pair is three files in one directory: Chinese base `foo.md` + English side `foo.en.md` + consistency record `foo.i18n.yaml`. They merge as a unit; a PR always lands all three, never one side alone.
- Both languages are equally authoritative: either side may come first, the other is translated against it, and neither is a "translation appendage".
- The record stores both sides' git blob hashes (`git hash-object` semantics, computable before commit, so local checks are immediate). Changing either side → minimally patch the other against that diff (not a retranslation) → `pnpm record:i18n -- docs/foo.md` re-records; the yaml diff is the reviewable "confirmed consistent" action.
- Recovery: any historical version of the record yaml still points at blobs reachable in the git object store, usable as the comparison text before re-recording.

## Switcher line

Every corpus document carries a switcher line: base side `[English](foo.en.md) | 中文`, English side `English | [中文](foo.md)`. Ordinary documents place it on the first non-empty line after H1; Agent Notes place it after the `Status:` line (the first-three-lines format is another gate's fixed contract and is not displaced). Both sides must have it; gates check.

## Structural mirror

Both sides must mirror structurally: heading levels and order, code fences (info string and content **byte-identical** — comments and diagram text inside fences are not translated), table rows and columns, list kind/ordered start/count, link targets (except the switcher line). Corpus-relative links: base side uses `.md`, English side uses `.en.md`; query and non-md fragments stay verbatim; an md target's fragment is the heading's locale projection, outside the mirror, and checked per side by the dead-anchor gate. Generated regions (`<!-- BEGIN GENERATED -->`) are byte-identical except locale-projected document paths.

## Terminology and prompt

The translation supply chain is machine-backed: [terminology.md](terminology.en.md) data rows are byte-identical across sides, and registered banned alternatives appearing in English-side prose turn red; [translation-prompt.md](translation-prompt.en.md) is the template for completing the English side, with placeholders checked by verify-terminology.

## Gates and workflow

- `pnpm verify:docs` includes verify-translation-pairing: complete trio, matching hashes, switcher lines, link locale, generated regions and structural signature all must hold.
- Daily loop: edit side A → minimally patch side B → re-record with `--write`, in the same PR; drifted pairs fail CI.
- Gate boundary: green proves "nothing drifted since the last confirmation", not that the translation is correct — semantic fidelity and wording belong to review.

## Scope and exemptions

Corpus = root `README.md`, `docs/**`, `.agents/notes/**` (except `archived/` — frozen artifacts are governed by the archive gate, sha256 stronger than pairing), `.agents/flow/**`. The only exemption registry is [scripts/translation-pairing.manifest.json](../../scripts/translation-pairing.manifest.json) (only an `excluded` field): currently the two AGENTS.md files (agent instruction layer, single-language like the blueprint). New exemptions change the manifest and state the reason in the PR.
