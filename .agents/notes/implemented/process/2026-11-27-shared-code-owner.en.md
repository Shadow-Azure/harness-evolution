# Agent Note: Shared code ownership in CODEOWNERS

Status: implemented

English | [中文](2026-11-27-shared-code-owner.md)

## Problem

The `Protect main` ruleset enables `require_code_owner_review: true`, while `.github/CODEOWNERS` lists only `@Shadow-Azure`. Other collaborators' approvals count toward the required approval count but not toward code-owner review: the PR keeps showing "Approvals 1 still required", and only the repository owner can unblock it. HaleyBG, the regular reviewer, is stuck at the last step every time; the ruleset bypass list lets her merge by skipping the rules, but that neither changes review semantics nor clears the blocked merge box.

## Decision

Register `@HaleyBG` next to the owner in the `*` line of CODEOWNERS, keeping `require_code_owner_review` as is: an approval from either code owner satisfies code-owner review, so HaleyBG can approve and merge independently and the owner is no longer the minimum review bottleneck.

## Alternatives considered

- Remove `require_code_owner_review` from the ruleset: equivalent to accepting any single collaborator approval, losing the "must be approved by a designated code owner" semantics and making CODEOWNERS inert.
- Rely on the ruleset bypass (`User 68089448`, `pull_request`): she can merge, but the UI still shows blocked, and this is a review bypass rather than independent review.
- Give HaleyBG the admin role: excessive permissions and no change to review semantics.

## Consequences

- Either code owner's approval unblocks the PR; review responsibility is shared by two people. The required approval count stays at 1 and must still come from a code owner (authors cannot self-approve).
- PRs authored by HaleyBG still need another code owner's approval; this is a GitHub platform limitation, not resolved by this decision.
- The comment in `.github/CODEOWNERS` and its dependency on the ruleset must stay in sync; update the comment whenever the list changes.
