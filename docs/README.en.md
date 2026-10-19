# Documentation Map

English | [中文](README.md)

The sole index for `docs/`. Every resident document must be registered in the table below; `verify-doc-index` reconciles both directions. Layering and writing rules live in [AGENTS.md](AGENTS.md).

## Map

| Document | Question it answers |
|---|---|
| [AGENTS.md](AGENTS.md) | Documentation layering, writing rules and gate entry points |
| [architecture.en.md](architecture.en.md) | Service boundaries, data flow, data-layer strategy and current API |
| [roadmap.en.md](roadmap.en.md) | Product phase roadmap and per-phase acceptance |
| [development.en.md](development.en.md) | Local environment, daily loop, commits and flow operations |
| [review.en.md](review.en.md) | Structured PR review, evidence requirements and triage |
| [charter.en.md](charter.en.md) | Experiment protocol, evolution criteria and safety boundaries |
| [metrics.en.md](metrics.en.md) | Primary metrics, guardrail metrics and run-record requirements |
| [i18n/README.en.md](i18n/README.en.md) | Bilingual trio, re-recording and exemption rules |
| [i18n/terminology.en.md](i18n/terminology.en.md) | Chinese-English terminology table and banned alternatives |
| [i18n/translation-prompt.en.md](i18n/translation-prompt.en.md) | Template for completing the English side |
| [postmortem/README.en.md](postmortem/README.en.md) | Incident-review structure and numbering rules |

## Reading order

- First contact: root [README.en.md](../README.en.md) → [architecture.en.md](architecture.en.md) → [development.en.md](development.en.md).
- Before changing code: the issue under `.agents/flow/` → this map → the matching implementation slice.
- Before running an experiment: [charter.en.md](charter.en.md) → [metrics.en.md](metrics.en.md) → `research/experiments/_template`.
- Before reviewing a PR: [review.en.md](review.en.md) → `.agents/skills/pr-review/SKILL.md`.

## Maintenance rules

- Each fact lives on one page; cross-page references are links, never restatements.
- Every resident document keeps a complete bilingual trio and a registered word budget.
- Adding, moving or deleting a document updates this table in the same change; gates block dead links and unregistered files.
