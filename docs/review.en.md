# PR Review

English | [中文](review.md)

> Type: process | Layer: review engineering. The goal is to let the maintainer understand what the PR does, why, and at what cost.

## Core intent

The first duty of a review document is understanding, not fact listing: pair abstract mechanisms with everyday analogies, explain each term in one plain sentence on first use, and ground claims in real call chains and real input-output. After reading, the maintainer should answer three questions: what problem is solved, how, and at what cost.

## Workflow

1. Collect facts: use `gh pr view` for title, description and size; `git diff --name-status <base>...<head>` for per-file status; copy the PR's verification claims verbatim.
2. Read the main line: follow the data flow from entry to boundary; line anchors come from actual reading, never estimates.
3. Produce the document: `plans/yyyy-mm-dd-pr<N>-review.md`, containing the change tree, one-page overview, architecture tour, data-flow walkthrough, reading map, manual acceptance, discussion points, triage table and file-level analysis.
4. For per-file annotation, use the format in `.agents/skills/pr-review/SKILL.md`; address review comments with `.agents/skills/pr-review-fix/SKILL.md`.

## Evidence requirements

- Claims about third-party or framework behavior must be tested: read package source, run a minimal reproduction, or cite official documentation.
- Files not fully read stay marked `◻` in the reading map; never pretend to have read them.
- Verification commands must actually run; unrun items say "not verified" and never "passed".
- Risks around security, data consistency, concurrency or state machines state the trigger condition and the suggested owning phase.

## Discussion format

Every discussion point has five parts: **Location** (file:line), **Observation**, **Question**, **Prediction**, **Conclusion**. The prediction is an initial opinion open to challenge; the conclusion stays empty for the maintainer. Settled items record date, rationale and measured data.

## Triage table

| Finding | Nature | Destination |
|---|---|---|
| Defect | bug | Fix PR or postmortem |
| Design trade-off | decision | Update the owning Agent Note |
| Usage steps | how-to | development.md |
| State mismatch | fact | The corresponding docs page |
| Review process | process | This review document |

The review report never enters `.agents/notes/`: that is a closed decision-record system whose classes, skeleton and bilingual trio are not designed for process records.

## Discipline

- Never decide for the maintainer: discussion points offer predictions, not conclusions.
- Never manufacture urgency: findings with no present harm are labeled "no present harm".
- Never restate code literally: explain intent, mechanism, boundary and cost.
- Review language follows the repository: the resident review standard is bilingual; an individual review record may be Chinese only.
